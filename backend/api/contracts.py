"""Contract upload + processing endpoints."""
import asyncio
import hashlib
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile, File, Form, Query, Header
from fastapi.responses import Response as FileResponse, StreamingResponse
from google.cloud import storage as gcs
from google.oauth2 import service_account
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.db import get_db, SessionLocal
from backend.models import (
    AgentOutput, AuditLog, Contract, ContractAssignment, ContractComment,
    Decision, SecurityEvent, ScoringFeedback,
)
from backend import audit
from backend.extractors import extract_text
from backend.segmentation import segment_clauses
from backend.agents.security import scan as security_scan
from backend import lobstertrap as lt_client
from backend.orchestrator import run_pipeline

logger = logging.getLogger(__name__)

router = APIRouter()


# ── Pydantic response schemas ─────────────────────────────────────────────────

class ContractSummary(BaseModel):
    id: int
    filename: str
    status: str
    uploaded_at: Optional[str]
    n_clauses: int


class ContractListResponse(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[ContractSummary]


class UploadResponse(BaseModel):
    id: int
    status: str
    filename: str
    n_clauses: Optional[int] = None
    char_count: Optional[int] = None
    metadata: Optional[dict] = None
    security_scan: Optional[dict] = None
    # Present only for duplicates
    existing_filename: Optional[str] = None
    existing_status: Optional[str] = None
    uploaded_at: Optional[str] = None
    message: Optional[str] = None


class BulkUploadResponse(BaseModel):
    total: int
    queued: int
    duplicates: int
    quarantined: int
    errors: int
    results: list[dict]


class DecideResponse(BaseModel):
    contract_id: int
    decision: str
    new_status: str


class CommentResponse(BaseModel):
    id: int
    contract_id: int
    actor: str
    role: str
    comment: str
    comment_type: str
    created_at: str


class AssignResponse(BaseModel):
    assignment_id: int
    contract_id: int
    assigned_role: str
    can_approve: bool


class RevokeResponse(BaseModel):
    revoked: bool
    contract_id: int
    assigned_role: str


class DeleteResponse(BaseModel):
    deleted: bool
    contract_id: int
    filename: str
    pinecone_vectors_removed: int
    gcs_deleted: bool


def _run_pipeline_background(contract_id: int) -> None:
    """Run the agent pipeline in a background task with its own DB session.

    BackgroundTasks execute after the response has been sent, so the request's
    DB session is already closed. We open a fresh session here instead.
    """
    db = SessionLocal()
    try:
        run_pipeline(db, contract_id)
    except Exception:
        logger.exception("Background pipeline failed for contract %d", contract_id)
    finally:
        db.close()


# GCS bucket for uploaded contract files.
# Auth strategy (in priority order):
#   1. GCS_SERVICE_ACCOUNT_KEY — path to a service account JSON key file.
#      Use this for local dev and CI. Set in .env.
#   2. Workload Identity (no key file) — on Cloud Run, attach the service
#      account to the Cloud Run service and omit GCS_SERVICE_ACCOUNT_KEY.
#      The client picks it up automatically from the metadata server.
GCS_BUCKET_NAME = os.getenv("GCS_BUCKET_NAME", "")
GCS_SERVICE_ACCOUNT_KEY = os.getenv("GCS_SERVICE_ACCOUNT_KEY", "")  # path to JSON key
_gcs_client: gcs.Client | None = None

# Maximum file size accepted by the upload endpoints (bytes).
# Configurable via env var MAX_UPLOAD_BYTES; defaults to 50 MB.
MAX_UPLOAD_BYTES: int = int(os.getenv("MAX_UPLOAD_BYTES", str(50 * 1024 * 1024)))


def _get_bucket() -> gcs.Bucket:
    global _gcs_client
    if not GCS_BUCKET_NAME:
        raise RuntimeError("GCS_BUCKET_NAME is not set in environment")
    if _gcs_client is None:
        if GCS_SERVICE_ACCOUNT_KEY:
            # Explicit service account key — local dev / CI
            credentials = service_account.Credentials.from_service_account_file(
                GCS_SERVICE_ACCOUNT_KEY,
                scopes=["https://www.googleapis.com/auth/cloud-platform"],
            )
            _gcs_client = gcs.Client(credentials=credentials, project=credentials.project_id)
            logger.info("GCS client initialised with service account key: %s", GCS_SERVICE_ACCOUNT_KEY)
        else:
            # Workload Identity on Cloud Run — no key file needed
            _gcs_client = gcs.Client()
            logger.info("GCS client initialised with Workload Identity (Cloud Run)")
    return _gcs_client.bucket(GCS_BUCKET_NAME)


def _upload_to_gcs(file_bytes: bytes, blob_name: str) -> str:
    """Upload bytes to GCS. Returns the gs:// URI.

    Blob names are SHA-256 derived, so if the blob already exists it is
    guaranteed to have identical content — skip the upload rather than
    attempting an overwrite (which requires storage.objects.delete permission).
    """
    bucket = _get_bucket()
    blob = bucket.blob(blob_name)
    try:
        if blob.exists():
            logger.info("GCS blob already exists, skipping upload (dedup): %s", blob_name)
            return f"gs://{GCS_BUCKET_NAME}/{blob_name}"
    except Exception:
        # If we can't check existence, proceed with upload and let it fail
        # with a clear error rather than silently swallowing.
        logger.warning("Could not check GCS blob existence for %s — attempting upload anyway", blob_name)

    blob.upload_from_string(file_bytes)
    logger.info("Uploaded %d bytes to GCS: %s", len(file_bytes), blob_name)
    return f"gs://{GCS_BUCKET_NAME}/{blob_name}"


@router.get("/", response_model=ContractListResponse)
def list_contracts(
    status: str | None = Query(None, description="Filter by contract status (e.g. 'legal_review')"),
    assigned_role: str | None = Query(None, description="Include contracts with an active assignment for this role"),
    limit: int = Query(50, ge=1, le=500, description="Max results to return"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    db: Session = Depends(get_db),
):
    """List contracts with optional filtering and pagination.

    Filters:
      status        — filter by contract status (e.g. 'legal_review')
      assigned_role — include contracts where this role has an active assignment
                      (used to surface escalated contracts to Executive / Auditor / etc.)
    Both filters can be combined — e.g. status=legal_review&assigned_role=Executive.
    """
    q = db.query(Contract).order_by(Contract.uploaded_at.desc())

    if assigned_role:
        assigned_ids = (
            db.query(ContractAssignment.contract_id)
            .filter_by(assigned_role=assigned_role, active=True)
            .subquery()
        )
        q = q.filter(Contract.id.in_(assigned_ids))

    if status:
        q = q.filter(Contract.status == status)

    total = q.count()
    rows = q.offset(offset).limit(limit).all()

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": [
            {
                "id": r.id,
                "filename": r.filename,
                "status": r.status,
                "uploaded_at": r.uploaded_at.isoformat() if r.uploaded_at else None,
                "n_clauses": len(r.clauses) if r.clauses else 0,
            }
            for r in rows
        ],
    }


@router.get("/{contract_id}")
def get_contract(contract_id: int, db: Session = Depends(get_db)):
    contract = db.query(Contract).filter(Contract.id == contract_id).first()
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")

    # Surface latest agent outputs keyed by agent name
    agent_outputs: dict[str, dict] = {}
    rows = (
        db.query(AgentOutput)
        .filter(AgentOutput.contract_id == contract_id)
        .order_by(AgentOutput.created_at.asc())
        .all()
    )
    for row in rows:
        agent_outputs[row.agent_name] = {
            "output": row.output,
            "confidence": row.confidence,
            "prompt_hash": row.prompt_hash,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }

    # Decision history (newest first)
    decisions = [
        {
            "id": d.id,
            "recommendation": d.recommendation,
            "reasoning": d.reasoning,
            "reviewer_role": d.reviewer_role,
            "decided_at": d.decided_at.isoformat() if d.decided_at else None,
            "scoring_details": d.scoring_details,  # composite score, sub-scores, rationale
        }
        for d in sorted(contract.decisions or [], key=lambda d: d.decided_at or "", reverse=True)
    ]

    return {
        "id": contract.id,
        "filename": contract.filename,
        "status": contract.status,
        "uploaded_at": contract.uploaded_at.isoformat() if contract.uploaded_at else None,
        "raw_text": contract.raw_text,
        "clauses": contract.clauses,
        "agent_outputs": agent_outputs,
        "decisions": decisions,
        "security_events": [
            {
                "event_type": e.event_type,
                "severity": e.severity,
                "details": e.details,
            }
            for e in contract.security_events
        ],
        "comments": [
            {
                "id":           c.id,
                "actor":        c.actor,
                "role":         c.role,
                "comment":      c.comment,
                "comment_type": c.comment_type,
                "created_at":   c.created_at.isoformat() if c.created_at else None,
            }
            for c in (contract.comments or [])
        ],
        "assignments": [
            {
                "id":            a.id,
                "assigned_role": a.assigned_role,
                "assigned_by":   a.assigned_by,
                "can_approve":   a.can_approve,
                "note":          a.note,
                "active":        a.active,
                "assigned_at":   a.assigned_at.isoformat() if a.assigned_at else None,
            }
            for a in (contract.assignments or [])
        ],
    }


@router.get("/{contract_id}/file")
def get_contract_file(contract_id: int, db: Session = Depends(get_db)):
    """Stream the original contract file (PDF or DOCX) from GCS.

    Returns the raw bytes with the correct Content-Type so browsers and
    Streamlit's iframe preview can render PDFs inline.
    """
    contract = db.query(Contract).filter(Contract.id == contract_id).first()
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")
    if not contract.gcs_uri:
        raise HTTPException(
            status_code=404,
            detail="No file stored for this contract (upload may predate GCS storage)",
        )

    blob_name = contract.gcs_uri.replace(f"gs://{GCS_BUCKET_NAME}/", "")
    try:
        bucket = _get_bucket()
        blob = bucket.blob(blob_name)
        file_bytes = blob.download_as_bytes()
    except Exception as exc:
        logger.exception("Failed to fetch contract %d from GCS (%s): %s", contract_id, blob_name, exc)
        raise HTTPException(status_code=503, detail=f"File unavailable: {exc}")

    suffix = Path(contract.filename).suffix.lower()
    content_type = (
        "application/pdf"
        if suffix == ".pdf"
        else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )

    return FileResponse(
        content=file_bytes,
        media_type=content_type,
        headers={
            "Content-Disposition": f'inline; filename="{contract.filename}"',
            "Content-Length": str(len(file_bytes)),
        },
    )


_SSE_FINAL_STATUSES = frozenset({
    "auto_approved", "manager_review", "legal_review", "rejected",
    "approved", "quarantined", "extraction_failed", "pipeline_failed", "processed",
})


@router.get("/{contract_id}/stream")
async def stream_contract_status(contract_id: int):
    """Server-Sent Events (SSE) endpoint for live pipeline status updates.

    Emits ``data: {"status": "...", "contract_id": N}`` every 500 ms until a
    terminal status is reached, then emits a final event with ``"done": true``
    and closes the stream.

    The frontend should open this with ``EventSource`` — no polling needed.

    Notes on DB isolation: a fresh ``SessionLocal()`` session is opened on
    every poll iteration and closed immediately after.  This guarantees each
    poll starts a new transaction at READ COMMITTED, so the SSE consumer always
    sees the latest commits from the background orchestrator thread without
    needing ``expire_all()`` or fighting open-transaction snapshot isolation.
    """
    async def _generate():
        last_status: str | None = None
        while True:
            # Open a brand-new session for every poll so we always read at
            # READ COMMITTED (no stale open-transaction snapshot).
            db_poll = SessionLocal()
            try:
                contract = db_poll.query(Contract).filter(Contract.id == contract_id).first()
                status: str | None = contract.status if contract else None
            finally:
                db_poll.close()

            if status is None:
                yield f"data: {json.dumps({'error': 'not_found', 'contract_id': contract_id})}\n\n"
                return

            status = status or "uploading"

            # Only push an event when the status actually changes
            if status != last_status:
                last_status = status
                payload = {"status": status, "contract_id": contract_id}
                if status in _SSE_FINAL_STATUSES:
                    payload["done"] = True  # type: ignore[assignment]
                yield f"data: {json.dumps(payload)}\n\n"

            if status in _SSE_FINAL_STATUSES:
                return  # generator exhausted → FastAPI closes the stream

            await asyncio.sleep(0.5)

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",   # disable nginx / Cloud Run buffering
            "Connection": "keep-alive",
        },
    )


@router.delete("/{contract_id}", response_model=DeleteResponse)
def delete_contract(
    contract_id: int,
    actor: str = "user:Procurement Analyst",
    db: Session = Depends(get_db),
):
    """Delete a contract and all its associated data.

    Deletes (in order):
      1. agent_outputs, decisions, security_events  (child rows)
      2. The GCS blob (best-effort — skipped if blob not found or no GCS configured)
      3. The contract row itself

    Audit logs referencing this contract are intentionally kept — they form
    the immutable governance trail and must survive the contract deletion.

    Returns 404 if the contract does not exist.
    """
    contract = db.query(Contract).filter(Contract.id == contract_id).first()
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")

    filename = contract.filename
    gcs_uri = contract.gcs_uri
    file_hash = contract.file_hash
    clauses = list(contract.clauses or [])   # capture before ORM object is deleted

    # Write a deletion audit entry BEFORE deleting so the trail is complete
    try:
        audit.log(
            db,
            actor=actor,
            action="delete",
            resource=f"contract:{contract_id}",
            before={
                "filename": filename,
                "status": contract.status,
                "hash_prefix": (file_hash or "")[:12],
                "gcs_uri": gcs_uri,
            },
            after=None,
        )
    except Exception:
        logger.exception("Audit log failed before deleting contract %d (continuing)", contract_id)

    # Delete child rows in FK-safe order (audit_logs are intentionally kept).
    # Rules:
    #   scoring_feedback.decision_id → decisions.id   → must go before decisions
    #   scoring_feedback.contract_id → contracts.id   → must go before contracts
    #   everything else              → contracts.id   → must go before contracts
    try:
        db.query(ScoringFeedback).filter(ScoringFeedback.contract_id == contract_id).delete()
        db.query(ContractComment).filter(ContractComment.contract_id == contract_id).delete()
        db.query(ContractAssignment).filter(ContractAssignment.contract_id == contract_id).delete()
        db.query(AgentOutput).filter(AgentOutput.contract_id == contract_id).delete()
        db.query(Decision).filter(Decision.contract_id == contract_id).delete()
        db.query(SecurityEvent).filter(SecurityEvent.contract_id == contract_id).delete()
        db.delete(contract)
        db.commit()
        logger.info("Deleted contract %d (%s) from database", contract_id, filename)
    except Exception as exc:
        db.rollback()
        logger.exception("Database delete failed for contract %d: %s", contract_id, exc)
        raise HTTPException(status_code=500, detail=f"Delete failed: {exc}")

    # Delete Pinecone vectors (best-effort — only uploaded contracts have vectors;
    # corpus contracts use a different ID prefix and are never deleted here)
    pinecone_deleted = 0
    try:
        from backend.rag.ingest import delete_contract_vectors
        pinecone_deleted = delete_contract_vectors(contract_id, clauses)
    except Exception:
        logger.exception(
            "Pinecone vector delete failed for contract %d (non-fatal — DB row already removed)",
            contract_id,
        )

    # Delete the GCS blob (best-effort)
    gcs_deleted = False
    if gcs_uri and GCS_BUCKET_NAME:
        try:
            blob_name = gcs_uri.replace(f"gs://{GCS_BUCKET_NAME}/", "")
            bucket = _get_bucket()
            blob = bucket.blob(blob_name)
            if blob.exists():
                blob.delete()
                gcs_deleted = True
                logger.info("Deleted GCS blob: %s", blob_name)
            else:
                logger.warning("GCS blob not found (already deleted?): %s", blob_name)
        except Exception:
            logger.exception(
                "GCS blob delete failed for contract %d (non-fatal — DB row already removed)",
                contract_id,
            )

    logger.info(
        "Contract %d fully deleted — db=True gcs=%s pinecone_vectors=%d",
        contract_id, gcs_deleted, pinecone_deleted,
    )

    return {
        "deleted": True,
        "contract_id": contract_id,
        "filename": filename,
        "pinecone_vectors_removed": pinecone_deleted,
        "gcs_deleted": gcs_deleted,
    }


@router.post("/{contract_id}/process")
def process_contract(
    contract_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Kick off the agent pipeline in the background.

    Returns immediately with {"contract_id": ..., "queued": true}.
    Poll GET /contracts/{id} for status changes.
    """
    contract = db.query(Contract).filter(Contract.id == contract_id).first()
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")
    background_tasks.add_task(_run_pipeline_background, contract_id)
    return {"contract_id": contract_id, "queued": True, "current_status": contract.status}


@router.get("/{contract_id}/audit-report")
def audit_report(contract_id: int, db: Session = Depends(get_db)):
    """Compiled audit-ready report for one contract.

    Includes: contract metadata, every agent output (with prompt hashes),
    every Decision (AI + human), every security event, and every audit log
    entry that touched this contract — all in one downloadable JSON blob.
    Suitable for handing to an auditor or regulator.
    """
    contract = db.query(Contract).filter(Contract.id == contract_id).first()
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")

    agent_outputs = (
        db.query(AgentOutput)
        .filter(AgentOutput.contract_id == contract_id)
        .order_by(AgentOutput.created_at.asc())
        .all()
    )
    audit_logs = (
        db.query(AuditLog)
        .filter(AuditLog.resource == f"contract:{contract_id}")
        .order_by(AuditLog.timestamp.asc())
        .all()
    )

    return {
        "report_generated_at": datetime.now(timezone.utc).isoformat(),
        "report_version": "1.0",
        "contract": {
            "id": contract.id,
            "filename": contract.filename,
            "file_hash": contract.file_hash,
            "uploaded_at": contract.uploaded_at.isoformat() if contract.uploaded_at else None,
            "current_status": contract.status,
            "n_clauses": len(contract.clauses) if contract.clauses else 0,
            "char_count": len(contract.raw_text or ""),
        },
        "agent_outputs": [
            {
                "agent_name": ao.agent_name,
                "output": ao.output,
                "confidence": ao.confidence,
                "prompt_hash": ao.prompt_hash,
                "created_at": ao.created_at.isoformat() if ao.created_at else None,
            }
            for ao in agent_outputs
        ],
        "decisions": [
            {
                "id": d.id,
                "recommendation": d.recommendation,
                "reasoning": d.reasoning,
                "reviewer_role": d.reviewer_role,
                "decided_at": d.decided_at.isoformat() if d.decided_at else None,
                "scoring_details": d.scoring_details,
            }
            for d in contract.decisions
        ],
        "security_events": [
            {
                "event_type": se.event_type,
                "severity": se.severity,
                "details": se.details,
                "created_at": se.created_at.isoformat() if se.created_at else None,
            }
            for se in contract.security_events
        ],
        "audit_log": [
            {
                "actor": al.actor,
                "action": al.action,
                "before": al.before,
                "after": al.after,
                "timestamp": al.timestamp.isoformat() if al.timestamp else None,
            }
            for al in audit_logs
        ],
    }


# Human decision actions. Status mapping mirrors the AI's, but with the
# reviewer_role recording who actually pressed the button.
HUMAN_DECISION_TO_STATUS = {
    "APPROVED": "approved",
    "REJECTED": "rejected",
    "ESCALATED_LEGAL": "legal_review",
}


@router.post("/{contract_id}/decide", response_model=DecideResponse)
def make_human_decision(
    contract_id: int,
    decision: str = Form(...),
    reasoning: str = Form(...),
    actor: str = Form(...),
    role: str = Form(""),       # caller's role — used to deactivate their assignment
    db: Session = Depends(get_db),
):
    """Record a human approval decision. `decision` is one of
    APPROVED | REJECTED | ESCALATED_LEGAL.

    Permission check: the caller must either hold a role with default approval
    permission OR have an active ContractAssignment with can_approve=True.
    """
    if decision not in HUMAN_DECISION_TO_STATUS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid decision: {decision}. Use one of {list(HUMAN_DECISION_TO_STATUS)}",
        )

    contract = db.query(Contract).filter(Contract.id == contract_id).first()
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")

    # Deactivate caller's active assignment (if any) — they've acted on it
    if role:
        active_assignment = (
            db.query(ContractAssignment)
            .filter_by(contract_id=contract_id, assigned_role=role, active=True)
            .first()
        )
        if active_assignment:
            active_assignment.active = False

    decision_row = Decision(
        contract_id=contract_id,
        recommendation=decision,
        reasoning=reasoning,
        reviewer_role=actor,
    )
    db.add(decision_row)

    new_status = HUMAN_DECISION_TO_STATUS[decision]
    before_status = contract.status
    contract.status = new_status
    db.flush()  # get decision_row.id before commit

    # ── Auto-create ScoringFeedback so future contracts for this vendor
    # are aware of the human override and the reason given.
    # Maps human decision vs prior AI decision → feedback_type.
    try:
        ai_decision_row = (
            db.query(Decision)
            .filter_by(contract_id=contract_id)
            .filter(Decision.reviewer_role.like("agent:%"))
            .order_by(Decision.id.desc())
            .first()
        )
        ai_decision_code = ai_decision_row.recommendation if ai_decision_row else None

        # Determine feedback_type: did the human think the AI was too strict or too lenient?
        _leniency = {"AUTO_APPROVE": 0, "MANAGER_REVIEW": 1, "LEGAL_REVIEW": 2, "REJECT": 3,
                     "APPROVED": 0, "REJECTED": 3, "ESCALATED_LEGAL": 2}
        ai_rank  = _leniency.get(ai_decision_code, 1)
        hum_rank = _leniency.get(decision, 1)
        if hum_rank < ai_rank:
            feedback_type = "too_high"    # AI was stricter than needed
        elif hum_rank > ai_rank:
            feedback_type = "too_low"     # AI was too lenient
        else:
            feedback_type = "correct"

        # Grab composite score from latest AI decision's scoring_details
        composite_score = None
        if ai_decision_row and ai_decision_row.scoring_details:
            composite_score = ai_decision_row.scoring_details.get("composite_score")

        db.add(ScoringFeedback(
            contract_id=contract_id,
            decision_id=decision_row.id,
            feedback_type=feedback_type,
            ai_decision=ai_decision_code,
            human_decision=decision,
            composite_score=composite_score,
            notes=reasoning,            # ← reviewer's reason is stored here
            reviewer_role=actor,
        ))
        logger.info(
            "Human decision recorded for contract %s: %s → %s (feedback_type=%s)",
            contract_id, ai_decision_code, decision, feedback_type,
        )
    except Exception:
        logger.warning(
            "Could not auto-create ScoringFeedback for contract %s (non-fatal)",
            contract_id, exc_info=True,
        )

    db.commit()

    audit.log(
        db,
        actor=actor,
        action="decide",
        resource=f"contract:{contract_id}",
        before={"status": before_status},
        after={"decision": decision, "reasoning": reasoning, "status": new_status},
    )
    return {
        "contract_id": contract_id,
        "decision": decision,
        "new_status": new_status,
    }


# ── Comments ──────────────────────────────────────────────────────────────────

@router.post("/{contract_id}/comment", response_model=CommentResponse, status_code=201)
def add_comment(
    contract_id: int,
    comment: str = Form(...),
    role: str = Form(...),
    actor: str = Form(...),
    comment_type: str = Form("comment"),   # comment | recommendation | escalation
    db: Session = Depends(get_db),
):
    """Add a comment or recommendation to a contract.

    Available to all roles. Executive and Auditor use this as their
    primary way to provide input without approving/rejecting.
    """
    contract = db.query(Contract).filter(Contract.id == contract_id).first()
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")

    if not comment.strip():
        raise HTTPException(status_code=400, detail="Comment cannot be empty")

    row = ContractComment(
        contract_id=contract_id,
        actor=actor,
        role=role,
        comment=comment.strip(),
        comment_type=comment_type,
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    audit.log(
        db,
        actor=actor,
        action="comment",
        resource=f"contract:{contract_id}",
        after={"role": role, "comment_type": comment_type, "comment_preview": comment[:100]},
    )

    return {
        "id":           row.id,
        "contract_id":  contract_id,
        "actor":        row.actor,
        "role":         row.role,
        "comment":      row.comment,
        "comment_type": row.comment_type,
        "created_at":   row.created_at.isoformat(),
    }


# ── Assignments / Escalations ─────────────────────────────────────────────────

# Roles that Legal / Compliance can escalate to
ESCALATION_TARGETS = {"Legal Reviewer", "Compliance Officer", "Executive", "Auditor"}
# Roles that can create escalations
ESCALATION_SOURCES = {"Legal Reviewer", "Compliance Officer"}


@router.post("/{contract_id}/assign", response_model=AssignResponse, status_code=201)
def assign_contract(
    contract_id: int,
    assigned_role: str = Form(...),
    assigned_by: str = Form(...),    # actor string e.g. "user:Legal Reviewer"
    assigning_role: str = Form(...), # role of the caller e.g. "Legal Reviewer"
    can_approve: bool = Form(False),
    note: str = Form(""),
    db: Session = Depends(get_db),
):
    """Escalate / assign a contract to another role for review.

    Only Legal Reviewer and Compliance Officer can create assignments.
    If can_approve=True, the assigned role gains approve/reject permission
    on this specific contract, overriding their default read-only status.
    """
    if assigning_role not in ESCALATION_SOURCES:
        raise HTTPException(
            status_code=403,
            detail=f"Only Legal Reviewer and Compliance Officer can escalate contracts.",
        )

    if assigned_role not in ESCALATION_TARGETS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid target role: {assigned_role}.",
        )

    contract = db.query(Contract).filter(Contract.id == contract_id).first()
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")

    # Avoid duplicate active assignments for the same role
    existing = (
        db.query(ContractAssignment)
        .filter_by(contract_id=contract_id, assigned_role=assigned_role, active=True)
        .first()
    )
    if existing:
        # Update existing rather than creating a duplicate
        existing.can_approve = can_approve
        existing.note = note or existing.note
        existing.assigned_by = assigned_by
        db.commit()
        assignment_id = existing.id
    else:
        row = ContractAssignment(
            contract_id=contract_id,
            assigned_role=assigned_role,
            assigned_by=assigned_by,
            can_approve=can_approve,
            note=note.strip() if note else None,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        assignment_id = row.id

    # Also log an escalation comment so the audit trail is clear
    db.add(ContractComment(
        contract_id=contract_id,
        actor=assigned_by,
        role=assigning_role,
        comment=(
            f"Escalated to **{assigned_role}** for review"
            + (f" with approve/reject permission" if can_approve else " (advisory)")
            + (f". Note: {note}" if note else ".")
        ),
        comment_type="escalation",
    ))
    db.commit()

    audit.log(
        db,
        actor=assigned_by,
        action="assign",
        resource=f"contract:{contract_id}",
        after={
            "assigned_role": assigned_role,
            "can_approve":   can_approve,
            "note":          note,
        },
    )

    return {
        "assignment_id": assignment_id,
        "contract_id":   contract_id,
        "assigned_role": assigned_role,
        "can_approve":   can_approve,
    }


@router.delete("/{contract_id}/assign/{assigned_role}", response_model=RevokeResponse)
def revoke_assignment(
    contract_id: int,
    assigned_role: str,
    x_actor: str = Header(..., description="Actor performing the revocation (e.g. 'user:Legal Reviewer')"),
    db: Session = Depends(get_db),
):
    """Revoke an active assignment for a role on a contract.

    Pass the actor identity in the X-Actor request header.
    (DELETE bodies are not reliably forwarded by all HTTP clients / proxies.)
    """
    actor = x_actor
    assignment = (
        db.query(ContractAssignment)
        .filter_by(contract_id=contract_id, assigned_role=assigned_role, active=True)
        .first()
    )
    if not assignment:
        raise HTTPException(status_code=404, detail="No active assignment found")

    assignment.active = False
    db.commit()

    audit.log(
        db,
        actor=actor,
        action="revoke_assignment",
        resource=f"contract:{contract_id}",
        after={"revoked_role": assigned_role},
    )
    return {"revoked": True, "contract_id": contract_id, "assigned_role": assigned_role}


@router.post("/{contract_id}/rescore")
def rescore_contract(contract_id: int, db: Session = Depends(get_db)):
    """Rerun Agent 5 on a contract using the current scoring policy.

    Does NOT call any LLM — it reads the existing agent_outputs from the DB
    and recomputes the composite score + decision with the active policy.
    Useful after changing scoring policy thresholds or weights.

    Returns the new scoring breakdown.
    """
    from backend.agents import scoring as scoring_engine
    from backend.agents.recommendation import _latest_output, _get_security_events, _DECISION_TO_STATUS

    contract = db.query(Contract).filter(Contract.id == contract_id).first()
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")

    # Read existing LLM outputs — no new Gemini calls
    risk       = _latest_output(db, contract_id, "risk")
    compliance = _latest_output(db, contract_id, "compliance")
    extraction = _latest_output(db, contract_id, "extraction")
    sec_events = _get_security_events(db, contract_id)

    if risk is None and compliance is None:
        raise HTTPException(
            status_code=422,
            detail="No agent outputs found for this contract. Run the pipeline first.",
        )

    policy = scoring_engine.load_policy(db)
    result = scoring_engine.decide(risk, compliance, extraction, sec_events, policy)

    # Insert new Decision row with updated scoring_details
    new_decision = Decision(
        contract_id=contract_id,
        recommendation=result.decision,
        reasoning=result.rationale[0] if result.rationale else result.decision,
        reviewer_role="agent:rescore",
        scoring_details=result.to_dict(),
    )
    db.add(new_decision)

    # Update contract status to reflect new decision
    new_status = _DECISION_TO_STATUS.get(result.decision)
    old_status = contract.status
    if new_status:
        contract.status = new_status

    db.commit()

    audit.log(
        db,
        actor="system:rescore",
        action="rescore",
        resource=f"contract:{contract_id}",
        before={"status": old_status},
        after={
            "decision": result.decision,
            "composite_score": result.composite_score,
            "new_status": contract.status,
        },
    )

    return {
        "contract_id":    contract_id,
        "new_decision":   result.decision,
        "new_status":     contract.status,
        "scoring_details": result.to_dict(),
    }


def _process_single_upload(
    file_bytes: bytes,
    filename: str,
    actor: str,
    db: Session,
    background_tasks: BackgroundTasks,
) -> dict:
    """Core upload logic shared by single-upload and bulk-upload endpoints.

    Performs: dedup check → GCS upload → DB row → text extraction →
    security gate → clause segmentation → background pipeline launch.

    Returns the standard response dict (same shape as /upload).
    Raises HTTPException on hard failures; returns a dict with
    status='error' on soft failures so bulk callers can continue.
    """
    suffix = Path(filename).suffix.lower()
    if suffix not in {".pdf", ".docx"}:
        return {
            "status": "error",
            "filename": filename,
            "message": f"Unsupported file type: {suffix}. Use PDF or DOCX.",
        }

    if not file_bytes:
        return {"status": "error", "filename": filename, "message": "Empty file"}
    if len(file_bytes) > MAX_UPLOAD_BYTES:
        return {
            "status": "error",
            "filename": filename,
            "message": f"File too large ({len(file_bytes):,} bytes). Maximum is {MAX_UPLOAD_BYTES:,} bytes (50 MB).",
        }

    file_hash = hashlib.sha256(file_bytes).hexdigest()

    # ---- Duplicate detection ----
    existing = (
        db.query(Contract)
        .filter(Contract.file_hash == file_hash)
        .order_by(Contract.uploaded_at.desc())
        .first()
    )
    if existing:
        logger.info(
            "Duplicate upload detected — file_hash=%s matches contract %d (%s)",
            file_hash[:12], existing.id, existing.filename,
        )
        audit.log(
            db,
            actor=actor,
            action="upload_duplicate",
            resource=f"contract:{existing.id}",
            after={"filename": filename, "hash_prefix": file_hash[:12]},
        )
        return {
            "id": existing.id,
            "status": "duplicate",
            "filename": filename,
            "existing_filename": existing.filename,
            "existing_status": existing.status,
            "uploaded_at": existing.uploaded_at.isoformat() if existing.uploaded_at else None,
            "message": (
                f"Already uploaded as '{existing.filename}' "
                f"(contract #{existing.id}, status '{existing.status}')."
            ),
        }

    # Upload to GCS
    blob_name = f"contracts/{file_hash}{suffix}"
    try:
        gcs_uri = _upload_to_gcs(file_bytes, blob_name)
    except Exception as e:
        logger.exception("GCS upload failed for %s", filename)
        return {"status": "error", "filename": filename, "message": f"File storage unavailable: {e}"}

    # Create contract row
    contract = Contract(
        filename=filename,
        status="uploading",
        file_hash=file_hash,
        gcs_uri=gcs_uri,
    )
    db.add(contract)
    try:
        db.commit()
    except Exception as db_exc:
        logger.error("DB commit failed on upload of %s: %s", filename, db_exc)
        db.rollback()
        from backend import cache as shield_cache
        shield_cache.write(
            "contract_upload",
            {"filename": filename, "hash": file_hash, "status": "extracted"},
            source="contracts.upload",
            error=str(db_exc),
        )
        return {"status": "error", "filename": filename, "message": f"Database unavailable: {db_exc}"}
    db.refresh(contract)

    audit.log(
        db,
        actor=actor,
        action="upload",
        resource=f"contract:{contract.id}",
        after={
            "filename": filename,
            "hash_prefix": file_hash[:12],
            "size_bytes": len(file_bytes),
        },
    )

    # Extract text
    try:
        raw_text, meta = extract_text(file_bytes, filename)
    except Exception as e:
        contract.status = "extraction_failed"
        db.commit()
        audit.log(
            db,
            actor="agent:extractor",
            action="fail",
            resource=f"contract:{contract.id}",
            after={"error": str(e)},
        )
        return {
            "id": contract.id,
            "status": "extraction_failed",
            "filename": filename,
            "message": f"Could not extract text: {e}",
        }

    contract.raw_text = raw_text
    db.commit()

    # Security gate — BEFORE any LLM call
    lt_available = lt_client.is_available()
    scan_result = security_scan(db, contract.id, raw_text)

    sources_used = {ev["details"].get("source", "offline_detector") for ev in scan_result["events"]}
    security_scan_info = {
        "lt_available": lt_available,
        "lt_used": "lobstertrap" in sources_used or lt_available,
        "layers": sorted(sources_used) if sources_used else (
            ["lobstertrap", "offline_detector"] if lt_available else ["offline_detector"]
        ),
    }

    if not scan_result["clean"]:
        contract.status = "quarantined"
        db.commit()
        audit.log(
            db,
            actor="system",
            action="quarantine",
            resource=f"contract:{contract.id}",
            before={"status": "uploading"},
            after={
                "status": "quarantined",
                "events_detected": len(scan_result["events"]),
                "lt_available": lt_available,
            },
        )
        return {
            "id": contract.id,
            "status": "quarantined",
            "filename": filename,
            "security_events": scan_result["events"],
            "security_scan": security_scan_info,
            "message": "Contract quarantined — pre-LLM security gate detected malicious content.",
        }

    # Segment clauses
    clauses = segment_clauses(raw_text)
    contract.clauses = clauses
    contract.status = "extracted"
    db.commit()

    audit.log(
        db,
        actor="agent:extractor",
        action="extract",
        resource=f"contract:{contract.id}",
        after={"n_clauses": len(clauses), "char_count": len(raw_text)},
    )

    # Launch agent pipeline in background
    background_tasks.add_task(_run_pipeline_background, contract.id)
    logger.info("Contract %d (%s) queued for background processing", contract.id, filename)

    return {
        "id": contract.id,
        "status": "extracted",
        "filename": filename,
        "n_clauses": len(clauses),
        "char_count": len(raw_text),
        "metadata": meta,
        "security_scan": security_scan_info,
    }


@router.post("/upload", response_model=UploadResponse, status_code=202)
async def upload_contract(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    actor: str = Form("user:Procurement Analyst"),
    db: Session = Depends(get_db),
):
    """Upload a single contract PDF or DOCX.

    The endpoint returns in ~4 s after the security gate passes.
    The AI agent pipeline (Agents 1-3 + 5) runs asynchronously in the
    background.  Poll GET /contracts/{id} until status leaves 'extracted'.

    Pipeline (synchronous — all happen before the HTTP response):
      1. Validate extension + size
      2. Upload bytes to GCS + compute SHA-256
      3. Create Contract row (status='uploading')
      4. Extract text
      5. Pre-LLM security gate
      6. If unclean → status='quarantined', return early
      7. Segment clauses
      8. status='extracted'  ← response sent here

    Background (after response):
      9. Agents 1 (extraction) → 2 (risk) → 3 (compliance) → 5 (recommendation)
    """
    suffix = Path(file.filename).suffix.lower()
    if suffix not in {".pdf", ".docx"}:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {suffix}. Use PDF or DOCX.",
        )

    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Empty file")
    if len(file_bytes) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File too large: {len(file_bytes):,} bytes. Maximum allowed is {MAX_UPLOAD_BYTES:,} bytes (50 MB).",
        )

    result = _process_single_upload(file_bytes, file.filename, actor, db, background_tasks)

    # Map soft-error statuses back to HTTP errors for single-file callers
    if result.get("status") == "error":
        raise HTTPException(status_code=422, detail=result["message"])

    return result


@router.post("/bulk-upload", response_model=BulkUploadResponse, status_code=202)
async def bulk_upload_contracts(
    background_tasks: BackgroundTasks,
    files: list[UploadFile] = File(...),
    actor: str = Form("user:Procurement Analyst"),
    db: Session = Depends(get_db),
):
    """Upload multiple contract files in a single request.

    Processes each file through the full single-upload pipeline
    (dedup check → GCS → security gate → clause segmentation → background agents).

    One file failing does NOT abort the rest — each result is independent.

    Returns:
        {
          "total":       int,
          "queued":      int,   # files that passed security gate and are now processing
          "duplicates":  int,
          "quarantined": int,
          "errors":      int,
          "results":     [per-file result dicts, same shape as /upload response]
        }
    """
    if not files:
        raise HTTPException(status_code=400, detail="No files provided")

    MAX_BULK = 20
    if len(files) > MAX_BULK:
        raise HTTPException(
            status_code=400,
            detail=f"Bulk upload limit is {MAX_BULK} files per request. Got {len(files)}.",
        )

    logger.info(
        "Bulk upload started — %d files from actor '%s'", len(files), actor
    )

    results = []
    counts = {"queued": 0, "duplicates": 0, "quarantined": 0, "errors": 0}

    for file in files:
        try:
            file_bytes = await file.read()
            result = _process_single_upload(
                file_bytes, file.filename, actor, db, background_tasks
            )
        except Exception as exc:
            logger.exception("Bulk upload: unexpected error for file %s", file.filename)
            result = {
                "status": "error",
                "filename": file.filename,
                "message": str(exc),
            }

        results.append(result)

        status = result.get("status", "error")
        if status == "extracted":
            counts["queued"] += 1
        elif status == "duplicate":
            counts["duplicates"] += 1
        elif status == "quarantined":
            counts["quarantined"] += 1
        else:
            counts["errors"] += 1

    logger.info(
        "Bulk upload complete — total=%d queued=%d duplicates=%d quarantined=%d errors=%d",
        len(files), counts["queued"], counts["duplicates"],
        counts["quarantined"], counts["errors"],
    )

    return {
        "total":       len(files),
        "queued":      counts["queued"],
        "duplicates":  counts["duplicates"],
        "quarantined": counts["quarantined"],
        "errors":      counts["errors"],
        "results":     results,
    }
