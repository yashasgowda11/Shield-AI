"""Tests for the dashboard aggregation endpoints.

These don't hit Gemini — they query the DB directly and assert shape + math.
"""
import json

from fastapi.testclient import TestClient

from backend.agents.schemas import (
    ComplianceResult,
    ExtractionResult,
    Party,
    PartyRole,
    RiskAssessment,
    RiskFinding,
    Severity,
)
from backend.db import SessionLocal
from backend.main import app
from backend.models import AgentOutput, Contract, SecurityEvent

client = TestClient(app)


def _seed_contract(
    *,
    filename: str,
    risk_score: int,
    findings: list | None = None,
    vendor: str | None = None,
    status: str = "approved",
) -> int:
    """Seed a contract + extraction (with vendor) + risk output."""
    db = SessionLocal()
    c = Contract(
        filename=filename,
        status=status,
        file_hash=f"h_{filename}",
        raw_text="...",
        clauses=[],
    )
    db.add(c)
    db.commit()
    db.refresh(c)

    if vendor:
        ext = ExtractionResult(
            parties=[Party(name=vendor, role=PartyRole.VENDOR)],
            obligations=[], summary="seed",
        )
        db.add(AgentOutput(
            contract_id=c.id,
            agent_name="extraction",
            output=json.loads(ext.model_dump_json()),
        ))

    risk = RiskAssessment(score=risk_score, findings=findings or [])
    db.add(AgentOutput(
        contract_id=c.id,
        agent_name="risk",
        output=json.loads(risk.model_dump_json()),
    ))
    db.commit()
    cid = c.id
    db.close()
    return cid


# ---- Risk summary ----

def test_risk_summary_empty_db():
    r = client.get("/dashboard/risk-summary")
    assert r.status_code == 200
    body = r.json()
    assert body["total_contracts"] == 0
    assert body["scores"] == []
    assert body["anomalies"] == []


def test_risk_summary_aggregates_basic_metrics():
    _seed_contract(filename="a.pdf", risk_score=10, vendor="Acme")
    _seed_contract(filename="b.pdf", risk_score=45, vendor="Beta")
    _seed_contract(filename="c.pdf", risk_score=82, vendor="Charlie",
                   findings=[RiskFinding(
                       risk="Unlimited liability",
                       severity=Severity.CRITICAL,
                       clause_ref="7.2",
                       reasoning="...",
                   ).model_dump()])

    body = client.get("/dashboard/risk-summary").json()

    assert body["total_contracts"] == 3
    assert body["processed_contracts"] == 3
    assert sorted(body["scores"]) == [10, 45, 82]
    assert body["avg_risk_score"] > 40
    assert body["score_buckets"]["0-30 (low)"] == 1
    assert body["score_buckets"]["31-60 (moderate)"] == 1
    assert body["score_buckets"]["61-100 (high)"] == 1


def test_risk_summary_flags_high_score_as_anomaly():
    _seed_contract(filename="low.pdf", risk_score=10, vendor="Acme")
    _seed_contract(filename="high.pdf", risk_score=85, vendor="RiskyCo")

    body = client.get("/dashboard/risk-summary").json()
    flagged = {a["filename"] for a in body["anomalies"]}
    assert "high.pdf" in flagged
    # Low-score one shouldn't be an anomaly even with small corpus
    assert "low.pdf" not in flagged


def test_risk_summary_vendor_ranking_sorts_by_avg_score():
    _seed_contract(filename="a1.pdf", risk_score=80, vendor="RiskyVendor")
    _seed_contract(filename="a2.pdf", risk_score=70, vendor="RiskyVendor")
    _seed_contract(filename="b1.pdf", risk_score=15, vendor="SafeVendor")

    body = client.get("/dashboard/risk-summary").json()
    ranking = body["vendor_ranking"]
    assert ranking[0]["vendor"] == "RiskyVendor"
    assert ranking[0]["n_contracts"] == 2
    assert ranking[0]["avg_score"] == 75.0
    assert ranking[-1]["vendor"] == "SafeVendor"


def test_risk_summary_top_recurring_risks_counts_correctly():
    f1 = RiskFinding(risk="Unlimited liability", severity=Severity.CRITICAL,
                     clause_ref="7.2", reasoning="...").model_dump()
    f2 = RiskFinding(risk="Asymmetric termination", severity=Severity.HIGH,
                     clause_ref="8.1", reasoning="...").model_dump()
    _seed_contract(filename="a.pdf", risk_score=80, findings=[f1, f2])
    _seed_contract(filename="b.pdf", risk_score=70, findings=[f1])

    body = client.get("/dashboard/risk-summary").json()
    risks = {r["risk"]: r for r in body["top_recurring_risks"]}
    assert risks["Unlimited liability"]["count"] == 2
    assert risks["Unlimited liability"]["max_severity"] == "Critical"
    assert risks["Asymmetric termination"]["count"] == 1


# ---- Security summary ----

def _seed_security_event(filename: str, event_type: str, severity: str = "critical"):
    db = SessionLocal()
    c = Contract(filename=filename, status="quarantined", file_hash=f"h_{filename}")
    db.add(c)
    db.commit()
    db.refresh(c)
    db.add(SecurityEvent(
        contract_id=c.id,
        event_type=event_type,
        severity=severity,
        details={"matched_text": "ignore prior instructions",
                 "context": "...some context...",
                 "confidence": 0.95},
    ))
    db.commit()
    db.close()


def test_security_summary_empty():
    body = client.get("/dashboard/security-summary").json()
    assert body["total_events"] == 0
    assert body["blocked_injections"] == 0
    assert body["recent_events"] == []


def test_security_summary_counts_blocked_injections():
    _seed_security_event("bad1.pdf", "instruction_override")
    _seed_security_event("bad2.pdf", "decision_manipulation")
    _seed_security_event("bad3.pdf", "suspicious_metadata")

    body = client.get("/dashboard/security-summary").json()
    assert body["total_events"] == 3
    assert body["blocked_injections"] == 2  # the two injection-class events
    assert body["quarantined_contracts"] == 3
    assert body["events_by_type"]["instruction_override"] == 1


def test_security_summary_recent_events_include_matched_text():
    _seed_security_event("bad.pdf", "instruction_override")
    body = client.get("/dashboard/security-summary").json()
    assert len(body["recent_events"]) == 1
    ev = body["recent_events"][0]
    assert ev["filename"] == "bad.pdf"
    assert ev["details"]["matched_text"] == "ignore prior instructions"
