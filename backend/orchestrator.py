"""Agent pipeline runner.

Single entry point — `run_pipeline(db, contract_id)` — that runs every
agent that exists on a contract in `extracted` status.

Error handling strategy:
  - Each agent is run inside its own try/except so one failure does not
    abort downstream agents that might still succeed.
  - If ALL agents fail (errors == ran is empty), contract status is set to
    'pipeline_failed' so the Review Queue can surface it.
  - Individual agent failures are logged at ERROR level with the full
    traceback; non-fatal orchestrator bookkeeping failures at WARNING.
"""
import logging
import time
from typing import Any, Callable

from sqlalchemy.orm import Session

from backend import audit
from backend.agents import compliance as compliance_agent
from backend.agents import extraction as extraction_agent
from backend.agents import recommendation as recommendation_agent
from backend.agents import risk as risk_agent
from backend.models import AgentOutput, Contract

logger = logging.getLogger(__name__)


def _index_contract_to_rag(db: Session, contract: Contract) -> int:
    """Index a processed contract's clauses into the Pinecone contracts namespace.

    Extracts vendor name from Agent 1's output and risk findings from Agent 2's
    output, then calls upsert_contract_clauses so future uploads can use this
    contract as a RAG comparator.

    This is intentionally a best-effort operation — failures are logged but do
    not affect the contract's final status.

    Returns:
        Number of vectors upserted (0 on failure or nothing to index).
    """
    from backend.rag.ingest import upsert_contract_clauses

    clauses = contract.clauses or []
    if not clauses:
        logger.warning("_index_contract_to_rag: no clauses on contract %s", contract.id)
        return 0

    # ---- Vendor name from Agent 1 (extraction) ----
    vendor = "unknown"
    extraction_row = (
        db.query(AgentOutput)
        .filter_by(contract_id=contract.id, agent_name="extraction")
        .order_by(AgentOutput.created_at.desc())
        .first()
    )
    if extraction_row and extraction_row.output:
        parties = extraction_row.output.get("parties") or []
        if parties:
            vendor = parties[0].get("name") or "unknown"

    # ---- Risk findings + score from Agent 2 (risk) ----
    risk_findings: list[dict] = []
    risk_score: int | None = None
    risk_row = (
        db.query(AgentOutput)
        .filter_by(contract_id=contract.id, agent_name="risk")
        .order_by(AgentOutput.created_at.desc())
        .first()
    )
    if risk_row and risk_row.output:
        risk_findings = risk_row.output.get("findings") or []
        raw_score = risk_row.output.get("score")
        if raw_score is not None:
            try:
                risk_score = int(raw_score)
            except (TypeError, ValueError):
                pass

    logger.info(
        "Indexing contract %s into Pinecone RAG — vendor='%s' clauses=%d risk_score=%s",
        contract.id, vendor, len(clauses), risk_score,
    )

    return upsert_contract_clauses(
        contract_id=contract.id,
        vendor=vendor,
        clauses=clauses,
        risk_findings=risk_findings,
        approval_outcome=contract.status,
        risk_score=risk_score,
    )


def run_pipeline(db: Session, contract_id: int) -> dict[str, Any]:
    """Run all available agents on a contract. Idempotent.

    Returns a summary:
        {
          "contract_id": int,
          "ran": ["extraction", "risk", "compliance", "recommendation"],
          "errors": {"agent_name": "error message", ...},
          "durations_ms": {"agent_name": float, ...},
          "final_status": str,
        }
    """
    contract = db.query(Contract).filter_by(id=contract_id).first()
    if not contract:
        raise ValueError(f"Contract {contract_id} not found")

    # Allow re-runs from any state earlier than human decision.
    valid_starting_statuses = {
        "extracted", "processed", "pipeline_failed",
        "manager_review", "legal_review", "approved", "rejected",
    }
    if contract.status not in valid_starting_statuses:
        logger.info(
            "run_pipeline skipping contract %s — status '%s' not in valid starting statuses",
            contract_id, contract.status,
        )
        return {
            "contract_id": contract_id,
            "skipped": True,
            "reason": f"status is '{contract.status}'",
        }

    logger.info("run_pipeline starting for contract %s (status=%s)", contract_id, contract.status)

    ran: list[str] = []
    errors: dict[str, str] = {}
    durations_ms: dict[str, float] = {}

    # Pipeline ordering matters: Agent 5 reads outputs from Agents 1-3.
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
        t0 = time.perf_counter()
        try:
            fn()
            elapsed = (time.perf_counter() - t0) * 1000
            durations_ms[name] = round(elapsed, 1)
            ran.append(name)
            logger.info("Agent '%s' completed in %.0f ms (contract %s)", name, elapsed, contract_id)
        except Exception as exc:
            elapsed = (time.perf_counter() - t0) * 1000
            durations_ms[name] = round(elapsed, 1)
            errors[name] = str(exc)
            logger.exception(
                "Agent '%s' FAILED after %.0f ms for contract %s: %s",
                name, elapsed, contract_id, exc,
            )

    # ---- Update contract status ----
    try:
        if not ran:
            # Every agent failed — mark explicitly so the queue can surface it
            contract.status = "pipeline_failed"
            logger.error(
                "All agents failed for contract %s — status set to 'pipeline_failed'",
                contract_id,
            )
        elif "recommendation" not in ran:
            # Partial success — at least something ran but Agent 5 didn't
            contract.status = "processed"
            logger.warning(
                "Agent 'recommendation' did not run for contract %s — status set to 'processed'",
                contract_id,
            )
        # else: Agent 5 already set the status (approved / manager_review / etc.)

        db.commit()
    except Exception as exc:
        logger.exception(
            "run_pipeline failed to commit final status for contract %s: %s",
            contract_id, exc,
        )
        db.rollback()

    # ---- Index into Pinecone RAG (best-effort, non-fatal) ----
    # Run after the status commit so the approval_outcome stored in Pinecone
    # metadata reflects the AI recommendation (approved / manager_review / etc.).
    rag_vectors = 0
    if ran:  # at least one agent succeeded — worth indexing
        try:
            rag_vectors = _index_contract_to_rag(db, contract)
        except Exception:
            logger.exception(
                "RAG indexing failed for contract %s (non-fatal — pipeline result unaffected)",
                contract_id,
            )

    # ---- Audit log ----
    try:
        audit.log(
            db,
            actor="system",
            action="process",
            resource=f"contract:{contract_id}",
            after={
                "agents_ran": ran,
                "agents_failed": list(errors.keys()) or None,
                "durations_ms": durations_ms,
                "final_status": contract.status,
                "rag_vectors_indexed": rag_vectors,
            },
        )
    except Exception:
        logger.exception(
            "run_pipeline audit log failed for contract %s (non-fatal)", contract_id,
        )

    logger.info(
        "run_pipeline finished for contract %s — ran=%s errors=%s status=%s rag_vectors=%d",
        contract_id, ran, list(errors.keys()), contract.status, rag_vectors,
    )

    return {
        "contract_id": contract_id,
        "ran": ran,
        "errors": errors,
        "durations_ms": durations_ms,
        "final_status": contract.status,
        "rag_vectors_indexed": rag_vectors,
    }
