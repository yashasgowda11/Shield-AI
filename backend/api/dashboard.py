"""Dashboard aggregation endpoints.

Two endpoints:
  GET /dashboard/risk-summary      → Risk Dashboard data
  GET /dashboard/security-summary  → Security Dashboard data

Reads from agent_outputs (latest per agent per contract) + security_events
+ contracts. No LLM calls.
"""
import statistics
from collections import Counter
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.db import get_db
from backend.models import AgentOutput, Contract, SecurityEvent

router = APIRouter()


# ---- Helpers ----

def _batch_latest_outputs(
    db: Session,
    contract_ids: list[int],
    agent_name: str,
) -> dict[int, dict]:
    """Return the latest output for `agent_name` for every contract in one query.

    Uses a subquery to pick the MAX(created_at) per contract so we load
    exactly N rows instead of issuing N separate SELECT statements.
    """
    if not contract_ids:
        return {}

    # Subquery: latest created_at per contract for this agent
    latest_sq = (
        db.query(
            AgentOutput.contract_id,
            func.max(AgentOutput.created_at).label("max_ts"),
        )
        .filter(
            AgentOutput.contract_id.in_(contract_ids),
            AgentOutput.agent_name == agent_name,
        )
        .group_by(AgentOutput.contract_id)
        .subquery()
    )

    rows = (
        db.query(AgentOutput)
        .join(
            latest_sq,
            (AgentOutput.contract_id == latest_sq.c.contract_id)
            & (AgentOutput.created_at == latest_sq.c.max_ts),
        )
        .filter(AgentOutput.agent_name == agent_name)
        .all()
    )

    return {row.contract_id: (row.output or {}) for row in rows}


def _vendor_from_extraction(extraction: dict | None) -> str | None:
    if not extraction:
        return None
    # First Vendor-role party wins; otherwise fall back to the first party.
    parties = extraction.get("parties") or []
    for p in parties:
        if (p.get("role") or "").lower() == "vendor":
            return p.get("name")
    if parties:
        return parties[0].get("name")
    return None


# ---- Risk Dashboard ----

@router.get("/risk-summary")
def risk_summary(db: Session = Depends(get_db)) -> dict[str, Any]:
    contracts = db.query(Contract).all()
    contract_ids = [c.id for c in contracts]

    # Batch-load latest risk + extraction outputs — 2 queries total, not 2N
    risk_map = _batch_latest_outputs(db, contract_ids, "risk")
    ext_map  = _batch_latest_outputs(db, contract_ids, "extraction")

    # Per-contract risk view
    rows: list[dict[str, Any]] = []
    for c in contracts:
        risk = risk_map.get(c.id, {})
        ext  = ext_map.get(c.id, {})
        rows.append({
            "contract_id": c.id,
            "filename": c.filename,
            "status": c.status,
            "vendor": _vendor_from_extraction(ext),
            "score": risk.get("score"),
            "findings": risk.get("findings") or [],
            "uploaded_at": c.uploaded_at.isoformat() if c.uploaded_at else None,
        })

    scored = [r for r in rows if isinstance(r["score"], (int, float))]
    scores = [r["score"] for r in scored]

    # Status counts
    by_status = dict(Counter(r["status"] for r in rows))

    # Score buckets for the histogram
    buckets = {"0-30 (low)": 0, "31-60 (moderate)": 0, "61-100 (high)": 0}
    for s in scores:
        if s <= 30:
            buckets["0-30 (low)"] += 1
        elif s <= 60:
            buckets["31-60 (moderate)"] += 1
        else:
            buckets["61-100 (high)"] += 1

    avg_score = round(statistics.mean(scores), 1) if scores else 0
    median_score = round(statistics.median(scores), 1) if scores else 0

    # Vendor ranking (avg score per vendor, desc)
    vendor_groups: dict[str, list[int]] = {}
    for r in scored:
        v = r["vendor"] or "(unknown)"
        vendor_groups.setdefault(v, []).append(r["score"])
    vendor_ranking = sorted(
        [
            {
                "vendor": v,
                "n_contracts": len(s),
                "avg_score": round(statistics.mean(s), 1),
                "max_score": max(s),
            }
            for v, s in vendor_groups.items()
        ],
        key=lambda x: x["avg_score"],
        reverse=True,
    )

    # Top recurring risk labels across all findings
    finding_counter: Counter = Counter()
    severity_by_finding: dict[str, list[str]] = {}
    for r in scored:
        for f in r["findings"]:
            label = f.get("risk", "(unknown)")
            finding_counter[label] += 1
            severity_by_finding.setdefault(label, []).append(f.get("severity", "Medium"))
    top_findings = [
        {
            "risk": label,
            "count": count,
            "max_severity": _max_severity(severity_by_finding.get(label, [])),
        }
        for label, count in finding_counter.most_common(10)
    ]

    # Anomaly detection — contracts >= 1.5 σ above the mean OR score >= 70.
    # The OR keeps the demo populated even when std dev is small.
    anomalies: list[dict] = []
    if scores:
        mean = statistics.mean(scores)
        stdev = statistics.pstdev(scores) if len(scores) > 1 else 0
        for r in scored:
            z = (r["score"] - mean) / stdev if stdev else 0
            is_outlier = stdev > 0 and z >= 1.5
            is_high = r["score"] >= 70
            if is_outlier or is_high:
                anomalies.append({
                    "contract_id": r["contract_id"],
                    "filename": r["filename"],
                    "vendor": r["vendor"],
                    "score": r["score"],
                    "z_score": round(z, 2) if stdev else None,
                    "reason": (
                        "high absolute score (≥70)" if is_high and not is_outlier
                        else f"{round(z, 2)}σ above corpus mean"
                    ),
                })

    return {
        "total_contracts": len(rows),
        "processed_contracts": len(scored),
        "avg_risk_score": avg_score,
        "median_risk_score": median_score,
        "by_status": by_status,
        "score_buckets": buckets,
        "scores": scores,  # raw for histograms
        "vendor_ranking": vendor_ranking,
        "top_recurring_risks": top_findings,
        "anomalies": anomalies,
    }


_SEVERITY_ORDER = ["Low", "Medium", "High", "Critical"]


def _max_severity(severities: list[str]) -> str:
    """Return the most severe entry from a list."""
    if not severities:
        return "Low"
    return max(severities, key=lambda s: _SEVERITY_ORDER.index(s) if s in _SEVERITY_ORDER else 0)


# ---- Security Dashboard ----

@router.get("/security-summary")
def security_summary(db: Session = Depends(get_db)) -> dict[str, Any]:
    events = (
        db.query(SecurityEvent)
        .order_by(SecurityEvent.created_at.desc())
        .all()
    )
    contracts = {c.id: c for c in db.query(Contract).all()}

    quarantined = sum(1 for c in contracts.values() if c.status == "quarantined")

    by_type = dict(Counter(e.event_type for e in events))
    by_severity = dict(Counter(e.severity for e in events))

    # Recent feed (last 20) with filename joined in
    recent = []
    for e in events[:20]:
        c = contracts.get(e.contract_id)
        recent.append({
            "contract_id": e.contract_id,
            "filename": c.filename if c else "(deleted)",
            "event_type": e.event_type,
            "severity": e.severity,
            "details": e.details,
            "created_at": e.created_at.isoformat() if e.created_at else None,
        })

    return {
        "total_events": len(events),
        "blocked_injections": sum(
            1 for e in events
            if e.event_type in ("instruction_override", "decision_manipulation",
                                "role_override", "policy_bypass")
        ),
        "quarantined_contracts": quarantined,
        "events_by_type": by_type,
        "events_by_severity": by_severity,
        "recent_events": recent,
    }
