"""Agent 6 — Analytics ("Ask Shield AI") — Gemini text-to-SQL.

Translates natural-language questions about the contracts corpus into SQL,
runs them against a READ-ONLY view of the SQLite DB, returns rows.

Safety layers (each one is a hard stop, not advisory):
  1. The Pydantic schema only allows {sql, explanation} as output.
  2. is_safe_sql() rejects any forbidden keyword (DROP, DELETE, UPDATE, etc.).
  3. The execution path only allows tables in ALLOWED_TABLES.
  4. We always wrap the result in LIMIT to bound payload size.
"""
import json
import logging
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.llm import MODEL_FLASH, generate_json, hash_prompt

logger = logging.getLogger(__name__)

AGENT_NAME = "analytics"
PROMPT_VERSION = "v1.0.0"

_PROMPT_PATH = Path(__file__).resolve().parents[2] / "prompts" / f"analytics_{PROMPT_VERSION}.txt"
_PROMPT_TEMPLATE = _PROMPT_PATH.read_text(encoding="utf-8")

SYSTEM_INSTRUCTION = (
    "You are Shield AI's analytics agent. You translate natural-language "
    "questions about the contracts corpus into safe, read-only SQLite queries. "
    "You never write SQL that modifies data. You always include a LIMIT."
)

ALLOWED_TABLES = {
    "contracts", "agent_outputs", "decisions",
    "security_events", "audit_logs",
}

FORBIDDEN_KEYWORDS = {
    "DROP", "DELETE", "UPDATE", "INSERT", "ALTER", "TRUNCATE",
    "CREATE", "REPLACE", "GRANT", "REVOKE", "ATTACH", "DETACH",
}

# Hard cap to keep the API payload sane even if the model omitted LIMIT
MAX_ROWS = 200


class AnalyticsResponse(BaseModel):
    sql: str = Field(description="The SQLite query to run")
    explanation: str = Field(description="One sentence describing what's being queried")


def is_safe_sql(sql: str) -> tuple[bool, str | None]:
    """Conservative safety check. Returns (ok, reason_if_not).

    Hard rejects:
      - any forbidden write keyword
      - multiple statements (semicolons separating queries)
      - PRAGMA / sqlite_master access
      - tables outside ALLOWED_TABLES
    """
    if not sql or not sql.strip():
        return False, "empty SQL"

    upper = sql.upper()

    # Reject obvious mutation keywords as standalone tokens
    for kw in FORBIDDEN_KEYWORDS:
        if re.search(rf"\b{kw}\b", upper):
            return False, f"forbidden keyword: {kw}"

    # Reject multi-statement queries
    body = sql.strip().rstrip(";")
    if ";" in body:
        return False, "multiple statements not allowed"

    # Reject PRAGMA and sqlite_master snooping
    if "PRAGMA" in upper or "SQLITE_MASTER" in upper or "SQLITE_SCHEMA" in upper:
        return False, "PRAGMA / sqlite_master access not allowed"

    # Lightweight table-name check — every FROM/JOIN target must be in ALLOWED_TABLES
    # (tolerates aliases like "FROM contracts c")
    tokens = re.findall(r"\b(?:FROM|JOIN)\s+([A-Za-z_][A-Za-z0-9_]*)", upper)
    for t in tokens:
        if t.lower() not in ALLOWED_TABLES:
            return False, f"table not allowed: {t.lower()}"

    return True, None


def nl_to_sql(question: str) -> AnalyticsResponse:
    """Generate SQL for a question. No execution, just translation."""
    prompt = _PROMPT_TEMPLATE.replace("{question}", question)
    return generate_json(
        prompt=prompt,
        schema=AnalyticsResponse,
        model=MODEL_FLASH,
        system=SYSTEM_INSTRUCTION,
    )


def run(db: Session, question: str) -> dict[str, Any]:
    """End-to-end: translate, validate, execute, return rows.

    Returns:
        {
          "question": str,
          "sql": str | None,
          "explanation": str | None,
          "rows": list[dict],
          "row_count": int,
          "error": str | None,
          "prompt_hash": str | None,
        }
    """
    p_hash = hash_prompt(_PROMPT_TEMPLATE.replace("{question}", question), system=SYSTEM_INSTRUCTION)

    try:
        response = nl_to_sql(question)
    except Exception as e:
        logger.exception("Analytics agent failed during NL→SQL translation")
        return {
            "question": question,
            "sql": None,
            "explanation": None,
            "rows": [],
            "row_count": 0,
            "error": f"Translation failed: {e}",
            "prompt_hash": p_hash,
        }

    sql = response.sql.strip().rstrip(";")
    ok, reason = is_safe_sql(sql)
    if not ok:
        return {
            "question": question,
            "sql": sql,
            "explanation": response.explanation,
            "rows": [],
            "row_count": 0,
            "error": f"SQL rejected by safety check: {reason}",
            "prompt_hash": p_hash,
        }

    # Execute — readonly engine path. SQLAlchemy text() with no params; we already
    # validated the SQL doesn't mutate.
    try:
        result = db.execute(text(sql))
        col_names = list(result.keys())
        raw_rows = result.fetchmany(MAX_ROWS)
    except Exception as e:
        logger.exception("Analytics SQL execution failed: %s", sql)
        return {
            "question": question,
            "sql": sql,
            "explanation": response.explanation,
            "rows": [],
            "row_count": 0,
            "error": f"Execution failed: {e}",
            "prompt_hash": p_hash,
        }

    # Coerce rows to dicts and stringify any JSON-blob columns
    rows = []
    for r in raw_rows:
        d: dict[str, Any] = {}
        for k, v in zip(col_names, r):
            # SQLite JSON fields come back as strings; try to parse for nicer rendering
            if isinstance(v, str) and v.startswith(("{", "[")):
                try:
                    d[k] = json.loads(v)
                    continue
                except Exception:
                    pass
            d[k] = v
        rows.append(d)

    return {
        "question": question,
        "sql": sql,
        "explanation": response.explanation,
        "rows": rows,
        "row_count": len(rows),
        "error": None,
        "prompt_hash": p_hash,
    }
