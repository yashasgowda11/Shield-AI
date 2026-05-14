"""Scoring policy CRUD endpoints.

GET  /scoring-policy/           — active policy + metadata
PUT  /scoring-policy/           — replace active policy (admin only)
GET  /scoring-policy/history    — all historical versions
GET  /scoring-policy/defaults   — the hardcoded DEFAULT_POLICY constant
"""
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.agents.scoring import DEFAULT_POLICY
from backend.db import get_db
from backend.models import ScoringFeedback, ScoringPolicy

logger = logging.getLogger(__name__)
router = APIRouter()

_ADMIN_ROLES = {"Admin", "Legal Reviewer", "System Administrator"}


# ── Request / response shapes ─────────────────────────────────────────────────

class PolicyUpdateRequest(BaseModel):
    config: dict
    updated_by: str = "admin"


class PolicyResponse(BaseModel):
    id: int
    name: str
    is_active: bool
    config: dict
    updated_by: str | None
    updated_at: str


def _row_to_response(row: ScoringPolicy) -> dict:
    return {
        "id":         row.id,
        "name":       row.name,
        "is_active":  row.is_active,
        "config":     row.config,
        "updated_by": row.updated_by,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/")
def get_active_policy(db: Session = Depends(get_db)):
    """Return the currently active scoring policy."""
    row = (
        db.query(ScoringPolicy)
        .filter_by(is_active=True)
        .order_by(ScoringPolicy.updated_at.desc())
        .first()
    )
    if not row:
        # Return defaults without a DB row (first-run edge case)
        return {
            "id": None,
            "name": "default",
            "is_active": True,
            "config": DEFAULT_POLICY,
            "updated_by": "system",
            "updated_at": None,
        }
    return _row_to_response(row)


@router.put("/")
def update_policy(
    body: PolicyUpdateRequest,
    x_role: str = Header(default=""),
    db: Session = Depends(get_db),
):
    """Replace the active scoring policy.

    Deactivates all existing policies and inserts a new row so the full
    change history is preserved. Requires an admin role header.
    """
    if x_role not in _ADMIN_ROLES:
        raise HTTPException(
            status_code=403,
            detail=f"Role '{x_role}' is not authorised to modify the scoring policy.",
        )

    # Basic config validation — must have weights and thresholds
    cfg = body.config
    if "weights" not in cfg or "thresholds" not in cfg:
        raise HTTPException(
            status_code=422,
            detail="Config must contain 'weights' and 'thresholds' keys.",
        )
    weights = cfg["weights"]
    total_weight = sum(weights.get(k, 0) for k in ("risk", "compliance", "quality"))
    if not (0.99 <= total_weight <= 1.01):
        raise HTTPException(
            status_code=422,
            detail=f"Weights must sum to 1.0 (got {total_weight:.3f}).",
        )

    try:
        # Deactivate all current policies
        db.query(ScoringPolicy).filter_by(is_active=True).update({"is_active": False})

        new_row = ScoringPolicy(
            name="default",
            is_active=True,
            config=cfg,
            updated_by=body.updated_by,
            updated_at=datetime.now(timezone.utc),
        )
        db.add(new_row)
        db.commit()
        db.refresh(new_row)
        logger.info(
            "Scoring policy updated by '%s' — new policy id=%d",
            body.updated_by, new_row.id,
        )
        return _row_to_response(new_row)
    except Exception as exc:
        db.rollback()
        logger.exception("Failed to update scoring policy: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/history")
def get_policy_history(db: Session = Depends(get_db)):
    """Return all historical scoring policy versions, newest first."""
    rows = db.query(ScoringPolicy).order_by(ScoringPolicy.updated_at.desc()).all()
    return [_row_to_response(r) for r in rows]


@router.get("/defaults")
def get_default_policy():
    """Return the hardcoded default policy — useful as a reset reference."""
    return DEFAULT_POLICY


# ── Feedback / reinforcement endpoints ────────────────────────────────────────

class FeedbackRequest(BaseModel):
    contract_id:    int
    decision_id:    int | None = None
    feedback_type:  str          # too_high | too_low | correct
    ai_decision:    str | None = None
    human_decision: str | None = None
    composite_score: float | None = None
    notes:          str | None = None
    reviewer_role:  str = "reviewer"

_VALID_FEEDBACK = {"too_high", "too_low", "correct"}


@router.post("/rescore-all")
def rescore_all_contracts(
    x_role: str = Header(default=""),
    db: Session = Depends(get_db),
):
    """Rescore every contract that has agent outputs using the current policy.

    No LLM calls — reads existing agent_outputs and recomputes composite scores.
    Admin-only. Calls the scoring logic directly (no self-HTTP round-trip).
    Returns a summary of decisions changed.
    """
    if x_role not in _ADMIN_ROLES:
        raise HTTPException(
            status_code=403,
            detail=f"Role '{x_role}' cannot trigger bulk rescoring.",
        )

    from backend.models import AgentOutput, Contract, Decision
    from backend.agents import scoring as scoring_engine
    from backend.agents.recommendation import _latest_output, _get_security_events, _DECISION_TO_STATUS
    from backend import audit

    contract_ids = [
        row[0] for row in db.query(AgentOutput.contract_id).distinct().all()
    ]

    results: dict[str, list] = {"rescored": [], "skipped": [], "errors": []}

    for cid in contract_ids:
        try:
            contract = db.query(Contract).filter_by(id=cid).first()
            if not contract:
                results["skipped"].append({"contract_id": cid, "reason": "not found"})
                continue

            risk       = _latest_output(db, cid, "risk")
            compliance = _latest_output(db, cid, "compliance")
            extraction = _latest_output(db, cid, "extraction")
            sec_events = _get_security_events(db, cid)

            if risk is None and compliance is None:
                results["skipped"].append({"contract_id": cid, "reason": "no agent outputs"})
                continue

            policy = scoring_engine.load_policy(db)
            result = scoring_engine.decide(risk, compliance, extraction, sec_events, policy)

            new_decision_row = Decision(
                contract_id=cid,
                recommendation=result.decision,
                reasoning=result.rationale[0] if result.rationale else result.decision,
                reviewer_role="agent:rescore",
                scoring_details=result.to_dict(),
            )
            db.add(new_decision_row)

            new_status = _DECISION_TO_STATUS.get(result.decision)
            old_status = contract.status
            if new_status:
                contract.status = new_status
            db.commit()

            audit.log(
                db,
                actor="system:rescore-all",
                action="rescore",
                resource=f"contract:{cid}",
                before={"status": old_status},
                after={"decision": result.decision, "composite_score": result.composite_score},
            )

            results["rescored"].append({
                "contract_id":  cid,
                "new_decision": result.decision,
                "composite":    result.composite_score,
                "new_status":   contract.status,
            })
        except Exception as exc:
            db.rollback()
            logger.exception("Bulk rescore failed for contract %s: %s", cid, exc)
            results["errors"].append({"contract_id": cid, "error": str(exc)})

    logger.info(
        "Bulk rescore complete — rescored=%d skipped=%d errors=%d",
        len(results["rescored"]), len(results["skipped"]), len(results["errors"]),
    )
    return results


@router.post("/feedback")
def submit_feedback(body: FeedbackRequest, db: Session = Depends(get_db)):
    """Record a reviewer's judgment on an AI scoring decision."""
    if body.feedback_type not in _VALID_FEEDBACK:
        raise HTTPException(
            status_code=422,
            detail=f"feedback_type must be one of {_VALID_FEEDBACK}",
        )
    row = ScoringFeedback(
        contract_id=body.contract_id,
        decision_id=body.decision_id,
        feedback_type=body.feedback_type,
        ai_decision=body.ai_decision,
        human_decision=body.human_decision,
        composite_score=body.composite_score,
        notes=body.notes,
        reviewer_role=body.reviewer_role,
    )
    db.add(row)
    db.commit()
    logger.info(
        "Scoring feedback recorded — contract=%s type=%s by=%s",
        body.contract_id, body.feedback_type, body.reviewer_role,
    )
    return {"status": "recorded", "id": row.id}


@router.get("/feedback/summary")
def feedback_summary(db: Session = Depends(get_db)):
    """Aggregate feedback stats for the Scoring Policy drift analysis panel."""
    rows = db.query(ScoringFeedback).all()
    if not rows:
        return {"total": 0, "breakdown": {}, "by_ai_decision": {}, "avg_composite": None}

    total = len(rows)
    breakdown: dict[str, int] = {}
    by_decision: dict[str, dict[str, int]] = {}
    composites: list[float] = []

    for r in rows:
        breakdown[r.feedback_type] = breakdown.get(r.feedback_type, 0) + 1
        if r.ai_decision:
            bd = by_decision.setdefault(r.ai_decision, {})
            bd[r.feedback_type] = bd.get(r.feedback_type, 0) + 1
        if r.composite_score is not None:
            composites.append(r.composite_score)

    avg_composite = round(sum(composites) / len(composites), 1) if composites else None

    # Simple reinforcement suggestion based on majority feedback
    suggestion = None
    too_high = breakdown.get("too_high", 0)
    too_low  = breakdown.get("too_low",  0)
    if total >= 5:
        if too_high / total > 0.5:
            suggestion = "More than 50% of feedback says scores are too high — consider raising composite thresholds or increasing compliance/quality weights."
        elif too_low / total > 0.5:
            suggestion = "More than 50% of feedback says scores are too low — consider lowering composite thresholds or increasing the risk weight."

    return {
        "total":          total,
        "breakdown":      breakdown,
        "by_ai_decision": by_decision,
        "avg_composite":  avg_composite,
        "suggestion":     suggestion,
    }


@router.get("/feedback/recent")
def recent_feedback(limit: int = 20, db: Session = Depends(get_db)):
    """Return most recent feedback entries."""
    rows = (
        db.query(ScoringFeedback)
        .order_by(ScoringFeedback.created_at.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id":             r.id,
            "contract_id":    r.contract_id,
            "feedback_type":  r.feedback_type,
            "ai_decision":    r.ai_decision,
            "human_decision": r.human_decision,
            "composite_score": r.composite_score,
            "notes":          r.notes,
            "reviewer_role":  r.reviewer_role,
            "created_at":     r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]
