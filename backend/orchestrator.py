"""Agent pipeline runner.

Single entry point — `run_pipeline(db, contract_id)` — that runs every
agent that exists on a contract in `extracted` status.
"""
import logging
from typing import Any, Callable

from sqlalchemy.orm import Session

from backend import audit
from backend.agents import compliance as compliance_agent
from backend.agents import extraction as extraction_agent
from backend.agents import recommendation as recommendation_agent
from backend.agents import risk as risk_agent
from backend.models import Contract

logger = logging.getLogger(__name__)


def run_pipeline(db: Session, contract_id: int) -> dict[str, Any]:
    """Run all available agents on a contract. Idempotent.

    Returns a summary:
        {
          "contract_id": int,
          "ran": ["extraction", "risk", "compliance"],
          "errors": {"agent_name": "error message", ...},
          "final_status": str,
        }
    """
    contract = db.query(Contract).filter_by(id=contract_id).first()
    if not contract:
        raise ValueError(f"Contract {contract_id} not found")

    # Allow re-runs from any state earlier than human decision.
    # `processed` and the AI-recommendation statuses (manager_review, legal_review,
    # approved, rejected) are all allowed to be re-processed from scratch.
    valid_starting_statuses = {
        "extracted", "processed",
        "manager_review", "legal_review", "approved", "rejected",
    }
    if contract.status not in valid_starting_statuses:
        return {
            "contract_id": contract_id,
            "skipped": True,
            "reason": f"status is '{contract.status}'",
        }

    ran: list[str] = []
    errors: dict[str, str] = {}

    # Pipeline ordering matters: Agent 5 (recommendation) reads outputs from
    # Agents 2 and 3, so it goes last. Agents 2 and 3 are independent of each
    # other and of Agent 1.
    pipeline: list[tuple[str, Callable[[], Any]]] = [
        ("extraction", lambda: extraction_agent.run(
            db, contract_id, contract.raw_text, contract.clauses or [],
        )),
        ("risk", lambda: risk_agent.run(
            db, contract_id, contract.clauses or [],
        )),
        ("compliance", lambda: compliance_agent.run(
            db, contract_id, contract.raw_text,
        )),
        ("recommendation", lambda: recommendation_agent.run(
            db, contract_id,
        )),
    ]

    for name, fn in pipeline:
        try:
            fn()
            ran.append(name)
        except Exception as e:
            logger.exception("Agent '%s' failed", name)
            errors[name] = str(e)

    # Status is now driven by Agent 5 (or set to 'processed' if the
    # recommendation agent didn't run for some reason).
    if "recommendation" not in ran and ran:
        contract.status = "processed"
        db.commit()

    audit.log(
        db,
        actor="system",
        action="process",
        resource=f"contract:{contract_id}",
        after={"agents_run": ran, "errors": list(errors.keys()) or None},
    )

    return {
        "contract_id": contract_id,
        "ran": ran,
        "errors": errors,
        "final_status": contract.status,
    }
