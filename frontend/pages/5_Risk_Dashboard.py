"""Risk Dashboard — the hero page judges remember.

Reads /dashboard/risk-summary and renders:
  • Headline metrics (total contracts, avg score, anomalies)
  • Risk score distribution histogram (Plotly)
  • Anomaly callout box
  • Vendor risk ranking table
  • Top recurring risky clauses list
  • By-status breakdown (donut)
"""
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from utils import api_get, current_role, render_topbar, setup_sidebar

st.set_page_config(page_title="Risk Dashboard — Shield AI", page_icon="📊", layout="wide")
setup_sidebar()
render_topbar("Risk Dashboard", "📊")

try:
    data = api_get("/dashboard/risk-summary").json()
except Exception as e:
    st.error(f"Couldn't reach backend: {e}")
    st.stop()

if data["total_contracts"] == 0:
    st.info("No contracts uploaded yet. Upload one to populate the dashboard.")
    st.stop()

# ---- Headline metrics ----
m1, m2, m3, m4 = st.columns(4)
m1.metric("Contracts", data["total_contracts"])
m2.metric("Processed", data["processed_contracts"])
m3.metric("Avg risk score", f"{data['avg_risk_score']}/100")
n_anom = len(data["anomalies"])
m4.metric(
    "Anomalies flagged", n_anom,
    delta="needs attention" if n_anom else "all clear",
    delta_color="inverse" if n_anom else "normal",
)

st.divider()

# ---- Anomaly callout ----
if data["anomalies"]:
    with st.container(border=True):
        st.markdown("### 🚨 Anomaly callouts")
        st.caption(
            "Contracts flagged because their risk score is materially above "
            "the corpus mean, or above the 70-point legal-review threshold."
        )
        for a in data["anomalies"]:
            cols = st.columns([3, 2, 2, 3])
            cols[0].markdown(f"**{a['filename']}**  ·  {a.get('vendor') or '_unknown_'}")
            cols[1].metric("Score", f"{a['score']}/100", label_visibility="collapsed")
            cols[2].caption(a["reason"])
            cols[3].caption(f"Contract #{a['contract_id']}")

# ---- Charts row ----
col_l, col_r = st.columns([3, 2])

with col_l:
    st.subheader("Risk score distribution")
    if data["scores"]:
        fig = px.histogram(
            x=data["scores"],
            nbins=10,
            range_x=[0, 100],
            labels={"x": "Risk score", "y": "Contracts"},
            color_discrete_sequence=["#ef4444"],
        )
        fig.add_vline(
            x=data["avg_risk_score"],
            line_dash="dash",
            line_color="white",
            annotation_text=f"avg {data['avg_risk_score']}",
            annotation_position="top",
        )
        fig.add_vline(x=40, line_dash="dot", line_color="orange",
                      annotation_text="manager (40)", annotation_position="bottom")
        fig.add_vline(x=70, line_dash="dot", line_color="red",
                      annotation_text="legal (70)", annotation_position="bottom")
        fig.update_layout(
            template="plotly_dark",
            margin=dict(l=10, r=10, t=10, b=40),
            showlegend=False,
            height=320,
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.caption("No risk scores yet.")

with col_r:
    st.subheader("By status")
    by_status = data.get("by_status") or {}
    if by_status:
        fig = go.Figure(go.Pie(
            labels=list(by_status.keys()),
            values=list(by_status.values()),
            hole=0.55,
            textinfo="label+value",
        ))
        fig.update_layout(
            template="plotly_dark",
            margin=dict(l=10, r=10, t=10, b=10),
            showlegend=False,
            height=320,
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.caption("No status data yet.")

st.divider()

# ---- Vendor ranking ----
col_v, col_r = st.columns([3, 2])

with col_v:
    st.subheader("Vendor risk ranking")
    ranking = data.get("vendor_ranking") or []
    if ranking:
        st.dataframe(
            ranking,
            hide_index=True,
            use_container_width=True,
            column_config={
                "vendor": st.column_config.TextColumn("Vendor"),
                "n_contracts": st.column_config.NumberColumn("Contracts"),
                "avg_score": st.column_config.NumberColumn("Avg score", format="%.1f"),
                "max_score": st.column_config.NumberColumn("Max score"),
            },
        )
    else:
        st.caption("No vendor data yet.")

with col_r:
    st.subheader("Recurring risky clauses")
    risks = data.get("top_recurring_risks") or []
    if risks:
        for r in risks[:8]:
            sev_emoji = {"Critical": "🔴", "High": "🟠", "Medium": "🟡", "Low": "🟢"}.get(
                r.get("max_severity", "Medium"), "⚪",
            )
            st.write(f"{sev_emoji} **{r['risk']}**  ·  appears in {r['count']} contract(s)")
    else:
        st.caption("No risk findings yet.")
