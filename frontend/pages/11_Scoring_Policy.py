"""Scoring Policy — admin page for tuning the hybrid scoring engine.

Only visible to Admin and Legal Reviewer roles.

Shows:
  - Score breakdown formula
  - Weight sliders (risk / compliance / quality, must sum to 1.0)
  - Decision band thresholds (composite_min, critical_max, high_max)
  - Framework-specific hard rejection rules
  - Full change history
"""
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

import streamlit as st
from utils import api_get, api_post, current_role, render_topbar, setup_sidebar
from score_descriptions import AGENT_SCORES, POLICY_PARAMS, SEVERITY, FEEDBACK

SEVERITY_BADGE_POLICY = {"Low": "🟢", "Medium": "🟡", "High": "🟠", "Critical": "🔴"}

st.set_page_config(page_title="Scoring Policy — Shield AI", page_icon="⚖️", layout="wide")
setup_sidebar()

# ── Access control ────────────────────────────────────────────────────────────
ALLOWED_ROLES = {"Admin", "Legal Reviewer", "System Administrator"}
role = current_role()
if role not in ALLOWED_ROLES:
    from style import apply_theme
    apply_theme()
    st.error(f"Access denied — role **{role}** cannot view or edit the scoring policy.")
    st.stop()

render_topbar("Scoring Policy", "⚖️")
st.markdown(
    "<div style='color:#7E89AC;font-size:0.88rem;margin-top:-0.75rem;margin-bottom:1rem;'>"
    "Configure the hybrid scoring engine used by Agent 5. "
    "Changes take effect immediately. Every save is version-tracked."
    "</div>",
    unsafe_allow_html=True,
)

# ── Load current policy ───────────────────────────────────────────────────────
try:
    policy_resp = api_get("/scoring-policy/").json()
    defaults_resp = api_get("/scoring-policy/defaults").json()
except Exception as e:
    st.error(f"Cannot reach backend: {e}")
    st.stop()

cfg = policy_resp.get("config", defaults_resp)
weights_cfg = cfg.get("weights", {})
thresh_cfg  = cfg.get("thresholds", {})
fw_cfg      = cfg.get("framework_rejection_rules", {})

st.info(
    f"**Active policy** — last updated by **{policy_resp.get('updated_by', 'system')}** "
    f"on {policy_resp.get('updated_at', 'unknown')[:19] if policy_resp.get('updated_at') else 'initial seed'}"
)

# ── How the formula works ─────────────────────────────────────────────────────
with st.expander("📐 How the composite score is calculated", expanded=False):
    st.markdown("""
    ```
    composite = (risk_weight × (100 − agent2_risk_score))
              + (compliance_weight × compliance_average)
              + (quality_weight   × contract_quality_score)
    ```
    """)
    _info_cols = st.columns(3)
    with _info_cols[0]:
        _r = AGENT_SCORES["agent2_risk"]
        st.markdown(f"**{_r['label']}**")
        st.caption(f"Range: {_r['range']}")
        st.info(_r["description"])
        st.caption(f"⚡ {_r['threshold_hint']}")
    with _info_cols[1]:
        _c = AGENT_SCORES["agent3_compliance"]
        st.markdown(f"**{_c['label']}**")
        st.caption(f"Range: {_c['range']}")
        st.info(_c["description"])
        st.caption(f"⚡ {_c['threshold_hint']}")
    with _info_cols[2]:
        _q = AGENT_SCORES["agent1_quality"]
        st.markdown(f"**{_q['label']}**")
        st.caption(f"Range: {_q['range']}")
        st.info(_q["description"])
        st.caption(f"⚡ {_q['threshold_hint']}")

    st.markdown("---")
    _comp = AGENT_SCORES["composite"]
    st.markdown(f"**{_comp['label']}** — {_comp['description']}")
    st.caption(f"Default thresholds: {_comp['threshold_hint']}")
    st.markdown("""
    - **Decision bands** are applied in priority order: **REJECT → LEGAL_REVIEW → MANAGER_REVIEW → AUTO_APPROVE**.
    - Hard override rules (framework critical gaps) bypass the composite entirely and force a REJECT.
    """)

st.divider()

# ── Score weights ─────────────────────────────────────────────────────────────
st.subheader("🔢 Score Weights")
st.caption("Must sum to exactly 1.00")

col1, col2, col3 = st.columns(3)
with col1:
    w_risk = st.slider(
        "⚠️ Risk assessment weight", 0.0, 1.0,
        float(weights_cfg.get("risk", 0.50)), 0.05,
        help=POLICY_PARAMS["weight_risk"],
    )
with col2:
    w_comp = st.slider(
        "📋 Compliance weight", 0.0, 1.0,
        float(weights_cfg.get("compliance", 0.35)), 0.05,
        help=POLICY_PARAMS["weight_compliance"],
    )
with col3:
    w_qual = st.slider(
        "📄 Contract quality weight", 0.0, 1.0,
        float(weights_cfg.get("quality", 0.15)), 0.05,
        help=POLICY_PARAMS["weight_quality"],
    )

weight_total = round(w_risk + w_comp + w_qual, 2)
if weight_total != 1.0:
    st.warning(f"Weights sum to **{weight_total}** — must equal 1.00 before saving.")
else:
    st.success(f"Weights sum to **{weight_total}** ✓")

st.divider()

# ── Decision band thresholds ──────────────────────────────────────────────────
st.subheader("🎚️ Decision Band Thresholds")
st.caption(
    "The composite score (0–100) is compared against these bands in priority order. "
    "Higher composite = healthier contract."
)

band_cols = st.columns(3)
auto_t  = thresh_cfg.get("auto_approve",   {})
mgr_t   = thresh_cfg.get("manager_review", {})
legal_t = thresh_cfg.get("legal_review",   {})

with band_cols[0]:
    st.markdown("#### ✅ AUTO_APPROVE")
    auto_min      = st.number_input(
        "Composite min", 0, 100, int(auto_t.get("composite_min", 82)), key="auto_min",
        help=POLICY_PARAMS["composite_min_auto"],
    )
    auto_crit_max = st.number_input(
        "Critical findings max", 0, 10, int(auto_t.get("critical_max", 0)), key="auto_crit",
        help=POLICY_PARAMS["critical_max"] + f"\n\n🔴 Critical: {SEVERITY['Critical']}",
    )
    auto_high_max = st.number_input(
        "High findings max", 0, 10, int(auto_t.get("high_max", 1)), key="auto_high",
        help=POLICY_PARAMS["high_max"] + f"\n\n🟠 High: {SEVERITY['High']}",
    )

with band_cols[1]:
    st.markdown("#### 🟡 MANAGER_REVIEW")
    mgr_min      = st.number_input(
        "Composite min", 0, 100, int(mgr_t.get("composite_min", 63)), key="mgr_min",
        help=POLICY_PARAMS["composite_min_manager"],
    )
    mgr_crit_max = st.number_input(
        "Critical findings max", 0, 10, int(mgr_t.get("critical_max", 0)), key="mgr_crit",
        help=POLICY_PARAMS["critical_max"] + f"\n\n🔴 Critical: {SEVERITY['Critical']}",
    )
    mgr_high_max = st.number_input(
        "High findings max", 0, 10, int(mgr_t.get("high_max", 2)), key="mgr_high",
        help=POLICY_PARAMS["high_max"] + f"\n\n🟠 High: {SEVERITY['High']}",
    )

with band_cols[2]:
    st.markdown("#### 🔴 LEGAL_REVIEW")
    legal_min      = st.number_input(
        "Composite min", 0, 100, int(legal_t.get("composite_min", 38)), key="legal_min",
        help=POLICY_PARAMS["composite_min_legal"],
    )
    legal_crit_max = st.number_input(
        "Critical findings max", 0, 10, int(legal_t.get("critical_max", 1)), key="legal_crit",
        help=POLICY_PARAMS["critical_max"] + f"\n\n🔴 Critical: {SEVERITY['Critical']}",
    )
    legal_high_max = st.number_input(
        "High findings max", 0, 10, int(legal_t.get("high_max", 5)), key="legal_high",
        help=POLICY_PARAMS["high_max"] + f"\n\n🟠 High: {SEVERITY['High']}",
    )

st.caption("⬇️ Any contract below the LEGAL_REVIEW composite minimum is automatically **REJECTED**.")

st.divider()

# ── Framework hard-rejection rules ───────────────────────────────────────────
st.subheader("🚫 Framework Hard-Rejection Rules")
st.markdown(
    "Critical gaps matching these keywords trigger an immediate **REJECT**, "
    "regardless of the composite score. One keyword per line."
)
with st.expander("ℹ️ What counts as a Critical gap?", expanded=False):
    sev_cols = st.columns(4)
    for col, (sev, desc) in zip(sev_cols, SEVERITY.items()):
        col.markdown(f"**{SEVERITY_BADGE_POLICY.get(sev, '')} {sev}**")
        col.caption(desc)

fw_cols = st.columns(3)
fw_edits: dict[str, list[str]] = {}

for fw_col, (fw_name, default_keywords) in zip(
    fw_cols,
    [
        ("GDPR",  fw_cfg.get("GDPR",  ["data processing agreement", "data breach notification", "subprocessor"])),
        ("HIPAA", fw_cfg.get("HIPAA", ["business associate agreement", "breach notification", "phi safeguard"])),
        ("SOC2",  fw_cfg.get("SOC2",  ["access control", "incident response", "security audit"])),
    ],
):
    with fw_col:
        st.markdown(f"**{fw_name}**")
        raw = st.text_area(
            f"{fw_name} critical keywords",
            value="\n".join(default_keywords),
            height=110,
            key=f"fw_{fw_name}",
            label_visibility="collapsed",
            help=POLICY_PARAMS["framework_keywords"],
        )
        fw_edits[fw_name] = [k.strip() for k in raw.splitlines() if k.strip()]

st.divider()

# ── Simulator ─────────────────────────────────────────────────────────────────
st.subheader("🧪 Score Simulator")
st.caption("Preview what decision the current settings would produce.")

sim_col1, sim_col2, sim_col3 = st.columns(3)
with sim_col1:
    sim_risk = st.slider("Agent 2 risk score (0=safe, 100=risky)", 0, 100, 45)
with sim_col2:
    sim_comp = st.slider("Compliance average %", 0, 100, 70)
with sim_col3:
    sim_qual = st.slider("Contract quality %", 0, 100, 80)

sim_composite = round(
    w_risk * (100 - sim_risk) + w_comp * sim_comp + w_qual * sim_qual, 1
)

sim_crit = st.number_input("Critical findings", 0, 20, 0, key="sim_crit")
sim_high = st.number_input("High findings", 0, 20, 1, key="sim_high")

# Determine simulated decision
if sim_crit > 0 and sim_crit > legal_crit_max:
    sim_decision = "REJECT"
    sim_reason   = f"Critical findings ({sim_crit}) exceed legal-review limit ({legal_crit_max})"
elif sim_composite >= auto_min and sim_crit <= auto_crit_max and sim_high <= auto_high_max:
    sim_decision = "AUTO_APPROVE"
    sim_reason   = f"Composite {sim_composite} ≥ {auto_min}, within finding limits"
elif sim_composite >= mgr_min and sim_crit <= mgr_crit_max and sim_high <= mgr_high_max:
    sim_decision = "MANAGER_REVIEW"
    sim_reason   = f"Composite {sim_composite} in manager band ({mgr_min}–{auto_min - 1})"
elif sim_composite >= legal_min or sim_high >= 3 or sim_crit <= legal_crit_max:
    sim_decision = "LEGAL_REVIEW"
    sim_reason   = f"Composite {sim_composite} in legal band ({legal_min}–{mgr_min - 1}) or findings threshold hit"
else:
    sim_decision = "REJECT"
    sim_reason   = f"Composite {sim_composite} below minimum threshold ({legal_min})"

_COLORS = {
    "AUTO_APPROVE":   "success",
    "MANAGER_REVIEW": "warning",
    "LEGAL_REVIEW":   "warning",
    "REJECT":         "error",
}
getattr(st, _COLORS[sim_decision])(
    f"**Simulated decision: {sim_decision}**  |  Composite score: **{sim_composite}/100**  |  {sim_reason}"
)

st.divider()

# ── Save ──────────────────────────────────────────────────────────────────────
st.subheader("💾 Save Policy")

if weight_total != 1.0:
    st.button("Save policy", disabled=True, help="Fix the weights first — they must sum to 1.00")
else:
    if st.button("Save policy", type="primary"):
        new_config = {
            "weights": {
                "risk":       round(w_risk, 2),
                "compliance": round(w_comp, 2),
                "quality":    round(w_qual, 2),
            },
            "thresholds": {
                "auto_approve":   {"composite_min": auto_min,  "critical_max": auto_crit_max,  "high_max": auto_high_max},
                "manager_review": {"composite_min": mgr_min,   "critical_max": mgr_crit_max,   "high_max": mgr_high_max},
                "legal_review":   {"composite_min": legal_min, "critical_max": legal_crit_max, "high_max": legal_high_max},
            },
            "framework_rejection_rules": fw_edits,
        }
        try:
            import requests, os
            BACKEND = os.getenv("BACKEND_URL", "http://localhost:8000")
            resp = requests.put(
                f"{BACKEND}/scoring-policy/",
                json={"config": new_config, "updated_by": role},
                headers={"x-role": role},
                timeout=10,
            )
            if resp.ok:
                st.success("Policy saved successfully. Next contract upload will use the new thresholds.")
                st.rerun()
            else:
                st.error(f"Save failed: {resp.status_code} — {resp.text}")
        except Exception as e:
            st.error(f"Could not reach backend: {e}")

st.divider()

# ── Rescore existing contracts ────────────────────────────────────────────────
st.subheader("🔄 Rescore Existing Contracts")
st.markdown(
    "Existing contracts are **not automatically rescored** when you change the policy. "
    "Use the buttons below to recompute decisions using the current thresholds — "
    "**no LLM calls are made**, it only re-reads existing agent outputs from the database."
)

import requests as _requests
import os as _os
BACKEND = _os.getenv("BACKEND_URL", "http://localhost:8000")

rescore_cols = st.columns([2, 1])

with rescore_cols[0]:
    st.info(
        "**Bulk rescore** rewrites the recommendation for every contract that has "
        "already been processed. Contract statuses will update to reflect the new policy. "
        "This is safe to run multiple times."
    )
    if st.button("🔄 Rescore all contracts", type="primary"):
        with st.spinner("Rescoring all contracts (no LLM calls — DB reads only)..."):
            try:
                resp = _requests.post(
                    f"{BACKEND}/scoring-policy/rescore-all",
                    headers={"x-role": role},
                    timeout=120,
                )
                if resp.ok:
                    data = resp.json()
                    rescored = data.get("rescored", [])
                    skipped  = data.get("skipped",  [])
                    errors   = data.get("errors",   [])
                    st.success(f"Done — {len(rescored)} rescored, {len(skipped)} skipped, {len(errors)} errors.")
                    if rescored:
                        import pandas as pd
                        df = pd.DataFrame(rescored)
                        st.dataframe(df, use_container_width=True, hide_index=True)
                    if errors:
                        st.warning(f"Errors: {errors}")
                else:
                    st.error(f"Failed: {resp.status_code} — {resp.text}")
            except Exception as e:
                st.error(f"Could not reach backend: {e}")

with rescore_cols[1]:
    st.markdown("**Rescore a single contract:**")
    try:
        all_contracts = api_get("/contracts/").json()
        processable = [c for c in all_contracts if c.get("status") not in ("uploaded", "quarantined")]
        if processable:
            options = {f"#{c['id']} — {c['filename'][:35]}": c["id"] for c in processable}
            picked = st.selectbox("Pick contract", list(options.keys()), key="rescore_picker")
            if st.button("Rescore this contract"):
                cid = options[picked]
                with st.spinner(f"Rescoring contract {cid}..."):
                    try:
                        r = _requests.post(f"{BACKEND}/contracts/{cid}/rescore", timeout=15)
                        if r.ok:
                            d = r.json()
                            sd = d.get("scoring_details", {})
                            st.success(
                                f"Rescored → **{d.get('new_decision')}**  "
                                f"(composite: {sd.get('composite_score')}/100, "
                                f"status: {d.get('new_status')})"
                            )
                        else:
                            st.error(f"Failed: {r.text}")
                    except Exception as e:
                        st.error(str(e))
        else:
            st.caption("No processed contracts available.")
    except Exception as e:
        st.warning(f"Could not load contracts: {e}")

st.divider()

# ── Reinforcement feedback analysis ──────────────────────────────────────────
st.subheader("📈 Reinforcement Feedback Analysis")
st.markdown(
    "Feedback submitted by reviewers in the Review Queue. "
    "Use these patterns to decide if thresholds need adjusting."
)

try:
    summary = api_get("/scoring-policy/feedback/summary").json()
    recent  = api_get("/scoring-policy/feedback/recent?limit=10").json()

    total = summary.get("total", 0)
    if total == 0:
        st.info("No feedback submitted yet. Reviewers can mark scores as Too High / Too Low / Correct in the Review Queue.")
    else:
        # Headline metrics
        breakdown = summary.get("breakdown", {})
        correct   = breakdown.get("correct",  0)
        too_high  = breakdown.get("too_high", 0)
        too_low   = breakdown.get("too_low",  0)

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Total feedback", total,
                  help="Total number of reviewer feedback submissions across all contracts.")
        m2.metric("✅ Correct",    correct,   f"{correct/total*100:.0f}%",
                  help=FEEDBACK["correct"])
        m3.metric("📉 Scored too high", too_high, f"{too_high/total*100:.0f}%",
                  delta_color="inverse",
                  help=FEEDBACK["too_high"])
        m4.metric("📈 Scored too low",  too_low,  f"{too_low/total*100:.0f}%",
                  delta_color="inverse",
                  help=FEEDBACK["too_low"])

        avg_comp = summary.get("avg_composite")
        if avg_comp is not None:
            st.caption(f"Average composite score at time of feedback: **{avg_comp}/100**")

        # Suggestion banner
        suggestion = summary.get("suggestion")
        if suggestion:
            st.warning(f"💡 **Suggested adjustment:** {suggestion}")

        # By AI decision breakdown
        by_decision = summary.get("by_ai_decision", {})
        if by_decision:
            st.markdown("**Feedback by AI decision band:**")
            for decision, counts in by_decision.items():
                total_d = sum(counts.values())
                parts = "  ·  ".join(f"{k}: {v}" for k, v in counts.items())
                st.markdown(f"- **{decision}** ({total_d} feedback) — {parts}")

        # Recent feedback table
        if recent:
            st.markdown("**Recent feedback entries:**")
            import pandas as pd
            df_fb = pd.DataFrame(recent)[[
                "contract_id", "feedback_type", "ai_decision",
                "human_decision", "composite_score", "reviewer_role", "created_at"
            ]]
            df_fb["created_at"] = df_fb["created_at"].str[:19]
            st.dataframe(df_fb, use_container_width=True, hide_index=True)

except Exception as e:
    st.warning(f"Could not load feedback data: {e}")

st.divider()

# ── Change history ────────────────────────────────────────────────────────────
st.subheader("📜 Change History")

try:
    history = api_get("/scoring-policy/history").json()
    if not history:
        st.info("No history yet.")
    else:
        for entry in history:
            status = "🟢 active" if entry.get("is_active") else "⚪ superseded"
            updated = (entry.get("updated_at") or "")[:19]
            with st.expander(
                f"{status}  ·  saved by **{entry.get('updated_by', '?')}**  ·  {updated}",
                expanded=False,
            ):
                ecfg = entry.get("config", {})
                w = ecfg.get("weights", {})
                t = ecfg.get("thresholds", {})
                st.markdown(
                    f"**Weights:** risk={w.get('risk')} · compliance={w.get('compliance')} · quality={w.get('quality')}"
                )
                at = t.get("auto_approve", {})
                mt = t.get("manager_review", {})
                lt = t.get("legal_review", {})
                st.markdown(
                    f"**AUTO_APPROVE** composite ≥ {at.get('composite_min')}  |  "
                    f"**MANAGER_REVIEW** composite ≥ {mt.get('composite_min')}  |  "
                    f"**LEGAL_REVIEW** composite ≥ {lt.get('composite_min')}"
                )
                with st.expander("Full config JSON"):
                    st.json(ecfg)
except Exception as e:
    st.warning(f"Could not load history: {e}")
