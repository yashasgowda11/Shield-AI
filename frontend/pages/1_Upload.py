"""Upload page — wires the file picker to the backend.

Renders, after upload:
  - Quarantined → red panel with the matched injection text
  - Extracted   → progress bar while agents run in background, then results

Only shows results of the currently uploaded file.
Recent uploads have their own page (2_Recent_Uploads).
"""
import json
import sys
import time
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

import streamlit as st
from utils import (
    api_get, api_post, api_delete, can, current_role, gate,
    render_file_preview, get_service_status, render_topbar, setup_sidebar,
)

st.set_page_config(page_title="Upload Contract — Shield AI", page_icon="📄", layout="wide")
setup_sidebar()
render_topbar("Upload Contract", "📄")

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
    "pipeline_failed": "⚫",
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


# ---- Shared constants ----

# Terminal statuses: pipeline is done (success or human decision)
_PIPELINE_DONE = {
    "processed", "pipeline_failed", "manager_review", "legal_review",
    "approved", "rejected", "quarantined",
}
# How long to poll before giving up (seconds)
_POLL_TIMEOUT = 180
_POLL_INTERVAL = 3  # seconds between status checks


def _poll_until_done(contract_id: int) -> dict:
    """Poll GET /contracts/{id} until the pipeline finishes or timeout."""
    stages = [
        ("🪤 Agent 4 — Security gate scanning clauses (Lobster Trap)…", 0.10),
        ("🔍 Agent 1 — Extracting parties, dates, obligations…",        0.30),
        ("⚠️  Agent 2 — Assessing clause-level risk…",                  0.55),
        ("📋 Agent 3 — Checking compliance frameworks…",                 0.75),
        ("🎯 Agent 5 — Generating approval recommendation…",             0.92),
        ("⏳ Finalising…",                                               0.97),
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
    """Render agent outputs for a successfully processed contract.

    body may be a fresh upload response or a duplicate stub — fall back to
    detail (fetched from GET /contracts/{id}) for metrics when body is sparse.
    """
    st.success(f"✅  Pipeline complete (status: **{detail['status']}**)")
    c1, c2, c3 = st.columns(3)
    clauses = detail.get("clauses") or []
    raw_text = detail.get("raw_text") or ""
    c1.metric("Clauses", body.get("n_clauses", len(clauses)))
    c2.metric("Characters", f"{body.get('char_count', len(raw_text)):,}")
    c3.metric("Document type", (body.get("metadata") or {}).get("type", "?"))

    # ---- File preview ----
    with st.expander("📄  Preview original document", expanded=False):
        render_file_preview(
            contract_id=body["id"],
            filename=body["filename"],
            raw_text=detail.get("raw_text"),
        )

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


# ── LT status banner (always shown) ──────────────────────────────────────────
_svc = get_service_status()
_lt_online = _svc.get("lt", {}).get("available", False)
if not _lt_online:
    st.warning(
        "⚠️ **Lobster Trap (primary security layer) is currently offline.** "
        "Uploads will be scanned by the offline pattern detector only. "
        "Lobster Trap provides: prompt injection DPI, credential leak detection, "
        "role impersonation detection, and data exfiltration pattern analysis."
    )


# ── Helper: render quarantine events ─────────────────────────────────────────

def _render_quarantine(body: dict) -> None:
    scan_info = body.get("security_scan", {})
    lt_used = scan_info.get("lt_used", False)
    layer_parts = (["🪤 **Lobster Trap**"] if lt_used else []) + ["🧱 **Offline detector**"]
    st.error("🚨 Contract quarantined by the pre-LLM security gate")
    st.caption(
        f"Suspicious content detected **before any LLM was called**. "
        f"Layers active: {' · '.join(layer_parts)}."
    )
    events = body.get("security_events", [])
    _SEV_ICON = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}
    for ev in events:
        d = ev.get("details") or {}
        source = d.get("source", "offline_detector")
        sev = ev.get("severity", "high")
        with st.expander(
            f"{_SEV_ICON.get(sev,'⚪')} **{ev['event_type']}**  ·  severity: {sev}",
            expanded=True,
        ):
            if d.get("matched_text"):
                st.code(d["matched_text"], language="text")
            if d.get("deny_message"):
                st.code(d["deny_message"], language="text")
            if d.get("description"):
                st.info(d["description"])


# ── Tabs: Single / Bulk ───────────────────────────────────────────────────────

tab_single, tab_bulk = st.tabs(["📄 Single upload", "📦 Bulk upload"])


# ════════════════════════════════════════════════════════════════════════════
# TAB 1 — Single upload (existing behaviour, unchanged)
# ════════════════════════════════════════════════════════════════════════════

with tab_single:
    uploaded = st.file_uploader(
        "Drop a PDF or DOCX here",
        type=["pdf", "docx"],
        help="Pipeline: Security Gate → Agent 1 (Extraction) → Agent 2 (Risk) → "
             "Agent 3 (Compliance) → Agent 5 (Recommendation)",
        key="single_uploader",
    )

    if not _lt_online and uploaded is not None:
        _lt_consent = st.checkbox(
            "I understand Lobster Trap is offline. Proceed with offline detector only.",
            key="lt_single_consent",
        )
        if not _lt_consent:
            st.info("Check the box above to proceed.")
            st.stop()

    if uploaded is not None:
        mime = (
            "application/pdf"
            if uploaded.name.lower().endswith(".pdf")
            else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
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

        if body["status"] == "duplicate":
            st.warning(
                f"⚠️ **This file has already been uploaded.**\n\n"
                f"Identical to **{body['existing_filename']}** "
                f"(Contract #{body['id']}, uploaded {(body.get('uploaded_at') or '')[:19].replace('T',' ')} UTC).\n\n"
                f"Current status: **{body['existing_status']}**"
            )
            st.info("Showing the existing report below — no re-processing needed.")
            detail = api_get(f"/contracts/{body['id']}").json()
            if detail.get("status") == "extracted":
                detail = _poll_until_done(body["id"])
            _render_results(body, detail)

        elif body["status"] == "quarantined":
            _render_quarantine(body)

        else:
            scan_info = body.get("security_scan", {})
            scanner_line = (
                "🪤 Lobster Trap + 🧱 Offline detector"
                if scan_info.get("lt_used")
                else "🧱 Offline detector _(Lobster Trap not reachable — using fallback)_"
            )
            st.success(
                f"✅ Security gate cleared — **{body.get('n_clauses','?')} clauses** extracted.  \n"
                f"Scanned by: {scanner_line}"
            )
            st.info("AI agents are now running in the background…")
            detail = _poll_until_done(body["id"])
            if detail.get("status") in _PIPELINE_DONE - {"quarantined"}:
                _render_results(body, detail)
            elif detail.get("status") == "quarantined":
                st.error("Contract was quarantined during agent processing.")
            else:
                st.warning(
                    f"Pipeline still running (status: **{detail.get('status')}**). "
                    "Track progress in the **Review Queue**."
                )


# ════════════════════════════════════════════════════════════════════════════
# TAB 2 — Bulk upload
# ════════════════════════════════════════════════════════════════════════════

with tab_bulk:
    st.markdown(
        "<div style='background:#0D1628;border:1px solid #212C4D;border-radius:10px;"
        "padding:0.9rem 1.1rem;margin-bottom:1rem;'>"
        "<span style='color:#7E89AC;font-size:0.82rem;'>"
        "📦 Upload up to <strong style='color:#fff;'>20 contracts</strong> at once. "
        "Each file goes through the full pipeline independently — "
        "one failure does not block the others. "
        "Track processing progress in the <strong style='color:#6C72FF;'>Review Queue</strong>."
        "</span></div>",
        unsafe_allow_html=True,
    )

    bulk_files = st.file_uploader(
        "Drop up to 20 PDF or DOCX files here",
        type=["pdf", "docx"],
        accept_multiple_files=True,
        help="Each file is processed independently through the full AI pipeline.",
        key="bulk_uploader",
    )

    if not _lt_online and bulk_files:
        _lt_bulk_consent = st.checkbox(
            "I understand Lobster Trap is offline. Proceed with offline detector only.",
            key="lt_bulk_consent",
        )
        if not _lt_bulk_consent:
            st.info("Check the box above to proceed.")

    _can_upload_bulk = bool(bulk_files) and (_lt_online or st.session_state.get("lt_bulk_consent", False))

    if bulk_files:
        if len(bulk_files) > 20:
            st.error("Maximum 20 files per bulk upload. Please remove some files.")
        else:
            st.caption(f"{len(bulk_files)} file(s) selected.")

    if _can_upload_bulk and len(bulk_files) <= 20:
        if st.button(
            f"🚀 Upload & process all {len(bulk_files)} file(s)",
            type="primary",
            key="bulk_submit",
        ):
            # Build multipart payload
            files_payload = []
            for f in bulk_files:
                mime = (
                    "application/pdf"
                    if f.name.lower().endswith(".pdf")
                    else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                )
                files_payload.append(("files", (f.name, f.getvalue(), mime)))

            with st.spinner(f"Uploading {len(bulk_files)} file(s) and running security gates…"):
                import requests, os
                BACKEND = os.getenv("BACKEND_URL", "http://localhost:8000")
                try:
                    resp = requests.post(
                        f"{BACKEND}/contracts/bulk-upload",
                        files=files_payload,
                        data={"actor": f"user:{current_role()}"},
                        timeout=120,
                    )
                    bulk_resp = resp.json() if resp.ok else None
                except Exception as exc:
                    st.error(f"Bulk upload request failed: {exc}")
                    bulk_resp = None

            if bulk_resp is None:
                st.error("Backend did not return a valid response.")
            else:
                # ── Summary banner ────────────────────────────────────────────
                total      = bulk_resp.get("total", 0)
                queued     = bulk_resp.get("queued", 0)
                duplicates = bulk_resp.get("duplicates", 0)
                quarantine = bulk_resp.get("quarantined", 0)
                errors     = bulk_resp.get("errors", 0)

                if queued == total:
                    st.success(f"✅ All {total} files uploaded and queued for AI processing.")
                elif queued > 0:
                    st.warning(
                        f"⚠️ {queued}/{total} files queued. "
                        f"{duplicates} duplicate(s) · {quarantine} quarantined · {errors} error(s)."
                    )
                else:
                    st.error(f"No files were queued. {quarantine} quarantined · {errors} error(s).")

                summary_cols = st.columns(4)
                summary_cols[0].metric("Queued for AI", queued)
                summary_cols[1].metric("Duplicates", duplicates)
                summary_cols[2].metric("Quarantined 🚨", quarantine)
                summary_cols[3].metric("Errors", errors)

                # ── Per-file results table ────────────────────────────────────
                st.markdown("### Results per file")

                _STATUS_ICON = {
                    "extracted":         "🟡 Processing…",
                    "duplicate":         "🔄 Duplicate",
                    "quarantined":       "🚨 Quarantined",
                    "extraction_failed": "⚫ Extraction failed",
                    "error":             "❌ Error",
                }

                for res in bulk_resp.get("results", []):
                    fname   = res.get("filename", "?")
                    status  = res.get("status", "error")
                    cid     = res.get("id")
                    msg     = res.get("message", "")
                    n_cls   = res.get("n_clauses")

                    icon_label = _STATUS_ICON.get(status, f"🟡 {status}")

                    with st.container(border=True):
                        row_l, row_r = st.columns([5, 2])
                        with row_l:
                            st.markdown(
                                f"<span style='font-weight:600;color:#fff;'>{fname}</span>  "
                                f"<span style='color:#7E89AC;font-size:0.8rem;'>{icon_label}</span>",
                                unsafe_allow_html=True,
                            )
                            if msg and status not in ("extracted",):
                                st.caption(msg)
                            if n_cls is not None:
                                st.caption(f"{n_cls} clauses extracted")
                        with row_r:
                            if cid and status not in ("error",):
                                st.markdown(
                                    f"<span style='font-size:0.78rem;color:#7E89AC;'>"
                                    f"Contract #{cid}</span>",
                                    unsafe_allow_html=True,
                                )
                            if status == "quarantined":
                                with st.expander("Security events"):
                                    for ev in (res.get("security_events") or []):
                                        st.caption(
                                            f"🔴 {ev.get('event_type')} · {ev.get('severity')}"
                                        )

                # ── Polling progress for queued files ─────────────────────────
                queued_ids = [
                    r["id"] for r in bulk_resp.get("results", [])
                    if r.get("status") == "extracted" and r.get("id")
                ]
                if queued_ids:
                    st.markdown("---")
                    st.info(
                        f"⏳ **{len(queued_ids)} file(s) are being processed by AI agents.** "
                        "Go to the **Review Queue** to monitor progress and take action when ready. "
                        "You don't need to stay on this page."
                    )
                    if st.button("🔄 Check processing status now", key="bulk_poll"):
                        still_running = []
                        done = []
                        for cid in queued_ids:
                            d = api_get(f"/contracts/{cid}").json()
                            if d.get("status") in _PIPELINE_DONE:
                                done.append((cid, d.get("status"), d.get("filename", "")))
                            else:
                                still_running.append(cid)
                        if done:
                            st.success(f"✅ {len(done)} file(s) finished processing:")
                            for cid, st_val, fn in done:
                                st.caption(f"  • #{cid} {fn} → **{st_val}**")
                        if still_running:
                            st.warning(
                                f"⏳ {len(still_running)} file(s) still processing "
                                f"(IDs: {still_running}). Check again in a moment."
                            )

# ── Hint to navigate to Recent Uploads ───────────────────────────────────────
st.markdown("<div style='height:1.5rem'></div>", unsafe_allow_html=True)
st.markdown(
    "<div style='background:#101935;border:1px solid #212C4D;border-radius:12px;"
    "padding:1rem 1.25rem;'>"
    "<span style='color:#7E89AC;font-size:0.85rem;'>"
    "📂 Looking for past uploads? Go to <strong style='color:#6C72FF;'>Recent Uploads</strong> "
    "in the sidebar for a full table with in-depth analysis of any contract."
    "</span></div>",
    unsafe_allow_html=True,
)
