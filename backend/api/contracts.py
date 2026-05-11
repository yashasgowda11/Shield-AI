"""Contract upload + processing endpoints.
"""
import hashlib
import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session

from datetime import datetime

from backend.db import get_db
from backend.models import AgentOutput, AuditLog, Contract, Decision
from backend import audit
from backend.extractors import extract_text
from backend.segmentation import segment_clauses
from backend.agents.security import scan as security_scan
from backend.orchestrator import run_pipeline

logger = logging.getLogger(__name__)


router = APIRouter()

# Where uploaded files live on disk. Filename is the SHA-256 hash + original suffix.
UPLOAD_DIR = Path(__file__).resolve().parents[1] / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)


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


@router.post("/{contract_id}/process")
def process_contract(contract_id: int, db: Session = Depends(get_db)):
    """Manually re-run the agent pipeline. Useful when iterating on prompts
    or recovering from a partial failure."""
    return run_pipeline(db, contract_id)


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
    file: UploadFile = File(...),
    actor: str = Form("user:Procurement Analyst"),
    db: Session = Depends(get_db),
):
    """Upload a contract PDF or DOCX.

    Pipeline (in strict order — security gate is BEFORE extraction outputs
    are returned to the user, and BEFORE any agent runs):
      1. Validate extension
      2. Persist bytes + compute SHA-256
      3. Create Contract row (status='uploading')
      4. Extract text
      5. Pre-LLM security gate
      6. If unclean → status='quarantined', return early
      7. Segment clauses
      8. status='extracted'
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

    # Persist file to disk
    stored_path = UPLOAD_DIR / f"{file_hash}{suffix}"
    stored_path.write_bytes(file_bytes)

    # Create row
    contract = Contract(
        filename=file.filename,
        status="uploading",
        file_hash=file_hash,
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

    # Run agent pipeline synchronously. Failures here don't fail the upload —
    # the contract is still in 'extracted' state and can be re-processed via
    # POST /contracts/{id}/process.
    pipeline_result: dict | None = None
    try:
        pipeline_result = run_pipeline(db, contract.id)
    except Exception as e:
        logger.exception("Agent pipeline crashed; upload still succeeded")
        pipeline_result = {"error": str(e)}

    return {
        "id": contract.id,
        "status": contract.status,
        "filename": file.filename,
        "n_clauses": len(clauses),
        "char_count": len(raw_text),
        "metadata": meta,
        "pipeline": pipeline_result,
    }
