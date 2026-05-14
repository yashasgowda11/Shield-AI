"""Knowledge Graph page — interactive graph view of vendors / contracts /
risks / frameworks built from existing extraction outputs.

This is the focus area #5 win: knowledge graph extraction from documents.
Uses streamlit-agraph for an interactive node/edge visualization with
filters and a click-to-inspect side panel.
"""
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

import streamlit as st

# streamlit-agraph imports
from streamlit_agraph import Config, Edge, Node, agraph

from utils import api_get, current_role, render_topbar, setup_sidebar

st.set_page_config(page_title="Knowledge Graph — Shield AI", page_icon="🕸", layout="wide")
setup_sidebar()
render_topbar("Knowledge Graph", "🕸")

st.markdown(
    "Vendors → Contracts → Risks → Frameworks, extracted from every contract "
    "the system has processed. Hub nodes (risks appearing across multiple "
    "contracts) are the visual story: this is what makes recurring risk patterns "
    "obvious at a glance."
)

# ---- Filters ----

NODE_TYPES = ["vendor", "contract", "risk", "framework"]
SEVERITIES = ["Low", "Medium", "High", "Critical"]

with st.container(border=True):
    fcol1, fcol2, fcol3 = st.columns([2, 2, 1])
    selected_types = fcol1.multiselect(
        "Show node types",
        NODE_TYPES,
        default=NODE_TYPES,
    )
    min_severity = fcol2.selectbox(
        "Minimum risk severity to show",
        ["(all)"] + SEVERITIES,
        index=0,
    )
    show_labels = fcol3.checkbox("Show labels", value=True)

# ---- Fetch data ----

params: dict = {}
if selected_types and len(selected_types) < len(NODE_TYPES):
    params["node_types"] = ",".join(selected_types)
if min_severity != "(all)":
    params["min_severity"] = min_severity

try:
    data = api_get("/graph/", params=params).json()
    hubs = api_get("/graph/hubs").json()
except Exception as e:
    st.error(f"Couldn't reach backend: {e}")
    st.stop()

stats = data.get("stats", {})
m1, m2, m3, m4 = st.columns(4)
m1.metric("Nodes", stats.get("n_nodes", 0))
m2.metric("Edges", stats.get("n_edges", 0))
by_type = stats.get("by_type", {})
m3.metric("Vendors", by_type.get("vendor", 0))
m4.metric("Risk hubs", by_type.get("risk", 0))

if stats.get("n_nodes", 0) == 0:
    st.info(
        "No data yet. Upload a few contracts so the system has something "
        "to extract a graph from."
    )
    st.stop()

st.divider()

# ---- Visual config: shape + color per node type ----

NODE_VISUAL = {
    "vendor":    {"shape": "box",      "color": "#4F8EF7"},  # blue — box is more readable than square
    "contract":  {"shape": "ellipse",  "color": "#22c55e"},  # green (overridden by status)
    "risk":      {"shape": "diamond",  "color": "#ef4444"},  # red (severity-based)
    "framework": {"shape": "hexagon",  "color": "#9A91FB"},  # purple
}

CONTRACT_STATUS_COLOR = {
    "approved": "#22c55e",
    "manager_review": "#f59e0b",
    "legal_review": "#3b82f6",
    "rejected": "#ef4444",
    "quarantined": "#dc2626",
    "processed": "#9ca3af",
    "extracted": "#9ca3af",
}

RISK_SEVERITY_COLOR = {
    "Low": "#facc15",
    "Medium": "#fb923c",
    "High": "#f97316",
    "Critical": "#dc2626",
}

EDGE_COLOR = {
    "signed": "#3b82f6",
    "flagged": "#ef4444",
    "checked": "#a855f7",
}


def _node_color(meta: dict) -> str:
    t = meta.get("type")
    if t == "contract":
        return CONTRACT_STATUS_COLOR.get(meta.get("status", ""), "#22c55e")
    if t == "risk":
        return RISK_SEVERITY_COLOR.get(meta.get("max_severity", "Low"), "#ef4444")
    return NODE_VISUAL.get(t, {}).get("color", "#9ca3af")


def _node_size(meta: dict) -> int:
    """Bigger nodes for hubs — minimum 28 so labels are always readable."""
    if meta.get("type") == "risk":
        return 28 + min(int(meta.get("occurrences", 1)) * 8, 48)
    if meta.get("type") == "vendor":
        return 32
    if meta.get("type") == "contract":
        return 26
    return 28


def _tooltip(n: dict) -> str:
    """Hover tooltip for a node."""
    t = n.get("type")
    if t == "vendor":
        return f"Vendor: {n.get('label')}"
    if t == "contract":
        return (f"Contract: {n.get('label')}\n"
                f"Status: {n.get('status')}\n"
                f"Risk score: {n.get('risk_score')}")
    if t == "risk":
        return (f"Risk: {n.get('label')}\n"
                f"Occurrences: {n.get('occurrences')}\n"
                f"Max severity: {n.get('max_severity')}")
    if t == "framework":
        return f"Framework: {n.get('label')}"
    return n.get("label", "")


# ---- Render the graph ----

st.subheader("Graph view")

agraph_nodes = []
for n in data["nodes"]:
    label = n.get("label", n["id"]) if show_labels else ""
    visual = NODE_VISUAL.get(n.get("type"), {})
    node_color = _node_color(n)
    agraph_nodes.append(Node(
        id=n["id"],
        label=label,
        size=_node_size(n),
        color={
            "background": node_color,
            "border": "#FFFFFF",
            "highlight": {"background": "#FDB52A", "border": "#FFFFFF"},
        },
        font={"color": "#FFFFFF", "size": 13, "face": "Inter, sans-serif", "strokeWidth": 2, "strokeColor": "#000000"},
        shape=visual.get("shape", "ellipse"),
        title=_tooltip(n),  # hover text
        borderWidth=2,
    ))

agraph_edges = []
for e in data["edges"]:
    agraph_edges.append(Edge(
        source=e["source"],
        target=e["target"],
        color=EDGE_COLOR.get(e.get("type"), "#9ca3af"),
        label=e.get("type", ""),
    ))

# Wrap graph in a light-background panel so dark nodes pop
st.markdown(
    "<div style='background:#0a1020;border:1px solid #212C4D;border-radius:14px;"
    "padding:0.5rem;margin:0.25rem 0 0.5rem;'>",
    unsafe_allow_html=True,
)

config = Config(
    width="100%",
    height=650,
    directed=True,
    physics=True,
    hierarchical=False,
    nodeHighlightBehavior=True,
    highlightColor="#FDB52A",
    collapsible=False,
    backgroundColor="#0a1020",
    node={"labelHighlightBold": True},
    edge={
        "color": {"color": "#37446B", "highlight": "#6C72FF", "hover": "#9A91FB"},
        "smooth": {"type": "curvedCW", "roundness": 0.2},
        "font": {"color": "#7E89AC", "size": 11, "face": "Inter, sans-serif"},
        "arrows": {"to": {"enabled": True, "scaleFactor": 0.6}},
    },
)

selected_id = agraph(nodes=agraph_nodes, edges=agraph_edges, config=config)
st.markdown("</div>", unsafe_allow_html=True)

# Side panel for selected node
if selected_id:
    selected_meta = next((n for n in data["nodes"] if n["id"] == selected_id), None)
    if selected_meta:
        with st.container(border=True):
            st.markdown(f"### Selected: `{selected_meta.get('label', selected_id)}`")
            st.json(selected_meta)


# ---- Hub summary ----

st.divider()
st.subheader("Hubs — what the graph reveals")

hcol1, hcol2, hcol3 = st.columns(3)

with hcol1:
    st.markdown("**Most-active vendors**")
    if hubs.get("top_vendors"):
        for v in hubs["top_vendors"]:
            st.write(f"- **{v['vendor']}** · {v['n_contracts']} contract(s)")
    else:
        st.caption("No vendors yet.")

with hcol2:
    st.markdown("**Most-recurring risks**")
    if hubs.get("top_risks"):
        for r in hubs["top_risks"]:
            sev_emoji = {"Critical": "🔴", "High": "🟠", "Medium": "🟡", "Low": "🟢"}.get(
                r.get("max_severity", "Medium"), "⚪",
            )
            st.write(
                f"{sev_emoji} **{r['risk']}** · in {r['occurrences']} contract(s)"
            )
    else:
        st.caption("No risks yet.")

with hcol3:
    st.markdown("**Frameworks checked**")
    if hubs.get("top_frameworks"):
        for f in hubs["top_frameworks"]:
            st.write(f"- **{f['framework']}** · {f['n_checks']} check(s)")
    else:
        st.caption("No compliance checks yet.")
