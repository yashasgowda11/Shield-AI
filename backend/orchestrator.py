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
from backend.agents import classifier as classifier_agent
from backend.agents import compliance as compliance_agent
from backend.agents import extraction as extraction_agent
from backend.agents import recommendation as recommendation_agent
from backend.agents import risk as risk_agent
from backend.agents.schemas import ClassificationResult
from backend.models import AgentOutput, Contract, ContractAssignment, ContractComment

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


def _auto_assign_multi_review(db: Session, contract_id: int) -> list[str]:
    """After the recommendation agent runs, check whether the contract should be
    assigned to multiple roles simultaneously.

    Rules:
      LEGAL_REVIEW + any compliance framework failed
        → also assign Compliance Officer (advisory, can_approve=False)

      MANAGER_REVIEW + any Critical risk finding
        → also assign Legal Reviewer (advisory, can_approve=False)

    Returns list of roles auto-assigned (empty if none).
    """
    assigned: list[str] = []
    try:
        # Read the recommendation decision
        rec_row = (
            db.query(AgentOutput)
            .filter_by(contract_id=contract_id, agent_name="recommendation")
            .order_by(AgentOutput.created_at.desc())
            .first()
        )
        # Recommendation is stored in the decisions table, not agent_outputs
        from backend.models import Decision
        ai_decision_row = (
            db.query(Decision)
            .filter_by(contract_id=contract_id)
            .filter(Decision.reviewer_role.like("agent:%"))
            .order_by(Decision.id.desc())
            .first()
        )
        if not ai_decision_row:
            return assigned

        decision_code = ai_decision_row.recommendation

        # Read compliance output
        comp_row = (
            db.query(AgentOutput)
            .filter_by(contract_id=contract_id, agent_name="compliance")
            .order_by(AgentOutput.created_at.desc())
            .first()
        )
        compliance_failed = False
        if comp_row and comp_row.output:
            for fw in (comp_row.output.get("frameworks") or []):
                if not fw.get("passed"):
                    compliance_failed = True
                    break

        # Read risk output
        risk_row = (
            db.query(AgentOutput)
            .filter_by(contract_id=contract_id, agent_name="risk")
            .order_by(AgentOutput.created_at.desc())
            .first()
        )
        has_critical = False
        if risk_row and risk_row.output:
            for f in (risk_row.output.get("findings") or []):
                if f.get("severity") == "Critical":
                    has_critical = True
                    break

        def _add_assignment(role: str, note: str) -> None:
            existing = (
                db.query(ContractAssignment)
                .filter_by(contract_id=contract_id, assigned_role=role, active=True)
                .first()
            )
            if not existing:
                db.add(ContractAssignment(
                    contract_id=contract_id,
                    assigned_role=role,
                    assigned_by="system:orchestrator",
                    can_approve=False,
                    note=note,
                ))
                db.add(ContractComment(
                    contract_id=contract_id,
                    actor="system:orchestrator",
                    role="system",
                    comment=f"Auto-assigned to **{role}** for advisory review. {note}",
                    comment_type="escalation",
                ))
                assigned.append(role)

        if decision_code == "LEGAL_REVIEW" and compliance_failed:
            _add_assignment(
                "Compliance Officer",
                "AI recommended Legal Review and compliance frameworks failed — "
                "Compliance Officer assigned for advisory review.",
            )

        if decision_code == "MANAGER_REVIEW" and has_critical:
            _add_assignment(
                "Legal Reviewer",
                "AI recommended Manager Review but Critical risk findings detected — "
                "Legal Reviewer assigned for advisory review.",
            )

        if assigned:
            db.commit()
            logger.info(
                "Auto-assigned contract %s to additional roles: %s",
                contract_id, assigned,
            )

    except Exception:
        logger.exception(
            "Auto-assign multi-review failed for contract %s (non-fatal)",
            contract_id,
        )
        db.rollback()

    return assigned


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

    # ── Agent 0: Classify first — its result gates which frameworks Agent 3 checks ──
    # Run outside the main pipeline loop so we can capture the result and pass
    # it to the compliance agent. Falls back gracefully — never raises.
    classification: ClassificationResult | None = None
    t0_cls = time.perf_counter()
    try:
        classification = classifier_agent.run(db, contract_id, contract.raw_text)
        elapsed_cls = (time.perf_counter() - t0_cls) * 1000
        durations_ms["classification"] = round(elapsed_cls, 1)
        ran.append("classification")
        logger.info(
            "Agent 'classification' completed in %.0f ms — type=%s sector=%s "
            "hipaa=%s gdpr=%s soc2=%s pci=%s ccpa=%s ferpa=%s cmmc=%s",
            elapsed_cls,
            classification.contract_type,
            classification.sector,
            classification.hipaa_applicable,
            classification.gdpr_applicable,
            classification.soc2_applicable,
            classification.pci_applicable,
            classification.ccpa_applicable,
            classification.ferpa_applicable,
            classification.cmmc_applicable,
        )
    except Exception as exc:
        elapsed_cls = (time.perf_counter() - t0_cls) * 1000
        durations_ms["classification"] = round(elapsed_cls, 1)
        errors["classification"] = str(exc)
        logger.exception(
            "Agent 'classification' FAILED after %.0f ms for contract %s: %s",
            elapsed_cls, contract_id, exc,
        )

    # Pipeline ordering matters: Agent 5 reads outputs from Agents 0-3.
    pipeline: list[tuple[str, Callable[[], Any]]] = [
        ("extraction", lambda: extraction_agent.run(
            db, contract_id, contract.raw_text, contract.clauses or [],
        )),
        ("risk", lambda: risk_agent.run(
            db, contract_id, contract.clauses or [],
        )),
        ("compliance", lambda: compliance_agent.run(
            db, contract_id, contract.raw_text,
            classification=classification,   # ← gates which frameworks run
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
        from backend import cache as shield_cache
        shield_cache.write(
            "pipeline_status_update",
            {
                "contract_id": contract_id,
                "attempted_status": contract.status,
                "ran": ran,
                "errors": errors,
            },
            source="orchestrator.run_pipeline",
            error=str(exc),
        )

    # ---- Auto-assign to multiple roles if warranted (best-effort) ----
    auto_assigned: list[str] = []
    if "recommendation" in ran:
        auto_assigned = _auto_assign_multi_review(db, contract_id)

    # ---- Index into Pinecone RAG (best-effort, non-fatal) ----
    # Run after the status commit so the approval_outcome stored in Pinecone
    # metadata reflects the AI recommendation (approved / manager_review / etc.).
    rag_vectors = 0
    if ran:  # at least one agent succeeded — worth indexing
        try:
            rag_vectors = _index_contract_to_rag(db, contract)
        except Exception as exc:
            logger.exception(
                "RAG indexing failed for contract %s (non-fatal — pipeline result unaffected)",
                contract_id,
            )
            from backend import cache as shield_cache
            shield_cache.write(
                "pinecone_index",
                {
                    "contract_id": contract.id,
                    "vendor": "unknown",
                    "n_clauses": len(contract.clauses or []),
                    "risk_score": None,
                },
                source="orchestrator._index_contract_to_rag",
                error=str(exc),
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
                "auto_assigned_roles": auto_assigned or None,
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
