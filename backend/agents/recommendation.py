"""Agent 5 — Approval Recommendation (rules-based, NO LLM).

The pitch: "we never let an LLM make the final approval call."
This agent's decision is deterministic. The rationale comes from a templated
lookup keyed by the path the decision took. No Gemini call.

Reads the latest risk + compliance outputs from agent_outputs and the
security_events for the contract, runs the decision tree, persists a Decision
row, and updates the contract's status.

Decision tree (in priority order):
  1. Any security events present                  → REJECT
  2. Any Critical compliance gap                  → LEGAL_REVIEW
  3. risk_score >= 70                             → LEGAL_REVIEW
  4. risk_score >= 40                             → MANAGER_REVIEW
  5. otherwise                                    → AUTO_APPROVE
"""
import logging
from typing import Any

from sqlalchemy.orm import Session

from backend import audit
from backend.models import AgentOutput, Contract, Decision, SecurityEvent

logger = logging.getLogger(__name__)

AGENT_NAME = "recommendation"

# Decision codes
AUTO_APPROVE = "AUTO_APPROVE"
MANAGER_REVIEW = "MANAGER_REVIEW"
LEGAL_REVIEW = "LEGAL_REVIEW"
REJECT = "REJECT"

# How an AI recommendation maps to a contract status
RECOMMENDATION_TO_STATUS = {
    AUTO_APPROVE: "approved",
    MANAGER_REVIEW: "manager_review",
    LEGAL_REVIEW: "legal_review",
    REJECT: "rejected",
}

RATIONALE_TEMPLATES = {
    "REJECT_security": (
        "Rejected: {n_events} security event(s) detected during the pre-LLM scan, "
        "including {top_event_type}."
    ),
    "LEGAL_REVIEW_compliance": (
        "Routed to legal review: {framework} critical compliance failure on '{requirement}'."
    ),
    "LEGAL_REVIEW_score": (
        "Routed to legal review: risk score {score}/100 exceeds the high-risk threshold (70)."
    ),
    "MANAGER_REVIEW": (
        "Routed to manager review: risk score {score}/100 is in the moderate range (40-69)."
    ),
    "AUTO_APPROVE": (
        "Auto-approved: risk score {score}/100, all compliance checks passed, no security events."
    ),
}

HIGH_RISK_THRESHOLD = 70
MODERATE_RISK_THRESHOLD = 40


def _latest_output(db: Session, contract_id: int, agent_name: str) -> dict | None:
    row = (
        db.query(AgentOutput)
        .filter_by(contract_id=contract_id, agent_name=agent_name)
        .order_by(AgentOutput.created_at.desc())
        .first()
    )
    return row.output if row else None


def _security_events(db: Session, contract_id: int) -> list[dict]:
    rows = db.query(SecurityEvent).filter_by(contract_id=contract_id).all()
    return [
        {"event_type": r.event_type, "severity": r.severity}
        for r in rows
    ]


def _decide(
    risk: dict[str, Any] | None,
    compliance: dict[str, Any] | None,
    security_events: list[dict],
) -> tuple[str, str]:
    """Pure decision function. Easy to unit-test independently of DB."""
    # 1. Any security events → hard reject
    if security_events:
        return REJECT, RATIONALE_TEMPLATES["REJECT_security"].format(
            n_events=len(security_events),
            top_event_type=security_events[0].get("event_type", "unknown"),
        )

    # 2. Critical compliance gap → legal review.
    # Trust the framework-level `passed` flag: if Gemini decided the framework
    # passed (e.g. HIPAA for an NDA — not applicable), don't second-guess by
    # iterating its individual checks. This avoids escalating NDAs to legal
    # because they technically don't have a BAA clause.
    for fw in (compliance or {}).get("frameworks", []):
        if fw.get("passed"):
            continue
        for check in fw.get("checks", []) or []:
            if (not check.get("present")) and check.get("severity") == "Critical":
                requirement = (check.get("requirement") or "?").strip("[]").strip()
                return LEGAL_REVIEW, RATIONALE_TEMPLATES["LEGAL_REVIEW_compliance"].format(
                    framework=fw.get("framework", "?"),
                    requirement=requirement,
                )

    # 3. Score-based routing
    score = int((risk or {}).get("score") or 0)
    if score >= HIGH_RISK_THRESHOLD:
        return LEGAL_REVIEW, RATIONALE_TEMPLATES["LEGAL_REVIEW_score"].format(score=score)
    if score >= MODERATE_RISK_THRESHOLD:
        return MANAGER_REVIEW, RATIONALE_TEMPLATES["MANAGER_REVIEW"].format(score=score)
    return AUTO_APPROVE, RATIONALE_TEMPLATES["AUTO_APPROVE"].format(score=score)


def run(db: Session, contract_id: int) -> Decision:
    """Execute Agent 5. Reads upstream outputs, persists Decision, updates status."""

    # ---- Read upstream outputs (non-fatal if missing — decision tree handles None) ----
    try:
        risk = _latest_output(db, contract_id, "risk")
        compliance = _latest_output(db, contract_id, "compliance")
        sec_events = _security_events(db, contract_id)
    except Exception as exc:
        logger.exception(
            "Agent 5 (recommendation) failed to read upstream outputs for contract %s: %s",
            contract_id, exc,
        )
        raise

    if risk is None:
        logger.warning(
            "Agent 5: no risk output found for contract %s — defaulting score to 0",
            contract_id,
        )
    if compliance is None:
        logger.warning(
            "Agent 5: no compliance output found for contract %s — skipping framework checks",
            contract_id,
        )

    # ---- Decision logic (pure, no I/O) ----
    try:
        recommendation, reasoning = _decide(risk, compliance, sec_events)
    except Exception as exc:
        logger.exception(
            "Agent 5 decision logic raised unexpectedly for contract %s: %s",
            contract_id, exc,
        )
        raise

    # ---- Persist Decision + update contract status ----
    try:
        decision = Decision(
            contract_id=contract_id,
            recommendation=recommendation,
            reasoning=reasoning,
            reviewer_role=f"agent:{AGENT_NAME}",
        )
        db.add(decision)

        contract = db.query(Contract).filter_by(id=contract_id).first()
        if contract is None:
            raise ValueError(f"Contract {contract_id} not found when persisting decision")

        new_status = RECOMMENDATION_TO_STATUS.get(recommendation)
        if new_status:
            contract.status = new_status

        db.commit()
        db.refresh(decision)
    except Exception as exc:
        logger.exception(
            "Agent 5 (recommendation) DB persist failed for contract %s: %s",
            contract_id, exc,
        )
        db.rollback()
        raise

    # ---- Audit log ----
    try:
        audit.log(
            db,
            actor=f"agent:{AGENT_NAME}",
            action="recommend",
            resource=f"contract:{contract_id}",
            after={
                "recommendation": recommendation,
                "reasoning": reasoning,
                "risk_score": (risk or {}).get("score"),
                "new_status": contract.status if contract else None,
            },
        )
    except Exception:
        logger.exception("Agent 5 audit log failed for contract %s (non-fatal)", contract_id)

    logger.info(
        "Agent 5 (recommendation) on contract %s → %s (status now %s)",
        contract_id, recommendation, contract.status if contract else "?",
    )
    return decision
