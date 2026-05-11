"""Audit log API.

Filterable, paginated read-only view of every audit_log entry.
This is what the Audit Log page in the frontend renders, and what an
auditor / regulator would download.
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.db import get_db
from backend.models import AuditLog

router = APIRouter()


@router.get("/")
def list_audit_logs(
    actor: str | None = Query(None, description="Substring match on actor"),
    action: str | None = Query(None, description="Substring match on action"),
    contract_id: int | None = Query(None, description="Filter to a specific contract"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """Return audit log entries newest first, with optional filters."""
    q = db.query(AuditLog).order_by(AuditLog.timestamp.desc())
    if actor:
        q = q.filter(AuditLog.actor.like(f"%{actor}%"))
    if action:
        q = q.filter(AuditLog.action.like(f"%{action}%"))
    if contract_id is not None:
        q = q.filter(AuditLog.resource == f"contract:{contract_id}")

    total = q.count()
    rows = q.offset(offset).limit(limit).all()

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": [
            {
                "id": r.id,
                "actor": r.actor,
                "action": r.action,
                "resource": r.resource,
                "before": r.before,
                "after": r.after,
                "timestamp": r.timestamp.isoformat() if r.timestamp else None,
            }
            for r in rows
        ],
    }
