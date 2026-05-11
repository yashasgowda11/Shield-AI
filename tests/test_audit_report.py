"""Tests for the audit-report endpoint.

Verifies the report aggregates everything we know about a contract: agent
outputs, decisions, security events, and the per-contract audit log.
"""
import json

from fastapi.testclient import TestClient

from backend import audit
from backend.agents.schemas import (
    ExtractionResult,
    Party,
    PartyRole,
    RiskAssessment,
    RiskFinding,
    Severity,
)
from backend.db import SessionLocal
from backend.main import app
from backend.models import AgentOutput, Contract, Decision, SecurityEvent

client = TestClient(app)


def _seed_full_contract() -> int:
    db = SessionLocal()
    c = Contract(
        filename="t.pdf",
        status="approved",
        file_hash="abcdef",
        raw_text="full contract text",
        clauses=[{"number": "1.1", "title": "Scope", "text": "..."}],
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    cid = c.id

    # Agent outputs
    ext = ExtractionResult(
        parties=[Party(name="Acme", role=PartyRole.VENDOR)],
        obligations=[], summary="seed",
    )
    db.add(AgentOutput(
        contract_id=cid, agent_name="extraction",
        output=json.loads(ext.model_dump_json()),
        prompt_hash="sha256:extraction1",
    ))

    risk = RiskAssessment(
        score=72,
        findings=[RiskFinding(
            risk="Test risk", severity=Severity.HIGH,
            clause_ref="1.1", reasoning="...",
        )],
    )
    db.add(AgentOutput(
        contract_id=cid, agent_name="risk",
        output=json.loads(risk.model_dump_json()),
        prompt_hash="sha256:risk1",
    ))

    # AI decision
    db.add(Decision(
        contract_id=cid,
        recommendation="LEGAL_REVIEW",
        reasoning="Score 72 over threshold.",
        reviewer_role="agent:recommendation",
    ))

    # Human decision
    db.add(Decision(
        contract_id=cid,
        recommendation="APPROVED",
        reasoning="Reviewed and approved.",
        reviewer_role="user:Legal Reviewer",
    ))

    # Security event
    db.add(SecurityEvent(
        contract_id=cid,
        event_type="instruction_override",
        severity="critical",
        details={"matched_text": "ignore prior instructions"},
    ))

    db.commit()

    # Audit log entries (via the helper, since that's how production writes them)
    audit.log(db, actor="user:Procurement Analyst", action="upload",
              resource=f"contract:{cid}", after={"filename": "t.pdf"})
    audit.log(db, actor="agent:risk", action="assess",
              resource=f"contract:{cid}", after={"score": 72})
    audit.log(db, actor="user:Legal Reviewer", action="decide",
              resource=f"contract:{cid}", after={"decision": "APPROVED"})

    db.close()
    return cid


def test_audit_report_404_for_unknown_contract():
    r = client.get("/contracts/9999/audit-report")
    assert r.status_code == 404


def test_audit_report_includes_all_sections():
    cid = _seed_full_contract()
    r = client.get(f"/contracts/{cid}/audit-report")
    assert r.status_code == 200
    body = r.json()

    # Top-level shape
    assert body["report_version"] == "1.0"
    assert body["report_generated_at"].endswith("Z")

    # Contract metadata
    assert body["contract"]["id"] == cid
    assert body["contract"]["file_hash"] == "abcdef"
    assert body["contract"]["current_status"] == "approved"
    assert body["contract"]["n_clauses"] == 1

    # Agent outputs (extraction + risk)
    names = {ao["agent_name"] for ao in body["agent_outputs"]}
    assert names == {"extraction", "risk"}

    # Prompt hashes are preserved
    risk_ao = next(ao for ao in body["agent_outputs"] if ao["agent_name"] == "risk")
    assert risk_ao["prompt_hash"] == "sha256:risk1"
    assert risk_ao["output"]["score"] == 72

    # Decisions (AI + human)
    assert len(body["decisions"]) == 2
    roles = {d["reviewer_role"] for d in body["decisions"]}
    assert "agent:recommendation" in roles
    assert "user:Legal Reviewer" in roles

    # Security events
    assert len(body["security_events"]) == 1
    assert body["security_events"][0]["event_type"] == "instruction_override"

    # Audit log (3 entries seeded)
    assert len(body["audit_log"]) == 3
    actions = [e["action"] for e in body["audit_log"]]
    assert actions == ["upload", "assess", "decide"]


def test_audit_report_handles_minimal_contract():
    """Contract with no agents run, no decisions, no events should still produce a report."""
    db = SessionLocal()
    c = Contract(filename="bare.pdf", status="extracted", file_hash="h", raw_text="x")
    db.add(c); db.commit(); db.refresh(c)
    cid = c.id
    db.close()

    r = client.get(f"/contracts/{cid}/audit-report")
    assert r.status_code == 200
    body = r.json()
    assert body["agent_outputs"] == []
    assert body["decisions"] == []
    assert body["security_events"] == []
    assert body["audit_log"] == []
