"""Tests for Agents 2 (risk) and 3 (compliance).

Both Gemini calls and RAG retrieval are mocked so tests are fast and offline.
"""
from unittest.mock import patch

from backend.agents import compliance, risk
from backend.agents.schemas import (
    ComplianceCheck,
    FrameworkResult,
    RiskAssessment,
    RiskFinding,
    Severity,
)
from backend.db import SessionLocal
from backend.models import AgentOutput, Contract


def _seed_contract(clauses=None) -> int:
    db = SessionLocal()
    c = Contract(
        filename="t.pdf",
        status="extracted",
        file_hash="h",
        raw_text="1.1 Scope. Vendor shall do X. 7.2 Liability. Unlimited.",
        clauses=clauses or [
            {"number": "1.1", "title": "Scope", "text": "Vendor shall do X."},
            {"number": "7.2", "title": "Liability", "text": "Unlimited liability for Customer."},
        ],
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    cid = c.id
    db.close()
    return cid


# ---- Agent 2: Risk ----

def test_risk_persists_output_and_audit():
    fake = RiskAssessment(
        score=82,
        findings=[
            RiskFinding(
                risk="Unlimited liability",
                severity=Severity.CRITICAL,
                clause_ref="7.2",
                reasoning="Customer assumes unbounded liability per clause 7.2.",
            ),
        ],
    )
    fake_similar = [{
        "vendor": "Helix Health",
        "clause_number": "7.2",
        "clause_text": "Unlimited liability for customer...",
        "findings_for_clause": [{"severity": "Critical", "risk": "Unlimited liability"}],
    }]

    cid = _seed_contract()

    with patch.object(risk, "generate_json", return_value=fake), \
         patch.object(risk, "retrieve", return_value=fake_similar):
        result = risk.run(SessionLocal(), cid, [
            {"number": "7.2", "title": "Liability", "text": "Unlimited liability for Customer."},
        ])

    assert result.score == 82
    assert result.findings[0].severity == Severity.CRITICAL
    assert result.findings[0].clause_ref == "7.2"

    db = SessionLocal()
    rows = db.query(AgentOutput).filter_by(contract_id=cid, agent_name="risk").all()
    assert len(rows) == 1
    assert rows[0].output["score"] == 82
    assert rows[0].prompt_hash and rows[0].prompt_hash.startswith("sha256:")
    db.close()


def test_risk_with_no_clauses_returns_zero_score():
    cid = _seed_contract()

    # generate_json should NOT be called when there are no clauses
    with patch.object(risk, "generate_json") as gen_mock:
        result = risk.run(SessionLocal(), cid, [])
        gen_mock.assert_not_called()

    assert result.score == 0
    assert result.findings == []


def test_risk_continues_when_rag_fails():
    """If retrieve() blows up, the agent should still run with empty comparators."""
    fake = RiskAssessment(score=50, findings=[])
    cid = _seed_contract()

    with patch.object(risk, "generate_json", return_value=fake), \
         patch.object(risk, "retrieve", side_effect=RuntimeError("RAG down")):
        result = risk.run(SessionLocal(), cid, [
            {"number": "1.1", "title": "Scope", "text": "..."},
        ])

    assert result.score == 50  # generate_json was still called


# ---- Agent 3: Compliance ----

def test_compliance_calls_gemini_once_per_framework():
    fake_fw = FrameworkResult(
        framework="HIPAA",
        passed=False,
        checks=[
            ComplianceCheck(
                requirement="BAA",
                present=False,
                gap_description="No BAA language found.",
                severity=Severity.CRITICAL,
            ),
        ],
    )
    # Provide snippets for ALL frameworks — agent short-circuits when
    # post-filter returns nothing, so a HIPAA-only mock would skip SOC2 and GDPR.
    fake_snippets = [
        {"framework": "HIPAA", "requirement": "BAA", "severity": "critical",
         "text": "Vendors handling PHI must have a BAA."},
        {"framework": "SOC2", "requirement": "Encryption", "severity": "high",
         "text": "Customer data must be encrypted in transit and at rest."},
        {"framework": "GDPR", "requirement": "DPA", "severity": "critical",
         "text": "Where the vendor processes personal data, a DPA is required."},
    ]

    cid = _seed_contract()

    with patch.object(compliance, "generate_json", return_value=fake_fw) as gen_mock, \
         patch.object(compliance, "retrieve", return_value=fake_snippets):
        result = compliance.run(SessionLocal(), cid, "raw contract text")

    # One call per framework
    assert gen_mock.call_count == len(compliance.FRAMEWORKS)
    assert {f.framework for f in result.frameworks} == set(compliance.FRAMEWORKS)


def test_compliance_filters_snippets_by_framework():
    """The agent should only pass HIPAA snippets to the HIPAA call, etc."""
    # Use distinctive requirement names that won't accidentally match other text.
    mixed_snippets = [
        {"framework": "HIPAA", "requirement": "REQ_HIPAA_BAA", "severity": "high", "text": "..."},
        {"framework": "GDPR", "requirement": "REQ_GDPR_DPA", "severity": "high", "text": "..."},
        {"framework": "SOC2", "requirement": "REQ_SOC2_ENC", "severity": "high", "text": "..."},
    ]
    fake_fw = FrameworkResult(framework="X", passed=True, checks=[])
    cid = _seed_contract()

    seen_prompts: list[str] = []

    def capture(prompt, schema, **kwargs):
        seen_prompts.append(prompt)
        return fake_fw

    with patch.object(compliance, "generate_json", side_effect=capture), \
         patch.object(compliance, "retrieve", return_value=mixed_snippets):
        compliance.run(SessionLocal(), cid, "raw text")

    # Each framework's requirement should appear in exactly one prompt.
    for marker in ["REQ_HIPAA_BAA", "REQ_GDPR_DPA", "REQ_SOC2_ENC"]:
        count = sum(1 for p in seen_prompts if marker in p)
        assert count == 1, f"{marker} should appear in exactly 1 prompt, got {count}"


def test_compliance_persists_aggregate_result():
    fake_fw = FrameworkResult(framework="X", passed=True, checks=[])
    cid = _seed_contract()

    with patch.object(compliance, "generate_json", return_value=fake_fw), \
         patch.object(compliance, "retrieve", return_value=[
             {"framework": "HIPAA", "requirement": "Q", "severity": "low", "text": "..."},
         ]):
        compliance.run(SessionLocal(), cid, "raw")

    db = SessionLocal()
    rows = db.query(AgentOutput).filter_by(contract_id=cid, agent_name="compliance").all()
    assert len(rows) == 1
    assert "frameworks" in rows[0].output
    assert len(rows[0].output["frameworks"]) == 3
    db.close()


# ---- Orchestrator: all three agents ----

def test_orchestrator_runs_all_four_agents():
    from backend import orchestrator
    from backend.agents import extraction
    from backend.agents.schemas import ExtractionResult, Party, PartyRole

    fake_ext = ExtractionResult(
        parties=[Party(name="X", role=PartyRole.OTHER)],
        obligations=[],
        summary="test",
    )
    fake_risk = RiskAssessment(score=10, findings=[])
    fake_comp = FrameworkResult(framework="X", passed=True, checks=[])
    fake_snippets = [{"framework": "HIPAA", "requirement": "Q", "severity": "low", "text": "..."}]

    cid = _seed_contract()

    with patch.object(extraction, "generate_json", return_value=fake_ext), \
         patch.object(risk, "generate_json", return_value=fake_risk), \
         patch.object(risk, "retrieve", return_value=[]), \
         patch.object(compliance, "generate_json", return_value=fake_comp), \
         patch.object(compliance, "retrieve", return_value=fake_snippets):
        out = orchestrator.run_pipeline(SessionLocal(), cid)

    assert set(out["ran"]) == {"extraction", "risk", "compliance", "recommendation"}
    assert out["errors"] == {}
    # Risk score 10 → Agent 5 routes to AUTO_APPROVE → status "approved"
    assert out["final_status"] == "approved"


def test_orchestrator_partial_failure_doesnt_break_chain():
    """If risk crashes, extraction + compliance still run."""
    from backend import orchestrator
    from backend.agents import extraction
    from backend.agents.schemas import ExtractionResult, Party, PartyRole

    fake_ext = ExtractionResult(
        parties=[Party(name="X", role=PartyRole.OTHER)],
        obligations=[],
        summary="test",
    )
    fake_comp = FrameworkResult(framework="X", passed=True, checks=[])

    cid = _seed_contract()

    with patch.object(extraction, "generate_json", return_value=fake_ext), \
         patch.object(risk, "generate_json", side_effect=RuntimeError("risk crashed")), \
         patch.object(risk, "retrieve", return_value=[]), \
         patch.object(compliance, "generate_json", return_value=fake_comp), \
         patch.object(compliance, "retrieve", return_value=[
             {"framework": "HIPAA", "requirement": "Q", "severity": "low", "text": "..."},
         ]):
        out = orchestrator.run_pipeline(SessionLocal(), cid)

    assert "extraction" in out["ran"]
    assert "compliance" in out["ran"]
    assert "risk" in out["errors"]
    assert "risk crashed" in out["errors"]["risk"]
