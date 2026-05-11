"""Tests for Agent 5 (recommendation) and the human-decision flow."""
import json
from unittest.mock import patch

from backend.agents import compliance as compliance_agent
from backend.agents import extraction as extraction_agent
from backend.agents import recommendation
from backend.agents import risk as risk_agent
from backend.agents.schemas import (
    ComplianceCheck,
    ExtractionResult,
    FrameworkResult,
    Party,
    PartyRole,
    RiskAssessment,
    RiskFinding,
    Severity,
)
from backend.db import SessionLocal
from backend.models import (
    AgentOutput,
    Contract,
    Decision,
    SecurityEvent,
)


def _seed_with_outputs(
    risk_score: int = 0,
    findings: list | None = None,
    compliance_frameworks: list | None = None,
    security_events: list | None = None,
) -> int:
    """Seed a contract + agent_outputs + security_events to drive Agent 5."""
    db = SessionLocal()
    c = Contract(filename="t.pdf", status="processed", file_hash="h",
                 raw_text="text", clauses=[])
    db.add(c)
    db.commit()
    db.refresh(c)

    if risk_score is not None:
        risk_obj = RiskAssessment(score=risk_score, findings=findings or [])
        db.add(AgentOutput(
            contract_id=c.id,
            agent_name="risk",
            output=json.loads(risk_obj.model_dump_json()),
        ))
    if compliance_frameworks is not None:
        from backend.agents.schemas import ComplianceResult
        comp_obj = ComplianceResult(frameworks=compliance_frameworks)
        db.add(AgentOutput(
            contract_id=c.id,
            agent_name="compliance",
            output=json.loads(comp_obj.model_dump_json()),
        ))
    for ev in security_events or []:
        db.add(SecurityEvent(
            contract_id=c.id,
            event_type=ev["event_type"],
            severity=ev["severity"],
            details={},
        ))
    db.commit()
    cid = c.id
    db.close()
    return cid


# ---- Pure decision logic (no DB) ----

def test_decide_security_event_forces_reject():
    rec, reason = recommendation._decide(
        risk={"score": 10, "findings": []},
        compliance={"frameworks": []},
        security_events=[{"event_type": "prompt_injection", "severity": "critical"}],
    )
    assert rec == recommendation.REJECT
    assert "prompt_injection" in reason


def test_decide_critical_compliance_gap_forces_legal_review():
    rec, reason = recommendation._decide(
        risk={"score": 20},
        compliance={"frameworks": [{
            "framework": "HIPAA",
            "passed": False,
            "checks": [{
                "requirement": "BAA",
                "present": False,
                "severity": "Critical",
            }],
        }]},
        security_events=[],
    )
    assert rec == recommendation.LEGAL_REVIEW
    assert "HIPAA" in reason and "BAA" in reason


def test_decide_ignores_critical_checks_when_framework_passed():
    """Regression: Gemini sometimes marks individual checks as
    present=false/Critical for inapplicable frameworks (e.g. HIPAA on an NDA)
    while correctly setting framework.passed=true. We must trust the
    framework-level flag and not escalate."""
    rec, _ = recommendation._decide(
        risk={"score": 10},
        compliance={"frameworks": [{
            "framework": "HIPAA",
            "passed": True,  # <-- framework explicitly passed
            "checks": [
                {"requirement": "BAA", "present": False, "severity": "Critical"},
                {"requirement": "Breach Notification", "present": False, "severity": "Critical"},
            ],
        }]},
        security_events=[],
    )
    assert rec == recommendation.AUTO_APPROVE


def test_decide_strips_brackets_from_requirement_in_reasoning():
    rec, reason = recommendation._decide(
        risk={"score": 20},
        compliance={"frameworks": [{
            "framework": "HIPAA",
            "passed": False,
            "checks": [{
                "requirement": "[BAA]",
                "present": False,
                "severity": "Critical",
            }],
        }]},
        security_events=[],
    )
    assert rec == recommendation.LEGAL_REVIEW
    assert "BAA" in reason
    assert "[BAA]" not in reason


def test_decide_high_score_routes_to_legal_review():
    rec, reason = recommendation._decide(
        risk={"score": 75},
        compliance={"frameworks": []},
        security_events=[],
    )
    assert rec == recommendation.LEGAL_REVIEW
    assert "75" in reason


def test_decide_moderate_score_routes_to_manager_review():
    rec, _ = recommendation._decide(
        risk={"score": 45},
        compliance={"frameworks": []},
        security_events=[],
    )
    assert rec == recommendation.MANAGER_REVIEW


def test_decide_low_score_auto_approves():
    rec, _ = recommendation._decide(
        risk={"score": 12},
        compliance={"frameworks": []},
        security_events=[],
    )
    assert rec == recommendation.AUTO_APPROVE


def test_decide_handles_missing_risk_compliance():
    """Defensive: if upstream agents failed, _decide shouldn't crash."""
    rec, _ = recommendation._decide(
        risk=None, compliance=None, security_events=[],
    )
    assert rec == recommendation.AUTO_APPROVE


# ---- DB-integrated agent ----

def test_run_persists_decision_and_updates_status():
    cid = _seed_with_outputs(risk_score=82)
    decision = recommendation.run(SessionLocal(), cid)

    assert decision.recommendation == recommendation.LEGAL_REVIEW
    assert decision.reviewer_role == "agent:recommendation"

    db = SessionLocal()
    contract = db.query(Contract).filter_by(id=cid).first()
    assert contract.status == "legal_review"
    rows = db.query(Decision).filter_by(contract_id=cid).all()
    assert len(rows) == 1
    db.close()


def test_run_low_risk_advances_to_approved():
    cid = _seed_with_outputs(risk_score=15)
    recommendation.run(SessionLocal(), cid)
    db = SessionLocal()
    contract = db.query(Contract).filter_by(id=cid).first()
    assert contract.status == "approved"
    db.close()


def test_run_security_event_overrides_low_score():
    cid = _seed_with_outputs(
        risk_score=10,
        security_events=[{"event_type": "prompt_injection", "severity": "critical"}],
    )
    decision = recommendation.run(SessionLocal(), cid)
    assert decision.recommendation == recommendation.REJECT
    db = SessionLocal()
    contract = db.query(Contract).filter_by(id=cid).first()
    assert contract.status == "rejected"
    db.close()


# ---- Human decision endpoint ----

def test_human_decision_endpoint_records_approval():
    from fastapi.testclient import TestClient
    from backend.main import app
    client = TestClient(app)

    cid = _seed_with_outputs(risk_score=50)
    # Move to manager_review state by running the recommender first
    recommendation.run(SessionLocal(), cid)

    r = client.post(
        f"/contracts/{cid}/decide",
        data={
            "decision": "APPROVED",
            "reasoning": "Reviewed and approved.",
            "actor": "user:Compliance Officer",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["new_status"] == "approved"

    db = SessionLocal()
    decisions = db.query(Decision).filter_by(contract_id=cid).all()
    assert len(decisions) == 2  # one from agent, one from human
    human = [d for d in decisions if d.reviewer_role.startswith("user:")][0]
    assert human.recommendation == "APPROVED"
    assert human.reviewer_role == "user:Compliance Officer"
    db.close()


def test_human_decision_invalid_value_400():
    from fastapi.testclient import TestClient
    from backend.main import app
    client = TestClient(app)

    cid = _seed_with_outputs(risk_score=50)
    r = client.post(
        f"/contracts/{cid}/decide",
        data={"decision": "MAYBE", "reasoning": "...", "actor": "user:X"},
    )
    assert r.status_code == 400


# ---- Orchestrator now runs all 4 agents ----

def test_orchestrator_runs_recommendation_after_others():
    from backend import orchestrator
    cid = _seed_with_outputs(risk_score=0, security_events=None)
    # Reset contract status so the orchestrator will pick it up
    db = SessionLocal()
    c = db.query(Contract).filter_by(id=cid).first()
    c.status = "extracted"
    c.raw_text = "1.1 Scope. Test."
    c.clauses = [{"number": "1.1", "title": "Scope", "text": "Test."}]
    db.commit()
    db.close()

    fake_ext = ExtractionResult(
        parties=[Party(name="X", role=PartyRole.OTHER)],
        obligations=[], summary="t",
    )
    fake_risk = RiskAssessment(score=10, findings=[])
    fake_comp = FrameworkResult(framework="X", passed=True, checks=[])

    with patch.object(extraction_agent, "generate_json", return_value=fake_ext), \
         patch.object(risk_agent, "generate_json", return_value=fake_risk), \
         patch.object(risk_agent, "retrieve", return_value=[]), \
         patch.object(compliance_agent, "generate_json", return_value=fake_comp), \
         patch.object(compliance_agent, "retrieve", return_value=[
             {"framework": "HIPAA", "requirement": "Q", "severity": "low", "text": "..."},
         ]):
        out = orchestrator.run_pipeline(SessionLocal(), cid)

    assert "recommendation" in out["ran"]
    db = SessionLocal()
    contract = db.query(Contract).filter_by(id=cid).first()
    # Low risk score → auto-approved by Agent 5
    assert contract.status == "approved"
    db.close()
