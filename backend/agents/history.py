"""Historical context helpers — used by all agents to be aware of past performance.

Each function queries the DB (not Pinecone) so they work even when the vector
index is unavailable. Results are formatted as compact prompt snippets that
agents can prepend to their existing prompts.
"""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


# ── Shared lookup ──────────────────────────────────────────────────────────────

def _agent_outputs_for_vendor(
    db: Session,
    vendor_name: str,
    agent_name: str,
    limit: int = 5,
) -> list[dict]:
    """Return the N most recent agent_outputs for a vendor (case-insensitive match).

    Captures both the AI recommendation and any human override decision + reason
    for each contract so downstream prompt snippets can reflect the full history.
    """
    if not vendor_name or vendor_name.lower() == "unknown":
        return []
    try:
        from sqlalchemy import text
        rows = db.execute(text("""
            SELECT
                ao.output,
                ao.created_at,
                c.filename,
                ai_d.recommendation  AS ai_recommendation,
                hum_d.recommendation AS human_decision,
                hum_d.reasoning      AS human_reasoning,
                hum_d.reviewer_role  AS human_reviewer
            FROM agent_outputs ao
            JOIN contracts c ON c.id = ao.contract_id
            -- AI decision (latest agent:* row for this contract)
            LEFT JOIN LATERAL (
                SELECT recommendation
                FROM decisions
                WHERE contract_id = ao.contract_id
                  AND reviewer_role LIKE 'agent:%%'
                ORDER BY id DESC
                LIMIT 1
            ) ai_d ON TRUE
            -- Human decision (latest non-agent row for this contract)
            LEFT JOIN LATERAL (
                SELECT recommendation, reasoning, reviewer_role
                FROM decisions
                WHERE contract_id = ao.contract_id
                  AND reviewer_role NOT LIKE 'agent:%%'
                ORDER BY id DESC
                LIMIT 1
            ) hum_d ON TRUE
            WHERE ao.agent_name = :agent
              AND ao.output IS NOT NULL
              AND LOWER(ao.output::text) LIKE :vendor_pattern
            ORDER BY ao.created_at DESC
            LIMIT :lim
        """), {
            "agent": agent_name,
            "vendor_pattern": f"%{vendor_name.lower()[:20]}%",
            "lim": limit,
        }).fetchall()
        return [
            {
                "output":           r.output,
                "filename":         r.filename,
                "recommendation":   r.ai_recommendation,
                "human_decision":   r.human_decision,
                "human_reasoning":  r.human_reasoning,
                "human_reviewer":   r.human_reviewer,
                "created_at":       str(r.created_at)[:10],
            }
            for r in rows
        ]
    except Exception:
        logger.exception("history: failed to fetch %s history for vendor '%s'", agent_name, vendor_name)
        return []


# ── Agent 1 — Extraction: vendor pattern awareness ────────────────────────────

def get_vendor_extraction_history(db: Session, vendor_name: str) -> str:
    """Return a prompt snippet summarising this vendor's past extraction patterns.

    Highlights if governing law or payment terms differ from the vendor's norm
    so Agent 1 can flag anomalies in its summary.
    """
    rows = _agent_outputs_for_vendor(db, vendor_name, "extraction", limit=4)
    if not rows:
        return ""

    governing_laws   = [r["output"].get("governing_law") for r in rows if r["output"].get("governing_law")]
    payment_terms    = [r["output"].get("payment_terms")  for r in rows if r["output"].get("payment_terms")]
    prior_decisions  = [r["recommendation"] for r in rows if r["recommendation"]]

    lines = [f"VENDOR HISTORY ({len(rows)} prior contract(s) for '{vendor_name}'):"]
    if governing_laws:
        unique_gl = list(dict.fromkeys(governing_laws))
        lines.append(f"  - Governing law seen before: {', '.join(unique_gl[:3])}")
    if payment_terms:
        unique_pt = list(dict.fromkeys(payment_terms))
        lines.append(f"  - Payment terms seen before: {', '.join(unique_pt[:3])}")
    if prior_decisions:
        lines.append(f"  - Prior AI decisions: {', '.join(prior_decisions[:4])}")

    # Human override decisions — most important signal
    for r in rows:
        if r.get("human_decision"):
            ai  = r.get("recommendation") or "unknown"
            hum = r["human_decision"]
            reason = r.get("human_reasoning") or ""
            role   = r.get("human_reviewer") or "reviewer"
            override_line = (
                f"  - HUMAN OVERRIDE ({role}): AI recommended {ai} → "
                f"human decided {hum}"
            )
            if reason:
                # Truncate long reasons to keep the prompt focused
                override_line += f'. Reason: "{reason[:200]}"'
            lines.append(override_line)

    lines.append(
        "If the current contract's governing law or payment terms differ significantly "
        "from the above, note it explicitly in the summary field. "
        "If a human reviewer previously overrode the AI decision for this vendor, "
        "factor their stated reason into your assessment."
    )
    return "\n".join(lines)


# ── Agent 3 — Compliance: vendor compliance track record ─────────────────────

def get_vendor_compliance_history(db: Session, vendor_name: str) -> str:
    """Return a prompt snippet of this vendor's past compliance results.

    Lets Agent 3 say 'this vendor has previously failed GDPR 3 times' rather
    than treating each upload as if the vendor is new.
    """
    rows = _agent_outputs_for_vendor(db, vendor_name, "compliance", limit=5)
    if not rows:
        return ""

    framework_failures: dict[str, int] = {}
    framework_passes:   dict[str, int] = {}
    critical_gaps: list[str] = []

    for r in rows:
        for fw in (r["output"].get("frameworks") or []):
            fw_name = fw.get("framework", "?")
            if fw.get("passed"):
                framework_passes[fw_name]   = framework_passes.get(fw_name, 0) + 1
            else:
                framework_failures[fw_name] = framework_failures.get(fw_name, 0) + 1
                for chk in (fw.get("checks") or []):
                    if not chk.get("present") and chk.get("severity") == "Critical":
                        req = chk.get("requirement", "?")
                        if req not in critical_gaps:
                            critical_gaps.append(req)

    if not framework_failures and not framework_passes:
        return ""

    lines = [f"VENDOR COMPLIANCE HISTORY ({len(rows)} prior submission(s) for '{vendor_name}'):"]
    for fw, n in sorted(framework_failures.items(), key=lambda x: -x[1]):
        lines.append(f"  - {fw}: FAILED {n} time(s) in prior submissions")
    for fw, n in sorted(framework_passes.items(), key=lambda x: -x[1]):
        lines.append(f"  - {fw}: Passed {n} time(s) in prior submissions")
    if critical_gaps:
        lines.append(f"  - Recurring critical gaps: {'; '.join(critical_gaps[:5])}")

    # Human override decisions — surface reviewer judgements to the compliance LLM
    for r in rows:
        if r.get("human_decision"):
            ai  = r.get("recommendation") or "unknown"
            hum = r["human_decision"]
            reason = r.get("human_reasoning") or ""
            role   = r.get("human_reviewer") or "reviewer"
            override_line = (
                f"  - HUMAN OVERRIDE ({role}): AI recommended {ai} → "
                f"human decided {hum}"
            )
            if reason:
                override_line += f'. Reviewer note: "{reason[:300]}"'
            lines.append(override_line)

    lines.append(
        "Use this history to calibrate your assessment — recurring failures "
        "for the same vendor on the same requirements should be rated more severely. "
        "If a human reviewer explicitly approved a prior contract despite compliance gaps, "
        "note their reason but still flag any unresolved requirements as findings."
    )
    return "\n".join(lines)


# ── Agent 5 — Recommendation: feedback-informed rationale ────────────────────

def get_feedback_context(db: Session, vendor_name: str) -> dict[str, Any]:
    """Return scoring feedback patterns to inform Agent 5's rationale.

    Returns:
        {
          "global_suggestion": str | None,   — e.g. "scores tend to be too high"
          "vendor_pattern":    str | None,   — e.g. "this vendor scored too low twice"
          "total_feedback":    int,
        }
    """
    result: dict[str, Any] = {
        "global_suggestion": None,
        "vendor_pattern":    None,
        "total_feedback":    0,
    }
    try:
        from backend.models import ScoringFeedback
        from sqlalchemy import func

        all_fb = db.query(ScoringFeedback).all()
        result["total_feedback"] = len(all_fb)

        if len(all_fb) >= 5:
            too_high = sum(1 for f in all_fb if f.feedback_type == "too_high")
            too_low  = sum(1 for f in all_fb if f.feedback_type == "too_low")
            total    = len(all_fb)
            if too_high / total > 0.5:
                result["global_suggestion"] = (
                    "Reviewers have historically found AI scores too HIGH — "
                    "apply stricter scrutiny before recommending auto-approval."
                )
            elif too_low / total > 0.5:
                result["global_suggestion"] = (
                    "Reviewers have historically found AI scores too LOW — "
                    "the composite score may be conservative for this contract type."
                )

        # Vendor-specific feedback
        if vendor_name and vendor_name.lower() != "unknown":
            vendor_fb = [
                f for f in all_fb
                if vendor_name.lower()[:15] in (f.notes or "").lower()
                or vendor_name.lower()[:15] in (f.ai_decision or "").lower()
            ]
            if vendor_fb:
                vh = sum(1 for f in vendor_fb if f.feedback_type == "too_high")
                vl = sum(1 for f in vendor_fb if f.feedback_type == "too_low")
                if vh > vl:
                    result["vendor_pattern"] = f"Reviewer feedback for '{vendor_name}': scores have previously been marked too high ({vh}x)."
                elif vl > vh:
                    result["vendor_pattern"] = f"Reviewer feedback for '{vendor_name}': scores have previously been marked too low ({vl}x)."

            # Surface the most recent human override reason for this vendor
            overrides = [
                f for f in vendor_fb
                if f.feedback_type in ("too_high", "too_low") and f.notes
            ]
            if overrides:
                latest = sorted(overrides, key=lambda f: f.created_at, reverse=True)[0]
                result["last_human_override_reason"] = (
                    f"{latest.reviewer_role} changed {latest.ai_decision} → "
                    f"{latest.human_decision}: \"{(latest.notes or '')[:200]}\""
                )
    except Exception:
        logger.exception("history: failed to load feedback context (non-fatal)")
    return result
