"""Contract upload + processing endpoints.
"""
import hashlib
import logging
import os
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import Response as FileResponse
from google.cloud import storage as gcs
from google.oauth2 import service_account
from sqlalchemy.orm import Session

from datetime import datetime

from backend.db import get_db, SessionLocal
from backend.models import AgentOutput, AuditLog, Contract, Decision
from backend import audit
from backend.extractors import extract_text
from backend.segmentation import segment_clauses
from backend.agents.security import scan as security_scan
from backend.orchestrator import run_pipeline

logger = logging.getLogger(__name__)

router = APIRouter()


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


@router.get("/")
def list_contracts(
    status: str | None = None,
    db: Session = Depends(get_db),
):
    """List all contracts. Optional status filter (e.g. 'legal_review')."""
    q = db.query(Contract).order_by(Contract.uploaded_at.desc())
    if status:
        q = q.filter(Contract.status == status)
    rows = q.all()
    return [
        {
            "id": r.id,
            "filename": r.filename,
            "status": r.status,
            "uploaded_at": r.uploaded_at.isoformat() if r.uploaded_at else None,
            "n_clauses": len(r.clauses) if r.clauses else 0,
        }
        for r in rows
    ]


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
            "recommendation": d.recommendation,
            "reasoning": d.reasoning,
            "reviewer_role": d.reviewer_role,
            "decided_at": d.decided_at.isoformat() if d.decided_at else None,
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
        "report_generated_at": datetime.utcnow().isoformat() + "Z",
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
                "recommendation": d.recommendation,
                "reasoning": d.reasoning,
                "reviewer_role": d.reviewer_role,
                "decided_at": d.decided_at.isoformat() if d.decided_at else None,
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


@router.post("/{contract_id}/decide")
def make_human_decision(
    contract_id: int,
    decision: str = Form(...),
    reasoning: str = Form(...),
    actor: str = Form(...),
    db: Session = Depends(get_db),
):
    """Record a human approval decision. `decision` is one of
    APPROVED | REJECTED | ESCALATED_LEGAL."""
    if decision not in HUMAN_DECISION_TO_STATUS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid decision: {decision}. Use one of {list(HUMAN_DECISION_TO_STATUS)}",
        )

    contract = db.query(Contract).filter(Contract.id == contract_id).first()
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")

    db.add(Decision(
        contract_id=contract_id,
        recommendation=decision,
        reasoning=reasoning,
        reviewer_role=actor,
    ))

    new_status = HUMAN_DECISION_TO_STATUS[decision]
    before_status = contract.status
    contract.status = new_status
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


@router.post("/upload")
async def upload_contract(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    actor: str = Form("user:Procurement Analyst"),
    db: Session = Depends(get_db),
):
    """Upload a contract PDF or DOCX.

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

    # Read & hash
    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Empty file")
    file_hash = hashlib.sha256(file_bytes).hexdigest()

    # ---- Duplicate detection ----
    # If a contract with this exact SHA-256 already exists, return it immediately
    # without re-processing. The frontend will redirect to the existing report.
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
            after={"filename": file.filename, "hash_prefix": file_hash[:12]},
        )
        return {
            "id": existing.id,
            "status": "duplicate",
            "filename": file.filename,
            "existing_filename": existing.filename,
            "existing_status": existing.status,
            "uploaded_at": existing.uploaded_at.isoformat() if existing.uploaded_at else None,
            "message": (
                f"This file has already been uploaded as '{existing.filename}' "
                f"(contract #{existing.id}) with status '{existing.status}'."
            ),
        }

    # Upload to GCS — blob name is hash + suffix so identical files dedup naturally
    blob_name = f"contracts/{file_hash}{suffix}"
    try:
        gcs_uri = _upload_to_gcs(file_bytes, blob_name)
    except Exception as e:
        logger.exception("GCS upload failed")
        raise HTTPException(status_code=503, detail=f"File storage unavailable: {e}")

    # Create row — store GCS URI instead of local path
    contract = Contract(
        filename=file.filename,
        status="uploading",
        file_hash=file_hash,
        gcs_uri=gcs_uri,
    )
    db.add(contract)
    db.commit()
    db.refresh(contract)

    audit.log(
        db,
        actor=actor,
        action="upload",
        resource=f"contract:{contract.id}",
        after={
            "filename": file.filename,
            "hash_prefix": file_hash[:12],
            "size_bytes": len(file_bytes),
        },
    )

    # Extract text
    try:
        raw_text, meta = extract_text(file_bytes, file.filename)
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
        raise HTTPException(status_code=422, detail=f"Could not extract text: {e}")

    contract.raw_text = raw_text
    db.commit()

    # CRITICAL: security gate runs BEFORE any LLM call.
    scan_result = security_scan(db, contract.id, raw_text)

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
            },
        )
        return {
            "id": contract.id,
            "status": "quarantined",
            "filename": file.filename,
            "security_events": scan_result["events"],
            "message": (
                "Contract quarantined. The pre-LLM security gate detected "
                "malicious or suspicious content."
            ),
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

    # Launch the agent pipeline in the background — response returns here.
    # The pipeline creates its own DB session (see _run_pipeline_background).
    background_tasks.add_task(_run_pipeline_background, contract.id)
    logger.info("Contract %d queued for background processing", contract.id)

    return {
        "id": contract.id,
        "status": "extracted",
        "filename": file.filename,
        "n_clauses": len(clauses),
        "char_count": len(raw_text),
        "metadata": meta,
    }
