"""Contract Detail — in-depth analysis of a single contract.

Navigated to from Recent Uploads via st.switch_page().
Reads `st.session_state["view_contract_id"]` to determine which contract to show.
"""
import json
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

import streamlit as st
from utils import api_get, render_file_preview, render_topbar, setup_sidebar
from style import apply_theme, status_pill, score_color, score_bar_html
from score_descriptions import AGENT_SCORES, SEVERITY

st.set_page_config(page_title="Contract Detail — Shield AI", page_icon="📋", layout="wide")
setup_sidebar()

# ── Check we were navigated here with a contract_id ──────────────────────────
contract_id = st.session_state.get("view_contract_id")
if contract_id is None:
    apply_theme()
    st.markdown(
        "<div style='text-align:center;padding:4rem;'>"
        "<div style='font-size:3rem;margin-bottom:1rem;'>📋</div>"
        "<div style='font-size:1.1rem;font-weight:600;color:#FFFFFF;margin-bottom:0.5rem;'>"
        "No contract selected</div>"
        "<div style='color:#7E89AC;'>Navigate here from <strong>Recent Uploads</strong> "
        "by clicking a contract name.</div>"
        "</div>",
        unsafe_allow_html=True,
    )
    if st.button("← Go to Recent Uploads"):
        st.switch_page("pages/2_Recent_Uploads.py")
    st.stop()

# ── Fetch contract detail ─────────────────────────────────────────────────────
try:
    detail = api_get(f"/contracts/{contract_id}").json()
except Exception as e:
    apply_theme()
    st.error(f"Cannot reach backend: {e}")
    st.stop()

# ── Top bar ───────────────────────────────────────────────────────────────────
render_topbar(detail.get("filename", f"Contract #{contract_id}"), "📋")

# Back navigation
if st.button("← Back to Recent Uploads", key="back_btn"):
    st.switch_page("pages/2_Recent_Uploads.py")

st.markdown("<div style='height:0.5rem'></div>", unsafe_allow_html=True)

# ── Header card ───────────────────────────────────────────────────────────────
decisions = detail.get("decisions") or []
ai_dec = next(
    (d for d in decisions if (d.get("reviewer_role") or "").startswith("agent:")),
    None,
)
scoring_details = (ai_dec or {}).get("scoring_details") or {}
composite = scoring_details.get("composite_score")

agent_outputs = detail.get("agent_outputs") or {}
risk_out  = agent_outputs.get("risk",       {}).get("output", {})
comp_out  = agent_outputs.get("compliance", {}).get("output", {})
extr_out  = agent_outputs.get("extraction", {}).get("output", {})

# Status strip
status = detail.get("status", "unknown")
rec    = (ai_dec or {}).get("recommendation", "")

h1, h2, h3, h4 = st.columns([3, 1, 1, 1])
with h1:
    st.markdown(
        f"<div style='background:#101935;border:1px solid #212C4D;border-radius:14px;"
        f"padding:1.25rem 1.5rem;'>"
        f"<div style='font-size:0.72rem;color:#7E89AC;font-weight:600;text-transform:uppercase;"
        f"letter-spacing:0.06em;margin-bottom:0.35rem;'>Contract</div>"
        f"<div style='font-size:1.1rem;font-weight:700;color:#FFFFFF;margin-bottom:0.5rem;'>"
        f"{detail.get('filename', '—')}</div>"
        f"<div>{status_pill(status)}</div>"
        f"</div>",
        unsafe_allow_html=True,
    )
with h2:
    st.metric(
        "Composite score",
        f"{composite:.0f}/100" if composite is not None else "—",
        help=AGENT_SCORES["composite"]["description"],
    )
with h3:
    risk_score = risk_out.get("score", 0)
    st.metric("Risk score", f"{risk_score}/100",
              help=AGENT_SCORES["agent2_risk"]["description"])
with h4:
    n_findings = len(risk_out.get("findings") or [])
    n_critical = sum(1 for f in (risk_out.get("findings") or []) if f.get("severity") == "Critical")
    st.metric("Findings", f"{n_findings}", delta=f"{n_critical} critical" if n_critical else "0 critical",
              delta_color="inverse" if n_critical else "off")

st.markdown("<div style='height:0.75rem'></div>", unsafe_allow_html=True)

# ── Tabs ──────────────────────────────────────────────────────────────────────
tab_score, tab_extract, tab_risk, tab_compliance, tab_preview, tab_audit = st.tabs([
    "📊 Score Breakdown",
    "📄 Extraction",
    "⚠️ Risk",
    "📋 Compliance",
    "👁️ Preview",
    "📥 Audit Report",
])

# ── Score Breakdown ───────────────────────────────────────────────────────────
with tab_score:
    if not scoring_details:
        st.info(
            "Detailed scoring breakdown is not available for this contract. "
            "It may have been processed before the scoring engine was upgraded. "
            "Use **Scoring Policy → Rescore** to regenerate."
        )
    else:
        # Composite score bar
        st.markdown(
            f"<div style='background:#101935;border:1px solid #212C4D;border-radius:14px;"
            f"padding:1.5rem;margin-bottom:1rem;'>"
            f"<div style='font-size:0.72rem;color:#7E89AC;font-weight:600;text-transform:uppercase;"
            f"letter-spacing:0.06em;margin-bottom:0.75rem;'>Composite Approval Score</div>"
            f"{score_bar_html(composite or 0)}"
            f"<div style='margin-top:0.75rem;font-size:0.82rem;color:#AEB9E1;'>"
            f"Formula: (100 − risk) × 50% + compliance × 35% + quality × 15%</div>"
            f"</div>",
            unsafe_allow_html=True,
        )

        sc1, sc2, sc3 = st.columns(3)
        with sc1:
            v = 100 - scoring_details.get("risk_score", 0)
            st.metric("Risk contribution", f"{v:.0f}/100",
                      help=AGENT_SCORES["agent2_risk"]["description"])
            st.markdown(
                score_bar_html(v),
                unsafe_allow_html=True,
            )
        with sc2:
            v = scoring_details.get("compliance_average", 0)
            st.metric("Compliance avg", f"{v:.0f}%",
                      help=AGENT_SCORES["agent3_compliance"]["description"])
            st.markdown(score_bar_html(v), unsafe_allow_html=True)
        with sc3:
            v = scoring_details.get("quality_score", 0)
            st.metric("Contract quality", f"{v:.0f}%",
                      help=AGENT_SCORES["agent1_quality"]["description"])
            st.markdown(score_bar_html(v), unsafe_allow_html=True)

        st.markdown("<div style='height:0.5rem'></div>", unsafe_allow_html=True)
        fc1, fc2 = st.columns(2)
        with fc1:
            n_crit = scoring_details.get("critical_findings", 0)
            st.metric("Critical findings", n_crit,
                      delta=f"-{n_crit}" if n_crit else None,
                      delta_color="inverse",
                      help=f"🔴 Critical — {SEVERITY['Critical']}")
        with fc2:
            n_high = scoring_details.get("high_findings", 0)
            st.metric("High findings", n_high,
                      delta=f"-{n_high}" if n_high else None,
                      delta_color="inverse",
                      help=f"🟠 High — {SEVERITY['High']}")

        triggered = scoring_details.get("triggered_rules") or []
        if triggered:
            st.markdown("**Triggered rules:**")
            for t in triggered:
                st.markdown(f"- `{t}`")

        rationale = scoring_details.get("rationale") or []
        if rationale:
            st.markdown("**Decision rationale:**")
            for line in rationale:
                st.markdown(f"- {line}")

        actions = scoring_details.get("required_actions") or []
        if actions:
            st.warning("**Required actions before approval:**")
            for a in actions:
                st.markdown(f"- ⚠️ {a}")

        # AI recommendation highlight
        if ai_dec:
            _REC_COLORS = {
                "AUTO_APPROVE":   "#22c55e",
                "MANAGER_REVIEW": "#FDB52A",
                "LEGAL_REVIEW":   "#57C3FF",
                "REJECT":         "#ef4444",
            }
            rcolor = _REC_COLORS.get(rec, "#7E89AC")
            st.markdown(
                f"<div style='background:rgba(0,0,0,0.15);border:1px solid {rcolor}33;"
                f"border-left:3px solid {rcolor};border-radius:10px;padding:1rem 1.25rem;"
                f"margin-top:0.5rem;'>"
                f"<span style='font-size:0.72rem;color:{rcolor};font-weight:700;"
                f"text-transform:uppercase;letter-spacing:0.07em;'>AI Recommendation</span>"
                f"<div style='font-size:1.1rem;font-weight:700;color:{rcolor};margin-top:0.25rem;'>"
                f"{rec}</div>"
                f"<div style='font-size:0.85rem;color:#AEB9E1;margin-top:0.35rem;'>"
                f"{ai_dec.get('reasoning', '')}</div>"
                f"</div>",
                unsafe_allow_html=True,
            )

# ── Extraction ────────────────────────────────────────────────────────────────
with tab_extract:
    if not extr_out:
        st.info("No extraction data available for this contract.")
    else:
        col_a, col_b = st.columns(2)
        with col_a:
            st.markdown("**Parties**")
            for p in extr_out.get("parties") or []:
                st.markdown(
                    f"<div style='background:#0D1628;border-radius:8px;padding:0.6rem 0.85rem;"
                    f"margin-bottom:0.4rem;font-size:0.85rem;'>"
                    f"<strong style='color:#FFFFFF;'>{p.get('name', '—')}</strong>"
                    f" <span style='color:#7E89AC;'>· {p.get('role', '')}</span></div>",
                    unsafe_allow_html=True,
                )
            st.markdown(f"**Effective date:** {extr_out.get('effective_date') or '_not stated_'}")
            st.markdown(f"**Term:** {extr_out.get('term') or '_not stated_'}")
        with col_b:
            st.markdown(f"**Payment terms:** {extr_out.get('payment_terms') or '_n/a_'}")
            st.markdown(f"**Governing law:** {extr_out.get('governing_law') or '_not stated_'}")

        st.markdown("**Summary**")
        st.info(extr_out.get("summary") or "_(no summary)_")

        obligations = extr_out.get("obligations") or []
        if obligations:
            st.markdown(f"**Obligations ({len(obligations)})**")
            for o in obligations:
                ref = f" §{o['clause_ref']}" if o.get("clause_ref") else ""
                st.markdown(f"- **{o.get('party','?')}**{ref}: {o.get('description','')}")

        # Clauses
        clauses = detail.get("clauses") or []
        if clauses:
            st.markdown(f"**Extracted clauses ({len(clauses)})**")
            for clause in clauses:
                with st.expander(f"§ {clause['number']} — {clause['title']}"):
                    st.write(clause.get("text") or "_(empty)_")

# ── Risk ──────────────────────────────────────────────────────────────────────
with tab_risk:
    if not risk_out:
        st.info("No risk assessment data available for this contract.")
    else:
        _SBADGE = {"Low": "🟢", "Medium": "🟡", "High": "🟠", "Critical": "🔴"}
        score = risk_out.get("score", 0)
        findings = risk_out.get("findings") or []

        sc_col, bar_col = st.columns([1, 3])
        sc_col.metric("Raw risk score", f"{score}/100",
                      help="0 = safe · 100 = extremely risky. This is INVERTED in the composite.")
        with bar_col:
            inv_score = 100 - score
            st.markdown(
                f"<div style='padding-top:0.8rem;'>"
                f"{score_bar_html(inv_score, 'Inverted contribution to composite')}</div>",
                unsafe_allow_html=True,
            )

        if not findings:
            st.success("No material risks identified.")
        else:
            st.markdown(f"**Findings ({len(findings)})**")
            # Group by severity
            for sev in ["Critical", "High", "Medium", "Low"]:
                sev_findings = [f for f in findings if f.get("severity") == sev]
                if not sev_findings:
                    continue
                st.markdown(
                    f"<div style='font-size:0.72rem;font-weight:700;color:#7E89AC;"
                    f"text-transform:uppercase;letter-spacing:0.07em;margin:0.75rem 0 0.35rem;'>"
                    f"{_SBADGE.get(sev,'•')} {sev} ({len(sev_findings)})</div>",
                    unsafe_allow_html=True,
                )
                for f in sev_findings:
                    with st.expander(
                        f"§{f.get('clause_ref', '?')} — {f.get('risk', '?')}",
                        expanded=(sev in {"Critical", "High"}),
                    ):
                        st.write(f.get("reasoning", ""))
                        st.caption(f"Severity: {sev} · {SEVERITY.get(sev, '')}")

# ── Compliance ────────────────────────────────────────────────────────────────
with tab_compliance:
    if not comp_out:
        st.info("No compliance data available for this contract.")
    else:
        frameworks = comp_out.get("frameworks") or []
        fw_cols = st.columns(len(frameworks)) if frameworks else []
        for col, fw in zip(fw_cols, frameworks):
            checks     = fw.get("checks") or []
            n_checks   = len(checks)
            n_passed   = sum(1 for c in checks if c.get("present"))
            n_failed   = n_checks - n_passed
            # Recompute passed from actual checks — don't trust the stored field
            # because older records may have been set incorrectly by the LLM.
            fw_passed  = (n_failed == 0) if checks else fw.get("passed", True)
            col.metric(
                f"{'✅' if fw_passed else '❌'} {fw['framework']}",
                "PASSED" if fw_passed else "FAILED",
                delta=f"{n_passed}/{n_checks} requirements met",
                delta_color="normal" if fw_passed else "inverse",
            )

        st.markdown("<div style='height:0.5rem'></div>", unsafe_allow_html=True)

        for fw in frameworks:
            checks    = fw.get("checks") or []
            fw_passed = all(c.get("present") for c in checks) if checks else fw.get("passed", True)
            with st.expander(
                f"{fw['framework']} — {'PASSED ✅' if fw_passed else 'FAILED ❌'}",
                expanded=not fw_passed,
            ):
                for check in fw.get("checks") or []:
                    icon = "✓" if check.get("present") else "✗"
                    sev  = check.get("severity", "Medium")
                    sbadge = {"Low":"🟢","Medium":"🟡","High":"🟠","Critical":"🔴"}.get(sev,"")
                    st.markdown(
                        f"**{icon} {check.get('requirement','?')}**  · {sbadge} {sev}"
                    )
                    if check.get("present") and check.get("evidence_quote"):
                        st.code(check["evidence_quote"], language="text")
                    elif not check.get("present"):
                        st.caption(f"Gap: {check.get('gap_description','(no detail)')}")

# ── Preview ───────────────────────────────────────────────────────────────────
with tab_preview:
    render_file_preview(
        contract_id=contract_id,
        filename=detail.get("filename", ""),
        raw_text=detail.get("raw_text"),
        key_suffix="detail",
    )

# ── Audit Report ──────────────────────────────────────────────────────────────
with tab_audit:
    try:
        report = api_get(f"/contracts/{contract_id}/audit-report").json()
        st.download_button(
            "📥 Download full audit report (JSON)",
            data=json.dumps(report, indent=2),
            file_name=f"shield_audit_contract_{contract_id}.json",
            mime="application/json",
            type="primary",
        )
        with st.expander("Preview report structure"):
            st.json(report)
    except Exception as e:
        st.warning(f"Audit report unavailable: {e}")

    # Decision history
    if decisions:
        st.markdown("**Decision history**")
        for d in decisions:
            role_icon = "🤖" if (d.get("reviewer_role") or "").startswith("agent:") else "👤"
            st.markdown(
                f"{role_icon} **{d.get('recommendation')}** — "
                f"by `{d.get('reviewer_role')}` at {(d.get('created_at') or '')[:19]}  \n"
                f"_{d.get('reasoning', '')}_"
            )
