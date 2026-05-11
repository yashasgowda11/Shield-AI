"""Single source of truth for audit logging.

Every agent action and every human action goes through this module.
If you find yourself writing to AuditLog directly without going through
log(), you're probably bypassing something important — don't.
"""
from typing import Optional, Any
from sqlalchemy.orm import Session
from backend.models import AuditLog


def log(
    db: Session,
    actor: str,
    action: str,
    resource: Optional[str] = None,
    before: Optional[Any] = None,
    after: Optional[Any] = None,
) -> AuditLog:
    """Append an audit log entry. Always commits.

    Args:
        db: SQLAlchemy session.
        actor: who performed the action. Convention:
               - "agent:<name>" for AI agents (e.g. "agent:risk")
               - "user:<role>" for human actions (e.g. "user:Legal Reviewer")
               - "system" for automatic background actions
        action: verb describing what happened
                (e.g. "extract", "approve", "quarantine", "reject").
        resource: identifier of the thing acted on (e.g. "contract:42").
        before: state before the action. Must be JSON-serializable.
        after: state after the action. Must be JSON-serializable.

    Returns:
        The persisted AuditLog row.
    """
    entry = AuditLog(
        actor=actor,
        action=action,
        resource=resource,
        before=before,
        after=after,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry
