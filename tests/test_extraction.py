"""Tests for Agent 1 (extraction).

LLM calls are mocked so tests are fast, deterministic, and don't burn API quota.
"""
from unittest.mock import patch

from backend.agents import extraction
from backend.agents.schemas import (
    ExtractionResult,
    Obligation,
    Party,
    PartyRole,
)
from backend.db import SessionLocal
from backend.models import AgentOutput, Contract


def _seed_contract() -> int:
    db = SessionLocal()
    c = Contract(
        filename="t.pdf",
        status="extracted",
        file_hash="testhash",
        raw_text="1.1 Scope. Vendor shall do X.",
        clauses=[{"number": "1.1", "title": "Scope", "text": "Vendor shall do X."}],
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    cid = c.id
    db.close()
    return cid


def test_extraction_persists_output_and_audit_log():
    fake = ExtractionResult(
        parties=[
            Party(name="Acme Holdings", role=PartyRole.CUSTOMER),
            Party(name="DataSync Inc.", role=PartyRole.VENDOR),
        ],
        effective_date="2024-01-15",
        term="2 years from Effective Date",
        payment_terms="Net 30",
        governing_law="State of Delaware",
        obligations=[
            Obligation(party="DataSync Inc.", description="Provide SaaS services",
                       clause_ref="1.1"),
        ],
        summary="A 2-year SaaS agreement between Acme and DataSync, governed by Delaware law.",
    )

    cid = _seed_contract()

    with patch.object(extraction, "generate_json", return_value=fake):
        result = extraction.run(SessionLocal(), cid, "raw text", [])

    assert result.parties[0].name == "Acme Holdings"
    assert result.payment_terms == "Net 30"

    # Persisted to agent_outputs?
    db = SessionLocal()
    rows = (
        db.query(AgentOutput)
        .filter_by(contract_id=cid, agent_name="extraction")
        .all()
    )
    assert len(rows) == 1
    persisted = rows[0]
    assert persisted.output["parties"][0]["name"] == "Acme Holdings"
    assert persisted.output["payment_terms"] == "Net 30"
    assert persisted.prompt_hash and persisted.prompt_hash.startswith("sha256:")
    db.close()


def test_extraction_handles_minimal_contract():
    """NDAs typically have no payment terms or obligations beyond confidentiality."""
    fake = ExtractionResult(
        parties=[
            Party(name="Party A", role=PartyRole.DISCLOSER),
            Party(name="Party B", role=PartyRole.RECIPIENT),
        ],
        effective_date=None,
        term="2 years",
        payment_terms=None,
        governing_law="Delaware",
        obligations=[],
        summary="Mutual NDA between Party A and Party B.",
    )

    cid = _seed_contract()
    with patch.object(extraction, "generate_json", return_value=fake):
        result = extraction.run(SessionLocal(), cid, "raw text", [])

    assert result.payment_terms is None
    assert result.obligations == []


def test_orchestrator_runs_extraction_and_advances_status():
    """End-to-end: orchestrator runs all wired agents and advances status to 'processed'.

    All three agents must be mocked here — the orchestrator runs the full
    chain, and any unmocked agent would hit the real Gemini API."""
    from backend import orchestrator
    from backend.agents import compliance as compliance_agent
    from backend.agents import risk as risk_agent
    from backend.agents.schemas import (
        FrameworkResult,
        RiskAssessment,
    )

    fake_ext = ExtractionResult(
        parties=[Party(name="X", role=PartyRole.OTHER)],
        obligations=[],
        summary="test",
    )
    fake_risk = RiskAssessment(score=0, findings=[])
    fake_comp = FrameworkResult(framework="X", passed=True, checks=[])

    cid = _seed_contract()

    with patch.object(extraction, "generate_json", return_value=fake_ext), \
         patch.object(risk_agent, "generate_json", return_value=fake_risk), \
         patch.object(risk_agent, "retrieve", return_value=[]), \
         patch.object(compliance_agent, "generate_json", return_value=fake_comp), \
         patch.object(compliance_agent, "retrieve", return_value=[
             {"framework": "HIPAA", "requirement": "Q", "severity": "low", "text": "..."},
         ]):
        out = orchestrator.run_pipeline(SessionLocal(), cid)

    assert set(out["ran"]) == {"extraction", "risk", "compliance", "recommendation"}
    # Risk score 0 → Agent 5 routes to AUTO_APPROVE → status "approved"
    assert out["final_status"] == "approved"
    assert out["errors"] == {}


def test_orchestrator_skips_non_extracted_contracts():
    from backend import orchestrator

    db = SessionLocal()
    c = Contract(filename="q.pdf", status="quarantined", file_hash="x")
    db.add(c)
    db.commit()
    db.refresh(c)
    cid = c.id
    db.close()

    out = orchestrator.run_pipeline(SessionLocal(), cid)
    assert out.get("skipped") is True
