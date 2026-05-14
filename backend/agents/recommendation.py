"""Agent 5 — Approval Recommendation.

Decision engine type: POLICY_BASED — deterministic, no LLM call.
The recommendation is produced by the hybrid scoring engine in scoring.py
which combines a weighted composite score with hard override rules.

Priority order: REJECT > LEGAL_REVIEW > MANAGER_REVIEW > AUTO_APPROVE

The active scoring policy is loaded from the scoring_policies table so
admins can adjust thresholds and weights from the UI without a code deploy.
"""
import logging

from sqlalchemy.orm import Session

from backend import audit
from backend.agents import history as agent_history
from backend.agents import scoring as scoring_engine
from backend.models import AgentOutput, Contract, Decision, SecurityEvent

logger = logging.getLogger(__name__)

AGENT_NAME = "recommendation"

# Maps engine decision codes → contract status strings
_DECISION_TO_STATUS = {
    "AUTO_APPROVE":   "approved",
    "MANAGER_REVIEW": "manager_review",
    "LEGAL_REVIEW":   "legal_review",
    "REJECT":         "rejected",
}


def _latest_output(db: Session, contract_id: int, agent_name: str) -> dict | None:
    row = (
        db.query(AgentOutput)
        .filter_by(contract_id=contract_id, agent_name=agent_name)
        .order_by(AgentOutput.created_at.desc())
        .first()
    )
    return row.output if row else None


def _get_security_events(db: Session, contract_id: int) -> list[dict]:
    rows = db.query(SecurityEvent).filter_by(contract_id=contract_id).all()
    return [{"event_type": r.event_type, "severity": r.severity} for r in rows]


def run(db: Session, contract_id: int) -> Decision:
    """Execute Agent 5 — load upstream outputs, score, persist decision."""

    # ── Read outputs from upstream agents ─────────────────────────────────────
    try:
        risk           = _latest_output(db, contract_id, "risk")
        compliance     = _latest_output(db, contract_id, "compliance")
        extraction     = _latest_output(db, contract_id, "extraction")
        classification = _latest_output(db, contract_id, "classification")
        sec_events     = _get_security_events(db, contract_id)
    except Exception as exc:
        logger.exception(
            "Agent 5 failed to read upstream outputs for contract %s: %s",
            contract_id, exc,
        )
        raise

    if risk is None:
        logger.warning(
            "Agent 5: no risk output for contract %s — risk score defaults to 0",
            contract_id,
        )
    if compliance is None:
        logger.warning(
            "Agent 5: no compliance output for contract %s — skipping framework checks",
            contract_id,
        )
    if classification is None:
        logger.warning(
            "Agent 5: no classification output for contract %s — using default (Other) sector policy",
            contract_id,
        )
    else:
        logger.info(
            "Agent 5: classification loaded — type=%s sector=%s jurisdiction=%s/%s",
            classification.get("contract_type"),
            classification.get("sector"),
            classification.get("jurisdiction_country"),
            classification.get("jurisdiction_us_state"),
        )

    # ── Load active scoring policy (sector-aware) ──────────────────────────────
    sector = (classification or {}).get("sector", "Other")
    policy = scoring_engine.load_policy(db, sector=sector)

    # ── Load feedback context (best-effort) ───────────────────────────────────
    vendor_name = "unknown"
    feedback_ctx: dict = {}
    try:
        if extraction:
            parties = extraction.get("parties") or []
            vendor_name = parties[0].get("name", "unknown") if parties else "unknown"
        feedback_ctx = agent_history.get_feedback_context(db, vendor_name)
    except Exception:
        logger.warning("Agent 5: could not load feedback context (non-fatal)", exc_info=True)

    # ── Run hybrid scoring engine ──────────────────────────────────────────────
    try:
        result = scoring_engine.decide(
            risk=risk,
            compliance=compliance,
            extraction=extraction,
            security_events=sec_events,
            policy=policy,
            classification=classification,   # ← sector/jurisdiction/financial risk gating
        )
    except Exception as exc:
        logger.exception(
            "Agent 5 scoring engine raised for contract %s: %s",
            contract_id, exc,
        )
        raise

    logger.info(
        "Agent 5 scored contract %s — composite=%.1f risk=%d compliance=%.1f "
        "quality=%.1f critical=%d high=%d → %s",
        contract_id, result.composite_score, result.risk_score,
        result.compliance_avg, result.quality_score,
        result.critical_findings, result.high_findings,
        result.decision,
    )

    # ── Persist Decision + update contract status ──────────────────────────────
    try:
        # Append feedback context notes to rationale (non-blocking)
        if feedback_ctx.get("global_suggestion"):
            result.rationale.append(f"ℹ️ Reviewer trend: {feedback_ctx['global_suggestion']}")
        if feedback_ctx.get("vendor_pattern"):
            result.rationale.append(f"ℹ️ {feedback_ctx['vendor_pattern']}")
        if feedback_ctx.get("last_human_override_reason"):
            result.rationale.append(
                f"ℹ️ Prior human override for this vendor — {feedback_ctx['last_human_override_reason']}"
            )

        primary_reasoning = result.rationale[0] if result.rationale else result.decision

        decision = Decision(
            contract_id=contract_id,
            recommendation=result.decision,
            reasoning=primary_reasoning,
            reviewer_role=f"agent:{AGENT_NAME}",
            scoring_details=result.to_dict(),
        )
        db.add(decision)

        contract = db.query(Contract).filter_by(id=contract_id).first()
        if contract is None:
            raise ValueError(f"Contract {contract_id} not found")

        new_status = _DECISION_TO_STATUS.get(result.decision)
        if new_status:
            contract.status = new_status

        db.commit()
        db.refresh(decision)
    except Exception as exc:
        logger.exception(
            "Agent 5 DB persist failed for contract %s: %s",
            contract_id, exc,
        )
        db.rollback()
        raise

    # ── Audit log ──────────────────────────────────────────────────────────────
    try:
        audit.log(
            db,
            actor=f"agent:{AGENT_NAME}",
            action="recommend",
            resource=f"contract:{contract_id}",
            after={
                "decision":            result.decision,
                "composite_score":     result.composite_score,
                "risk_score":          result.risk_score,
                "compliance_avg":      result.compliance_avg,
                "quality_score":       result.quality_score,
                "critical_findings":   result.critical_findings,
                "high_findings":       result.high_findings,
                "triggered_rules":     result.triggered_rules,
                "sector":              result.sector,
                "jurisdiction":        result.jurisdiction,
                "financial_penalties": result.financial_penalties,
                "jurisdiction_penalties": result.jurisdiction_penalties,
                "new_status":          contract.status if contract else None,
            },
        )
    except Exception:
        logger.exception(
            "Agent 5 audit log failed for contract %s (non-fatal)", contract_id
        )

    return decision
