"""Tests for the contract Q&A agent.

LLM calls are mocked. We verify:
  - Prompt is built from real clause data
  - Output is persisted to agent_outputs with the right shape
  - Missing / empty-clause contracts degrade gracefully
  - The /query/ endpoint routes correctly based on contract_id
"""
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.agents import contract_qa
from backend.agents.schemas import ClauseCitation, ContractQAResult
from backend.db import SessionLocal
from backend.main import app
from backend.models import AgentOutput, Contract

client = TestClient(app)


def _seed_contract_with_clauses(clauses=None, status="approved", filename="t.pdf") -> int:
    db = SessionLocal()
    c = Contract(
        filename=filename,
        status=status,
        file_hash=f"h_{filename}",
        raw_text="(test text)",
        clauses=clauses if clauses is not None else [
            {"number": "1.1", "title": "Scope",
             "text": "Vendor shall provide consulting services."},
            {"number": "1.4", "title": "Limitation of Liability",
             "text": "Vendor's liability shall not exceed fees paid in the "
                     "twelve (12) months preceding the claim."},
            {"number": "1.6", "title": "Governing Law",
             "text": "This Agreement is governed by the laws of Delaware."},
        ],
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    cid = c.id
    db.close()
    return cid


# ─── Agent unit tests ────────────────────────────────────────────────────────

def test_qa_answers_and_persists_output():
    fake = ContractQAResult(
        answer="Liability is capped at 12 months of fees per §1.4.",
        cited_clauses=[
            ClauseCitation(number="1.4", title="Limitation of Liability", relevance="high"),
        ],
        confidence=0.95,
    )
    cid = _seed_contract_with_clauses()

    with patch.object(contract_qa, "generate_json", return_value=fake):
        result = contract_qa.run(SessionLocal(), cid, "What is the liability cap?")

    assert result["error"] is None
    assert "§1.4" in result["answer"]
    assert result["cited_clauses"][0]["number"] == "1.4"
    assert result["confidence"] == 0.95

    db = SessionLocal()
    rows = (
        db.query(AgentOutput)
        .filter_by(contract_id=cid, agent_name="contract_qa")
        .all()
    )
    db.close()
    assert len(rows) == 1
    persisted = rows[0]
    assert persisted.output["question"] == "What is the liability cap?"
    assert persisted.output["confidence"] == 0.95
    assert persisted.prompt_hash and persisted.prompt_hash.startswith("sha256:")


def test_qa_handles_missing_contract():
    result = contract_qa.run(SessionLocal(), 999_999, "anything")
    assert result["error"] and "not found" in result["error"]
    assert result["answer"] is None
    assert result["cited_clauses"] == []


def test_qa_handles_empty_clauses_gracefully():
    cid = _seed_contract_with_clauses(clauses=[])

    # Should NOT call Gemini — short-circuits with a friendly message.
    with patch.object(contract_qa, "generate_json") as mock_gen:
        result = contract_qa.run(SessionLocal(), cid, "What is the term?")
        mock_gen.assert_not_called()

    assert result["error"] is None
    assert result["answer"] and "no extracted clauses" in result["answer"].lower()
    assert result["confidence"] == 0.0


def test_qa_handles_gemini_failure():
    cid = _seed_contract_with_clauses()
    with patch.object(contract_qa, "generate_json",
                      side_effect=RuntimeError("Gemini down")):
        result = contract_qa.run(SessionLocal(), cid, "anything")
    assert result["error"] and "Gemini down" in result["error"]
    assert result["answer"] is None


def test_qa_prompt_includes_all_clauses_and_question():
    """Verify the prompt is built from real clause data, not hallucinated."""
    cid = _seed_contract_with_clauses()
    captured = {}

    def capture(prompt, schema, **kwargs):
        captured["prompt"] = prompt
        return ContractQAResult(
            answer="ok",
            cited_clauses=[],
            confidence=0.5,
        )

    with patch.object(contract_qa, "generate_json", side_effect=capture):
        contract_qa.run(SessionLocal(), cid, "Where is it governed?")

    prompt = captured["prompt"]
    # Every clause should be in the prompt
    assert "Scope" in prompt
    assert "Limitation of Liability" in prompt
    assert "Governing Law" in prompt
    # The question gets substituted
    assert "Where is it governed?" in prompt
    # Filename gets substituted
    assert "t.pdf" in prompt


# ─── /query endpoint routing ─────────────────────────────────────────────────

def test_query_endpoint_routes_to_analytics_by_default():
    """No contract_id → analytics agent (text-to-SQL)."""
    from backend.agents import analytics

    fake = analytics.AnalyticsResponse(
        sql="SELECT COUNT(*) AS n FROM contracts",
        explanation="Counts all contracts.",
    )
    with patch.object(analytics, "nl_to_sql", return_value=fake):
        r = client.post("/query/", json={"question": "how many"})

    assert r.status_code == 200
    body = r.json()
    assert body["mode"] == "analytics"
    assert body.get("sql") == "SELECT COUNT(*) AS n FROM contracts"


def test_query_endpoint_routes_to_contract_qa_when_id_present():
    """contract_id set → contract_qa agent."""
    cid = _seed_contract_with_clauses()
    fake = ContractQAResult(
        answer="Governed by Delaware per §1.6.",
        cited_clauses=[
            ClauseCitation(number="1.6", title="Governing Law", relevance="high"),
        ],
        confidence=0.99,
    )
    with patch.object(contract_qa, "generate_json", return_value=fake):
        r = client.post("/query/", json={
            "question": "What law governs?",
            "contract_id": cid,
        })

    assert r.status_code == 200
    body = r.json()
    assert body["mode"] == "contract_qa"
    assert "Delaware" in body["answer"]
    assert body["cited_clauses"][0]["number"] == "1.6"
    assert body["contract_id"] == cid
