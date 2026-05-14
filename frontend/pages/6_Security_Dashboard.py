"""Security Dashboard — the wow page.

Big red blocked-injection counter, event-type bar chart, and the recent
security event feed showing the actual hidden-text payload that was caught.
This is where the prompt-injection story lands visually.
"""
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

import plotly.graph_objects as go
import streamlit as st
from utils import api_get, current_role, render_topbar, setup_sidebar

st.set_page_config(page_title="Security Dashboard — Shield AI", page_icon="🔒", layout="wide")
setup_sidebar()
render_topbar("Security Dashboard", "🔒")

st.caption(f"Active role: **{current_role()}**")

# ── Agent 4 architecture banner ──────────────────────────────────────────────
with st.container(border=True):
    st.markdown(
        "## 🪤 Agent 4 — Security Gate (Lobster Trap)\n"
        "_Shield AI's primary security layer — runs **before** any LLM is ever called_"
    )
    col_arch_l, col_arch_r = st.columns([3, 2])
    with col_arch_l:
        st.markdown(
            "Every piece of untrusted content passes through **Agent 4** first:\n\n"
            "| Protected agent | What it receives |\n"
            "|---|---|\n"
            "| 🔍 **Agent 1** — Document Extraction | Uploaded contract text |\n"
            "| ⚠️ **Agent 2** — Risk Assessment | Extracted clause content |\n"
            "| 📋 **Agent 3** — Compliance Check | Extracted clause content |\n"
            "| 🎯 **Agent 5** — Approval Recommendation | Risk + compliance outputs |\n"
            "| 📊 **Agent 6** — Analytics (NL→SQL) | User's chat question |\n"
            "| ❓ **Agent 7** — Contract Q&A | User's chat question |\n"
        )
    with col_arch_r:
        st.markdown(
            "**Two-layer defence** (both run on every request):\n\n"
            "🪤 **Layer 1 — Lobster Trap** *(primary)*  \n"
            "Deep packet inspection proxy. Detects prompt injection, credential "
            "leaks, role impersonation, data exfiltration, and policy bypass. "
            "Returns `verdict: DENY` → content is quarantined immediately.\n\n"
            "🧱 **Layer 2 — Offline detector** *(fallback + belt-and-suspenders)*  \n"
            "13 regex patterns + zero-width unicode detection. Runs offline, "
            "always available even when Lobster Trap is unreachable."
        )

st.divider()

try:
    data = api_get("/dashboard/security-summary").json()
except Exception as e:
    st.error(f"Couldn't reach backend: {e}")
    st.stop()

# ---- Headline metrics ----
m1, m2, m3 = st.columns(3)
m1.metric(
    "Blocked injections",
    data["blocked_injections"],
    delta="all stopped pre-LLM" if data["blocked_injections"] else "none yet",
    delta_color="off" if data["blocked_injections"] else "normal",
)
m2.metric("Quarantined contracts", data["quarantined_contracts"])
m3.metric("Total security events", data["total_events"])

st.divider()



# ---- Two-column charts ----
col_l, col_r = st.columns(2)

with col_l:
    st.subheader("Events by type")
    by_type = data.get("events_by_type") or {}
    if by_type:
        fig = go.Figure(go.Bar(
            x=list(by_type.values()),
            y=list(by_type.keys()),
            orientation="h",
            marker_color="#ef4444",
        ))
        fig.update_layout(
            template="plotly_dark",
            margin=dict(l=10, r=10, t=10, b=10),
            height=300,
            xaxis_title="Count",
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.caption("No security events yet. Upload `Vendor_Agreement.pdf` to see one.")

with col_r:
    st.subheader("Events by severity")
    by_sev = data.get("events_by_severity") or {}
    if by_sev:
        # Order severities consistently
        order = ["critical", "high", "medium", "low"]
        labels = [s for s in order if s in by_sev] + [
            s for s in by_sev if s not in order
        ]
        values = [by_sev[s] for s in labels]
        colors = {
            "critical": "#dc2626",
            "high": "#f97316",
            "medium": "#facc15",
            "low": "#22c55e",
        }
        fig = go.Figure(go.Bar(
            x=labels,
            y=values,
            marker_color=[colors.get(s, "#9ca3af") for s in labels],
        ))
        fig.update_layout(
            template="plotly_dark",
            margin=dict(l=10, r=10, t=10, b=10),
            height=300,
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.caption("No events by severity yet.")

st.divider()

# ---- Recent events feed ----
st.subheader("Recent security events")
st.caption(
    "Each row is a real detection. The matched text shows exactly what was caught — "
    "this is the demo's smoking gun."
)

events = data.get("recent_events") or []
if not events:
    st.info(
        "No events yet. Upload `Vendor_Agreement.pdf` (the showcase contract with "
        "hidden white-on-white text) to populate this feed."
    )
else:
    SEV_COLOR = {
        "critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢",
    }
    SOURCE_BADGE = {
        "lobstertrap": "🪤 Lobster Trap",
        "offline_detector": "🧱 Offline detector",
    }

    for ev in events:
        with st.container(border=True):
            head_l, head_r = st.columns([3, 1])
            details = ev.get("details") or {}
            source = details.get("source", "offline_detector")
            head_l.markdown(
                f"**{SEV_COLOR.get(ev['severity'], '⚪')} {ev['event_type']}**  ·  "
                f"_{ev['filename']}_  ·  contract #{ev['contract_id']}  ·  "
                f"{SOURCE_BADGE.get(source, source)}"
            )
            head_r.caption((ev.get("created_at") or "")[:19].replace("T", " "))

            if details.get("rule_name"):
                st.markdown(f"**Lobster Trap rule:** `{details['rule_name']}`")
            if details.get("matched_text"):
                st.markdown("**Matched text:**")
                st.code(details["matched_text"], language="text")
            if details.get("context"):
                with st.expander("Surrounding context"):
                    st.code(details["context"], language="text")
            if details.get("detected_flags"):
                st.markdown(
                    "**Detected flags:** "
                    + ", ".join(f"`{f}`" for f in details["detected_flags"])
                )
            if details.get("description"):
                st.caption(details["description"])
            if details.get("risk_score") is not None:
                st.caption(f"Lobster Trap risk score: {details['risk_score']}")
            elif details.get("confidence") is not None:
                st.caption(f"Confidence: {details['confidence']}")
