"""Upload page — wires the file picker to the backend.

Renders, after upload:
  - Quarantined → red panel with the matched injection text
  - Extracted   → progress bar while agents run in background, then results
"""
import json
import sys
import time
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

import streamlit as st
from utils import api_get, api_post, current_role, gate

st.title("📄 Upload Contract")
st.caption(f"Active role: **{current_role()}**")

gate("upload", "Only Procurement Analysts can upload contracts.")


SEVERITY_BADGE = {
    "Low": "🟢 Low",
    "Medium": "🟡 Medium",
    "High": "🟠 High",
    "Critical": "🔴 Critical",
}

STATUS_EMOJI = {
    "extracted": "🟡",
    "processed": "🟢",
    "quarantined": "🔴",
    "uploading": "🟡",
    "extraction_failed": "⚫",
    "approved": "✅",
    "rejected": "❌",
    "manager_review": "🟠",
    "legal_review": "🔵",
}

RECOMMENDATION_BADGE = {
    "AUTO_APPROVE": ("✅ Auto-approve", "normal"),
    "MANAGER_REVIEW": ("🟠 Manager review", "off"),
    "LEGAL_REVIEW": ("🔵 Legal review", "off"),
    "REJECT": ("❌ Reject", "inverse"),
}


def render_extraction(block: dict) -> None:
    st.subheader("🤖  Agent 1 — Document Extraction")
    ex = block["output"]
    colA, colB = st.columns(2)
    with colA:
        st.markdown("**Parties**")
        for p in ex.get("parties", []):
            st.write(f"- **{p['name']}**  ·  {p['role']}")
        st.markdown(f"**Effective date:** {ex.get('effective_date') or '_not stated_'}")
        st.markdown(f"**Term:** {ex.get('term') or '_not stated_'}")
    with colB:
        st.markdown(f"**Payment terms:** {ex.get('payment_terms') or '_n/a_'}")
        st.markdown(f"**Governing law:** {ex.get('governing_law') or '_not stated_'}")
        st.caption(
            f"Prompt hash: `{block.get('prompt_hash', '?')}`  ·  "
            f"captured {(block.get('created_at') or '')[:19]}"
        )

    st.markdown("**Summary**")
    st.info(ex.get("summary", "_(no summary)_"))

    obligations = ex.get("obligations") or []
    if obligations:
        st.markdown(f"**Obligations** ({len(obligations)})")
        for o in obligations:
            ref = f" §{o['clause_ref']}" if o.get("clause_ref") else ""
            st.write(f"- **{o['party']}**{ref}: {o['description']}")


def render_risk(block: dict) -> None:
    st.subheader("⚠️  Agent 2 — Risk Assessment")
    risk = block["output"]
    score = risk.get("score", 0)
    findings = risk.get("findings") or []

    if score >= 61:
        delta_label, delta_color = "HIGH risk · legal review", "inverse"
    elif score >= 31:
        delta_label, delta_color = "MODERATE · manager review", "off"
    else:
        delta_label, delta_color = "LOW · auto-approve eligible", "normal"

    c1, c2 = st.columns([1, 3])
    c1.metric("Score", f"{score}/100", delta=delta_label, delta_color=delta_color)
    c2.markdown(
        "Score is grounded in retrieved comparators from past contracts "
        "(see _Similar prior clauses_ panel below)."
    )

    if not findings:
        st.success("No material risks identified.")
        return

    st.markdown(f"**Findings ({len(findings)})**")
    for f in findings:
        with st.expander(
            f"{SEVERITY_BADGE.get(f['severity'], f['severity'])}  ·  "
            f"{f['risk']}  ·  §{f.get('clause_ref', '?')}",
            expanded=f.get("severity") in {"High", "Critical"},
        ):
            st.write(f.get("reasoning", ""))
    st.caption(f"Prompt hash: `{block.get('prompt_hash', '?')}`")


def render_compliance(block: dict) -> None:
    st.subheader("📋  Agent 3 — Compliance")
    comp = block["output"]
    frameworks = comp.get("frameworks") or []

    cols = st.columns(len(frameworks)) if frameworks else []
    for col, fw in zip(cols, frameworks):
        emoji = "✅" if fw.get("passed") else "❌"
        n_checks = len(fw.get("checks") or [])
        n_failed = sum(1 for c in (fw.get("checks") or []) if not c.get("present"))
        col.metric(
            f"{emoji} {fw['framework']}",
            "PASSED" if fw.get("passed") else "FAILED",
            delta=f"{n_checks - n_failed}/{n_checks} requirements met",
            delta_color="normal" if fw.get("passed") else "inverse",
        )

    for fw in frameworks:
        with st.expander(
            f"{fw['framework']}  ·  {'PASSED' if fw.get('passed') else 'FAILED'}",
            expanded=not fw.get("passed"),
        ):
            for check in fw.get("checks") or []:
                icon = "✓" if check.get("present") else "✗"
                sev = SEVERITY_BADGE.get(check.get("severity", "Medium"), "")
                st.markdown(f"**{icon} {check['requirement']}**  ·  {sev}")
                if check.get("present"):
                    if check.get("evidence_quote"):
                        st.code(check["evidence_quote"], language="text")
                else:
                    st.write(f"_Gap:_ {check.get('gap_description', '(no detail)')}")
    st.caption(f"Prompt hashes: `{block.get('prompt_hash', '?')}`")


# ---- Upload widget ----

# Terminal statuses: pipeline is done (success or human decision)
_PIPELINE_DONE = {
    "processed", "manager_review", "legal_review",
    "approved", "rejected", "quarantined",
}
# How long to poll before giving up (seconds)
_POLL_TIMEOUT = 180
_POLL_INTERVAL = 3  # seconds between status checks


def _poll_until_done(contract_id: int) -> dict:
    """Poll GET /contracts/{id} until the pipeline finishes or timeout."""
    stages = [
        ("🔍 Agent 1 — Extracting parties, dates, obligations…", 0.20),
        ("⚠️  Agent 2 — Assessing clause-level risk…",          0.45),
        ("📋 Agent 3 — Checking compliance frameworks…",         0.70),
        ("🎯 Agent 5 — Generating approval recommendation…",     0.90),
        ("⏳ Finalising…",                                        0.95),
    ]
    stage_idx = 0
    elapsed = 0

    status_text = st.empty()
    prog_bar = st.progress(0.05)

    while elapsed < _POLL_TIMEOUT:
        detail = api_get(f"/contracts/{contract_id}").json()
        current = detail.get("status", "")

        if current in _PIPELINE_DONE:
            prog_bar.progress(1.0)
            status_text.empty()
            return detail

        # Advance the displayed stage message
        if stage_idx < len(stages):
            label, frac = stages[stage_idx]
            status_text.info(label)
            prog_bar.progress(frac)
            stage_idx += 1

        time.sleep(_POLL_INTERVAL)
        elapsed += _POLL_INTERVAL

    # Timed out — return whatever we have
    prog_bar.progress(1.0)
    status_text.warning(
        "⏰ Agents are taking longer than expected. "
        "Check the **Review Queue** in a minute."
    )
    return api_get(f"/contracts/{contract_id}").json()


def _render_results(body: dict, detail: dict) -> None:
    """Render agent outputs for a successfully processed contract."""
    st.success(f"✅  Pipeline complete (status: **{detail['status']}**)")
    c1, c2, c3 = st.columns(3)
    c1.metric("Clauses", body["n_clauses"])
    c2.metric("Characters", f"{body['char_count']:,}")
    c3.metric("Document type", body["metadata"].get("type", "?"))

    agent_outputs = detail.get("agent_outputs") or {}

    if "extraction" in agent_outputs:
        render_extraction(agent_outputs["extraction"])

    if "risk" in agent_outputs:
        render_risk(agent_outputs["risk"])

    if "compliance" in agent_outputs:
        render_compliance(agent_outputs["compliance"])

    # Agent 5 — recommendation (rules-based, deterministic)
    decisions = detail.get("decisions") or []
    ai_decision = next(
        (d for d in decisions if (d.get("reviewer_role") or "").startswith("agent:")),
        None,
    )
    if ai_decision:
        st.subheader("🎯  Agent 5 — Approval Recommendation")
        label, color = RECOMMENDATION_BADGE.get(
            ai_decision["recommendation"],
            (ai_decision["recommendation"], "off"),
        )
        c1, c2 = st.columns([1, 3])
        c1.metric("Recommendation", label, delta_color=color)
        c2.info(ai_decision.get("reasoning") or "")
        st.caption(
            "Decision is **rules-based** — no LLM in the approval path. "
            "Reasoning text is templated."
        )

    # Extracted clauses (for reference)
    st.subheader("📑  Extracted clauses")
    for clause in detail.get("clauses") or []:
        with st.expander(f"§ {clause['number']}  —  {clause['title']}"):
            st.write(clause["text"] or "_(empty)_")

    # Audit-ready report download
    st.subheader("📋  Audit report")
    try:
        report = api_get(f"/contracts/{body['id']}/audit-report").json()
        st.download_button(
            "📥 Download audit report (JSON)",
            data=json.dumps(report, indent=2),
            file_name=f"shield_audit_contract_{body['id']}.json",
            mime="application/json",
            help="Compiled audit-ready report — every agent prompt hash, "
                 "every decision, every security event, every audit log entry.",
        )
        with st.expander("Preview report contents"):
            st.json(report)
    except Exception as e:
        st.caption(f"Audit report unavailable: {e}")


uploaded = st.file_uploader(
    "Drop a PDF or DOCX here",
    type=["pdf", "docx"],
    help="Pipeline: extract → security gate → segment → Agents 1/2/3/5 (async).",
)

if uploaded is not None:
    mime = (
        "application/pdf"
        if uploaded.name.lower().endswith(".pdf")
        else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )

    # Step 1: upload + security gate (~4s)
    with st.spinner(f"Uploading **{uploaded.name}** and running security gate…"):
        r = api_post(
            "/contracts/upload",
            files={"file": (uploaded.name, uploaded.getvalue(), mime)},
            data={"actor": f"user:{current_role()}"},
        )

    if r.status_code != 200:
        st.error(f"Upload failed (HTTP {r.status_code})")
        try:
            st.json(r.json())
        except Exception:
            st.code(r.text)
        st.stop()

    body = r.json()

    # ---- Quarantined ----
    if body["status"] == "quarantined":
        st.error("🚨  Contract quarantined by the pre-LLM security gate")
        st.caption(
            "Suspicious content was detected **before any LLM was called**. "
            "This contract will not be processed further."
        )
        st.subheader("Detected events")
        for ev in body["security_events"]:
            with st.expander(
                f"⚠️  {ev['event_type']}  ·  severity: {ev['severity']}",
                expanded=True,
            ):
                d = ev["details"]
                if d.get("matched_text"):
                    st.markdown(f"**Matched text:** `{d['matched_text']}`")
                if d.get("confidence") is not None:
                    st.markdown(f"**Confidence:** {d['confidence']}")
                if d.get("context"):
                    st.markdown("**Context:**")
                    st.code(d["context"])
                if d.get("description"):
                    st.markdown(f"**Notes:** {d['description']}")

    # ---- Clean — poll while agents run in background ----
    else:
        st.info(
            f"✅ Security gate passed — **{body['n_clauses']} clauses** extracted. "
            "AI agents are now running in the background…"
        )

        # Step 2: poll until agents finish
        detail = _poll_until_done(body["id"])

        if detail.get("status") in _PIPELINE_DONE - {"quarantined"}:
            _render_results(body, detail)
        elif detail.get("status") == "quarantined":
            # Shouldn't happen (gate already passed), but handle defensively
            st.error("Contract was quarantined during agent processing.")
        else:
            st.warning(
                f"Pipeline still running (status: **{detail.get('status')}**). "
                "You can track progress in the **Review Queue**."
            )

# ---- Recent uploads ----
st.divider()
st.subheader("Recent uploads")

try:
    contracts = api_get("/contracts/").json()
except Exception as e:
    st.warning(f"Couldn't reach backend: {e}")
    contracts = []

if not contracts:
    st.caption("No contracts uploaded yet.")
else:
    for c in contracts[:10]:
        cols = st.columns([3, 2, 2, 2])
        cols[0].write(f"**{c['filename']}**")
        cols[1].write(f"{STATUS_EMOJI.get(c['status'], '⚪')} {c['status']}")
        cols[2].write(f"{c['n_clauses']} clauses")
        cols[3].caption((c["uploaded_at"] or "")[:19].replace("T", " "))
