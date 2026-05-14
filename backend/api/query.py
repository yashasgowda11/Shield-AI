"""NL Query endpoint — Ask Shield AI (two modes).

POST /query/   {"question": "..."}
    → analytics mode (text-to-SQL across the whole corpus)

POST /query/   {"question": "...", "contract_id": 42}
    → contract Q&A mode (grounded answer about ONE contract with citations)

Frontend toggles between modes; backend chooses by presence of contract_id.

Security:  Every user question is scanned by Agent 4 (Lobster Trap) BEFORE it
           reaches Agents 6 or 7. This closes the injection gap where a
           crafted question could otherwise be forwarded verbatim to Gemini.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.agents.analytics import run as analytics_run
from backend.agents.contract_qa import run as contract_qa_run
from backend import lobstertrap as lt_client
from backend.agents.security import scan_text_offline  # offline fallback
from backend.db import get_db

router = APIRouter()


class QueryRequest(BaseModel):
    question: str
    contract_id: Optional[int] = None


def _security_scan_question(question: str) -> dict:
    """Run Agent 4 (Lobster Trap + offline fallback) on the user's question.

    Returns a dict describing the scan outcome:
        {
          "blocked":    bool,
          "lt_used":    bool,
          "lt_result":  dict | None,   # populated when LT returned DENY
          "offline_events": list,      # populated when offline detector fires
          "reason":     str | None,    # human-readable block reason
        }
    """
    lt_available = lt_client.is_available()
    lt_result = None
    offline_events: list = []

    if lt_available:
        lt_result = lt_client.scan(question, agent_id="shield-ai-query-gate")

    if lt_result is not None:
        # Lobster Trap blocked it
        return {
            "blocked": True,
            "lt_used": True,
            "lt_result": lt_result,
            "offline_events": [],
            "reason": lt_result.get("deny_message") or f"Blocked by rule: {lt_result.get('rule_name')}",
        }

    # Offline pattern detector always runs (belt-and-suspenders / fallback)
    offline_events = scan_text_offline(question)
    if offline_events:
        return {
            "blocked": True,
            "lt_used": lt_available,
            "lt_result": None,
            "offline_events": offline_events,
            "reason": offline_events[0].get("description", "Suspicious content detected"),
        }

    return {
        "blocked": False,
        "lt_used": lt_available,
        "lt_result": None,
        "offline_events": [],
        "reason": None,
    }


@router.post("/")
def nl_query(req: QueryRequest, db: Session = Depends(get_db)):
    """Route to the right agent based on contract_id.

    Security gate (Agent 4) runs first on every question. If Lobster Trap or
    the offline detector flags the input, we return a 200 with `blocked: true`
    so the frontend can render a clear security notice.

    Analytics responses include `sql` and `rows`.
    Contract-Q&A responses include `answer`, `cited_clauses`, and `confidence`.
    Both include `mode` so the frontend renders the right thing without
    inferring from the shape.
    """
    # ── Agent 4: Security Gate ──────────────────────────────────────────────
    scan = _security_scan_question(req.question)

    if scan["blocked"]:
        # 400 Bad Request — the input itself was rejected by the security gate.
        # Returning 200 with blocked=true would be misleading; 400 signals to
        # the client that the query cannot be retried as-is.
        raise HTTPException(
            status_code=400,
            detail={
                "code": "QUERY_BLOCKED",
                "reason": scan["reason"],
                "lt_used": scan["lt_used"],
                "offline_events": scan["offline_events"],
                "message": f"Query blocked by Agent 4 — Security Gate: {scan['reason']}",
            },
        )

    security_info = {
        "lt_used": scan["lt_used"],
        "lt_available": scan["lt_used"],   # only True if it responded (same check)
    }

    # ── Agent 7: Contract Q&A ───────────────────────────────────────────────
    if req.contract_id is not None:
        result = contract_qa_run(db, req.contract_id, req.question)
        result["mode"] = "contract_qa"
        result["security_scan"] = security_info
        return result

    # ── Agent 6: Analytics (NL→SQL) ─────────────────────────────────────────
    result = analytics_run(db, req.question)
    result["mode"] = "analytics"
    result["security_scan"] = security_info
    return result
