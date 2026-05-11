"""Tests for Agent 6 (analytics / Ask Shield AI).

Covers SQL safety, mocked translation, and end-to-end execution against
seeded contracts. Gemini is mocked — no API calls.
"""
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.agents import analytics
from backend.agents.analytics import AnalyticsResponse, is_safe_sql
from backend.db import SessionLocal
from backend.main import app
from backend.models import Contract

client = TestClient(app)


# ---- Safety check ----

def test_safe_sql_accepts_select():
    ok, _ = is_safe_sql("SELECT * FROM contracts LIMIT 10")
    assert ok


def test_safe_sql_rejects_drop():
    ok, reason = is_safe_sql("DROP TABLE contracts")
    assert not ok and "DROP" in reason


def test_safe_sql_rejects_delete():
    ok, reason = is_safe_sql("DELETE FROM contracts WHERE id=1")
    assert not ok and "DELETE" in reason


def test_safe_sql_rejects_update():
    ok, reason = is_safe_sql("UPDATE contracts SET status='approved'")
    assert not ok and "UPDATE" in reason


def test_safe_sql_rejects_insert():
    ok, _ = is_safe_sql("INSERT INTO contracts (filename) VALUES ('x')")
    assert not ok


def test_safe_sql_rejects_multiple_statements():
    ok, reason = is_safe_sql("SELECT 1; SELECT 2")
    assert not ok and "multiple" in reason.lower()


def test_safe_sql_rejects_pragma():
    ok, _ = is_safe_sql("PRAGMA table_info(contracts)")
    assert not ok


def test_safe_sql_rejects_sqlite_master():
    ok, _ = is_safe_sql("SELECT * FROM sqlite_master")
    assert not ok


def test_safe_sql_rejects_unknown_table():
    ok, reason = is_safe_sql("SELECT * FROM users LIMIT 5")
    assert not ok and "users" in reason


def test_safe_sql_accepts_join_with_alias():
    ok, _ = is_safe_sql(
        "SELECT c.id FROM contracts c JOIN agent_outputs a ON a.contract_id = c.id LIMIT 5"
    )
    assert ok


# ---- End-to-end with mocked LLM ----

def _seed_contract(filename: str, status: str = "approved") -> int:
    db = SessionLocal()
    c = Contract(filename=filename, status=status, file_hash=f"h_{filename}")
    db.add(c)
    db.commit()
    db.refresh(c)
    cid = c.id
    db.close()
    return cid


def test_run_returns_rows_for_valid_sql():
    _seed_contract("a.pdf", "approved")
    _seed_contract("b.pdf", "legal_review")

    fake = AnalyticsResponse(
        sql="SELECT id, filename, status FROM contracts ORDER BY id LIMIT 10",
        explanation="Lists all contracts.",
    )
    with patch.object(analytics, "nl_to_sql", return_value=fake):
        result = analytics.run(SessionLocal(), "list everything")

    assert result["error"] is None
    assert result["row_count"] == 2
    assert result["rows"][0]["filename"] == "a.pdf"


def test_run_blocks_unsafe_sql_from_llm():
    """Belt and suspenders: even if the LLM returns DROP, we never run it."""
    fake = AnalyticsResponse(
        sql="DROP TABLE contracts",
        explanation="oops",
    )
    with patch.object(analytics, "nl_to_sql", return_value=fake):
        result = analytics.run(SessionLocal(), "drop everything")

    assert result["error"] is not None
    assert "DROP" in result["error"]
    assert result["rows"] == []


def test_run_handles_sql_execution_error():
    fake = AnalyticsResponse(
        sql="SELECT nonexistent_column FROM contracts",
        explanation="oops",
    )
    with patch.object(analytics, "nl_to_sql", return_value=fake):
        result = analytics.run(SessionLocal(), "broken")

    assert result["error"] is not None
    assert "Execution failed" in result["error"]


def test_run_handles_translation_failure_gracefully():
    with patch.object(analytics, "nl_to_sql",
                      side_effect=RuntimeError("LLM down")):
        result = analytics.run(SessionLocal(), "anything")

    assert result["error"] is not None
    assert "Translation failed" in result["error"]
    assert result["rows"] == []
    assert result["sql"] is None


# ---- HTTP endpoint ----

def test_query_endpoint_returns_payload():
    _seed_contract("a.pdf", "approved")
    fake = AnalyticsResponse(
        sql="SELECT COUNT(*) AS n FROM contracts",
        explanation="Count rows.",
    )
    with patch.object(analytics, "nl_to_sql", return_value=fake):
        r = client.post("/query/", json={"question": "how many"})

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["sql"] == "SELECT COUNT(*) AS n FROM contracts"
    assert body["row_count"] == 1
    assert body["rows"][0]["n"] == 1
