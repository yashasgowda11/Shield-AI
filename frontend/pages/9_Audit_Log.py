"""Audit Log — paginated, filterable view of every audit event.

This is the page that proves to judges we have a real governance story.
Every agent prompt, every human action, every status change is here.
"""
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

import streamlit as st
from utils import api_get, current_role, render_topbar, setup_sidebar

st.set_page_config(page_title="Audit Log — Shield AI", page_icon="📒", layout="wide")
setup_sidebar()
render_topbar("Audit Log", "📒")

st.markdown(
    "Append-only log of every action — agent runs, human decisions, "
    "security events, status changes."
)

# ---- Filters ----
col1, col2, col3, col4 = st.columns([2, 2, 2, 1])
actor_filter = col1.text_input("Actor (substring)", placeholder="agent:risk")
action_filter = col2.text_input("Action (substring)", placeholder="approve")
contract_filter = col3.number_input(
    "Contract ID", min_value=0, value=0,
    help="0 = no filter",
)
limit = col4.selectbox("Limit", [25, 50, 100, 250], index=2)

params = {"limit": limit}
if actor_filter:
    params["actor"] = actor_filter
if action_filter:
    params["action"] = action_filter
if contract_filter:
    params["contract_id"] = int(contract_filter)

try:
    payload = api_get("/audit/", params=params).json()
except Exception as e:
    st.error(f"Couldn't reach backend: {e}")
    st.stop()

st.caption(f"Showing {len(payload['items'])} of {payload['total']} entries.")

ACTOR_EMOJI = {
    "agent:": "🤖",
    "user:": "👤",
    "system": "⚙️",
}


def _actor_emoji(actor: str) -> str:
    for prefix, emoji in ACTOR_EMOJI.items():
        if actor.startswith(prefix):
            return emoji
    return "•"


for entry in payload["items"]:
    actor = entry.get("actor", "")
    with st.container(border=True):
        cols = st.columns([3, 2, 2, 3])
        cols[0].markdown(
            f"**{_actor_emoji(actor)} {actor}**  →  `{entry.get('action', '?')}`"
        )
        cols[1].caption(entry.get("resource") or "—")
        cols[2].caption(
            (entry.get("timestamp") or "").replace("T", " ")[:19]
        )
        with cols[3]:
            if entry.get("after"):
                with st.expander("after"):
                    st.json(entry["after"])
            if entry.get("before"):
                with st.expander("before"):
                    st.json(entry["before"])
