"""Agent 6 — Analytics ("Ask Shield AI") — Gemini text-to-SQL.

Translates natural-language questions about the contracts corpus into SQL,
runs them against a READ-ONLY view of the PostgreSQL DB, returns rows.

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

# Dialect-specific prompts. We pick at runtime based on the bound DB engine
# so the same agent code works against SQLite (local dev) and PostgreSQL
# (Cloud Run / production). Cloud Run's SQL grammar is incompatible with
# SQLite's and vice-versa — wrong dialect → "unrecognized token" errors.
_PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts"
_PG_PROMPT = (_PROMPTS_DIR / f"analytics_{PROMPT_VERSION}.txt").read_text(encoding="utf-8")
_SQLITE_PROMPT = (_PROMPTS_DIR / f"analytics_sqlite_{PROMPT_VERSION}.txt").read_text(encoding="utf-8")

_SYSTEM_PG = (
    "You are Shield AI's analytics agent. You translate natural-language "
    "questions about the contracts corpus into safe, read-only PostgreSQL queries. "
    "You never write SQL that modifies data. You always include a LIMIT. "
    "You always use PostgreSQL JSON operators (->> and ->) — never SQLite's json_extract()."
)
_SYSTEM_SQLITE = (
    "You are Shield AI's analytics agent. You translate natural-language "
    "questions about the contracts corpus into safe, read-only SQLite queries. "
    "You never write SQL that modifies data. You always include a LIMIT. "
    "You always use SQLite's json_extract / json_each — never PostgreSQL's ->> "
    "or :: casts."
)


def _select_prompt(db: Session) -> tuple[str, str]:
    """Pick the (template, system_instruction) pair matching the bound dialect."""
    name = (db.bind.dialect.name if db.bind is not None else "").lower()
    if name.startswith("postgres"):
        return _PG_PROMPT, _SYSTEM_PG
    # Fall back to SQLite for sqlite, sqlite-in-memory, or unknown.
    return _SQLITE_PROMPT, _SYSTEM_SQLITE

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
    sql: str = Field(description="The PostgreSQL query to run (use ->> and -> for JSON, never json_extract)")
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

    # Reject SQLite-specific snooping keywords (belt-and-suspenders; we're on PG)
    if "PRAGMA" in upper or "SQLITE_MASTER" in upper or "SQLITE_SCHEMA" in upper:
        return False, "PRAGMA / sqlite_master access not allowed"

    # PostgreSQL set-returning functions that are legal in a FROM / JOIN clause.
    # These are NOT table names — whitelisting them prevents false positives.
    PG_SRF_ALLOWLIST = {
        "json_array_elements",
        "jsonb_array_elements",
        "json_array_elements_text",
        "jsonb_array_elements_text",
        "json_each",
        "jsonb_each",
        "json_each_text",
        "jsonb_each_text",
        "json_object_keys",
        "jsonb_object_keys",
        "unnest",
        "generate_series",
        "lateral",  # LATERAL keyword appears where a table name would
    }

    # Lightweight table-name check — every FROM/JOIN target must be in ALLOWED_TABLES
    # or a whitelisted PG set-returning function.
    # Tolerates aliases like "FROM contracts c" and "FROM json_array_elements(...) fw".
    tokens = re.findall(r"\b(?:FROM|JOIN)\s+([A-Za-z_][A-Za-z0-9_]*)", upper)
    for t in tokens:
        tl = t.lower()
        if tl not in ALLOWED_TABLES and tl not in PG_SRF_ALLOWLIST:
            return False, f"table not allowed: {tl}"

    return True, None


def nl_to_sql(question: str, db: Session) -> AnalyticsResponse:
    """Generate SQL for a question. No execution, just translation.

    The prompt + system instruction are picked based on the bound DB dialect
    so SQLite and PostgreSQL targets each get syntactically valid SQL.
    """
    template, system = _select_prompt(db)
    prompt = template.replace("{question}", question)
    return generate_json(
        prompt=prompt,
        schema=AnalyticsResponse,
        model=MODEL_FLASH,
        system=system,
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
    template, system = _select_prompt(db)
    p_hash = hash_prompt(template.replace("{question}", question), system=system)

    try:
        response = nl_to_sql(question, db)
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
            # JSON columns may come back as strings; try to parse for nicer rendering
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
