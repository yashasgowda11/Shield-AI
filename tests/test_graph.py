"""Tests for the knowledge graph builder + endpoint.

No LLM or RAG needed — graph is built from existing agent_outputs in the DB.
"""
import json

from fastapi.testclient import TestClient

from backend.agents.schemas import (
    ComplianceCheck,
    ComplianceResult,
    ExtractionResult,
    FrameworkResult,
    Party,
    PartyRole,
    RiskAssessment,
    RiskFinding,
    Severity,
)
from backend.db import SessionLocal
from backend.graph.builder import build, hub_summary, to_payload
from backend.main import app
from backend.models import AgentOutput, Contract

client = TestClient(app)


def _seed(
    *,
    filename: str,
    vendor: str,
    risk_findings: list[RiskFinding] | None = None,
    risk_score: int = 0,
    framework_results: list[FrameworkResult] | None = None,
    status: str = "approved",
) -> int:
    db = SessionLocal()
    c = Contract(filename=filename, status=status, file_hash=f"h_{filename}")
    db.add(c)
    db.commit()
    db.refresh(c)

    ext = ExtractionResult(
        parties=[Party(name=vendor, role=PartyRole.VENDOR)],
        obligations=[], summary="seed",
    )
    db.add(AgentOutput(contract_id=c.id, agent_name="extraction",
                       output=json.loads(ext.model_dump_json())))

    risk = RiskAssessment(score=risk_score, findings=risk_findings or [])
    db.add(AgentOutput(contract_id=c.id, agent_name="risk",
                       output=json.loads(risk.model_dump_json())))

    if framework_results is not None:
        comp = ComplianceResult(frameworks=framework_results)
        db.add(AgentOutput(contract_id=c.id, agent_name="compliance",
                           output=json.loads(comp.model_dump_json())))

    db.commit()
    cid = c.id
    db.close()
    return cid


# ---- Builder ----

def test_build_empty_db_returns_empty_graph():
    db = SessionLocal()
    g = build(db)
    db.close()
    assert g.number_of_nodes() == 0


def test_build_creates_vendor_contract_edge():
    _seed(filename="a.pdf", vendor="Acme")
    db = SessionLocal()
    g = build(db)
    db.close()

    assert "vendor:Acme" in g.nodes
    contract_node = next(n for n in g.nodes if n.startswith("contract:"))
    assert g.has_edge("vendor:Acme", contract_node)


def test_build_collapses_same_risk_across_contracts_into_one_node():
    """The whole point of the graph: same risk in N contracts = one hub."""
    f = RiskFinding(risk="Unlimited liability", severity=Severity.CRITICAL,
                    clause_ref="7.2", reasoning="...")
    _seed(filename="a.pdf", vendor="V1", risk_findings=[f], risk_score=80)
    _seed(filename="b.pdf", vendor="V2", risk_findings=[f], risk_score=85)
    _seed(filename="c.pdf", vendor="V3", risk_findings=[f], risk_score=70)

    db = SessionLocal()
    g = build(db)
    db.close()

    risk_nodes = [n for n in g.nodes if g.nodes[n].get("type") == "risk"]
    assert len(risk_nodes) == 1
    assert g.nodes["risk:Unlimited liability"]["occurrences"] == 3
    assert g.nodes["risk:Unlimited liability"]["max_severity"] == "Critical"


def test_build_tracks_max_severity_per_risk():
    f1 = RiskFinding(risk="X", severity=Severity.MEDIUM, clause_ref="1", reasoning="...")
    f2 = RiskFinding(risk="X", severity=Severity.CRITICAL, clause_ref="2", reasoning="...")
    _seed(filename="a.pdf", vendor="V", risk_findings=[f1])
    _seed(filename="b.pdf", vendor="V", risk_findings=[f2])

    db = SessionLocal()
    g = build(db)
    db.close()
    assert g.nodes["risk:X"]["max_severity"] == "Critical"


def test_build_adds_framework_nodes_with_passed_edge():
    fw = FrameworkResult(framework="HIPAA", passed=False, checks=[
        ComplianceCheck(requirement="BAA", present=False,
                        gap_description="...", severity=Severity.CRITICAL),
    ])
    _seed(filename="a.pdf", vendor="V", framework_results=[fw])

    db = SessionLocal()
    g = build(db)
    db.close()
    assert "framework:HIPAA" in g.nodes
    contract_node = next(n for n in g.nodes if n.startswith("contract:"))
    edge_data = list(g.get_edge_data(contract_node, "framework:HIPAA").values())[0]
    assert edge_data["type"] == "checked"
    assert edge_data["passed"] is False


# ---- Hub summary ----

def test_hub_summary_ranks_risks_by_occurrences_then_severity():
    f_critical = RiskFinding(risk="Critical risk", severity=Severity.CRITICAL,
                             clause_ref="1", reasoning="...")
    f_low = RiskFinding(risk="Low risk", severity=Severity.LOW,
                        clause_ref="2", reasoning="...")
    _seed(filename="a.pdf", vendor="V", risk_findings=[f_critical, f_low])
    _seed(filename="b.pdf", vendor="V", risk_findings=[f_critical, f_low])
    _seed(filename="c.pdf", vendor="V", risk_findings=[f_low])

    db = SessionLocal()
    g = build(db)
    summary = hub_summary(g)
    db.close()

    # Critical risk has higher severity → ranks first even though Low has more occurrences
    assert summary["top_risks"][0]["risk"] == "Critical risk"


# ---- Endpoint ----

def test_graph_endpoint_returns_payload_shape():
    _seed(filename="a.pdf", vendor="Acme")
    r = client.get("/graph/")
    assert r.status_code == 200
    body = r.json()
    assert "nodes" in body and "edges" in body and "stats" in body
    assert body["stats"]["n_nodes"] >= 2  # vendor + contract


def test_graph_endpoint_filters_by_node_type():
    _seed(filename="a.pdf", vendor="Acme",
          risk_findings=[RiskFinding(risk="X", severity=Severity.HIGH,
                                     clause_ref="1", reasoning="...")])
    r = client.get("/graph/?node_types=vendor,contract")
    body = r.json()
    types = {n["type"] for n in body["nodes"]}
    assert "risk" not in types
    assert "vendor" in types and "contract" in types


def test_graph_endpoint_filters_by_min_severity():
    _seed(filename="a.pdf", vendor="V", risk_findings=[
        RiskFinding(risk="Low", severity=Severity.LOW, clause_ref="1", reasoning="."),
        RiskFinding(risk="High", severity=Severity.HIGH, clause_ref="2", reasoning="."),
    ])
    r = client.get("/graph/?min_severity=High")
    body = r.json()
    risk_labels = {n["label"] for n in body["nodes"] if n.get("type") == "risk"}
    assert "Low" not in risk_labels
    assert "High" in risk_labels


def test_hubs_endpoint_returns_top_lists():
    _seed(filename="a.pdf", vendor="V")
    r = client.get("/graph/hubs")
    assert r.status_code == 200
    body = r.json()
    assert "top_vendors" in body
    assert "top_risks" in body
    assert "top_frameworks" in body
