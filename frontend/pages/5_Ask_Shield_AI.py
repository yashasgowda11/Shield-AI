"""Ask Shield AI — natural-language chat over the contracts DB.

Backend Agent 6 translates NL → SQL, executes against the read-only DB,
returns rows. The page renders the answer + a collapsible "View SQL" panel
so the user can see exactly what was queried.

The 4 quick-question chips at the top are pre-canned demo prompts that we've
verified work well — judges will use them.
"""
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

import streamlit as st
from utils import api_post, current_role

st.set_page_config(page_title="Ask Shield AI", layout="wide")

st.title("💬 Ask Shield AI")
st.caption(f"Active role: **{current_role()}**")

st.markdown(
    "Ask anything about the contracts corpus in plain English. Shield AI "
    "translates your question to SQL, runs it against a read-only view of the "
    "database, and shows you both the answer **and the SQL it generated**."
)

# Pre-canned demo prompts — clicking one fills the input
SUGGESTIONS = [
    "Show me all contracts with HIPAA gaps",
    "Which vendors have the highest average risk score?",
    "How many contracts were quarantined in total?",
    "List contracts pending legal review",
]

if "ask_messages" not in st.session_state:
    st.session_state.ask_messages = []
if "pending_question" not in st.session_state:
    st.session_state.pending_question = None


# Quick-suggestion chips
st.markdown("**Quick suggestions:**")
chip_cols = st.columns(len(SUGGESTIONS))
for col, suggestion in zip(chip_cols, SUGGESTIONS):
    if col.button(suggestion, key=f"chip_{suggestion}"):
        st.session_state.pending_question = suggestion


# Render chat history
for msg in st.session_state.ask_messages:
    with st.chat_message(msg["role"]):
        if msg["role"] == "user":
            st.write(msg["content"])
        else:  # assistant
            st.write(msg.get("explanation") or msg.get("content") or "")
            if msg.get("error"):
                st.error(msg["error"])
            elif msg.get("rows") is not None:
                if msg["rows"]:
                    st.dataframe(msg["rows"], use_container_width=True, hide_index=True)
                    st.caption(f"{msg['row_count']} row(s)")
                else:
                    st.caption("No rows returned.")
            if msg.get("sql"):
                with st.expander("View SQL"):
                    st.code(msg["sql"], language="sql")


# Determine the next question — either from chip click or chat input
typed = st.chat_input("Ask a question about your contracts…")
question = st.session_state.pending_question or typed
if question:
    st.session_state.pending_question = None  # consume

    # Render user turn immediately
    st.session_state.ask_messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.write(question)

    # Call backend
    with st.chat_message("assistant"):
        with st.spinner("Translating to SQL and running..."):
            try:
                resp = api_post("/query/", json={"question": question})
                payload = resp.json()
            except Exception as e:
                payload = {
                    "question": question,
                    "sql": None,
                    "explanation": None,
                    "rows": [],
                    "row_count": 0,
                    "error": f"Backend unreachable: {e}",
                }

        # Render answer
        if payload.get("error"):
            st.error(payload["error"])
        else:
            st.write(payload.get("explanation") or "Here's what I found:")

        if payload.get("rows"):
            st.dataframe(payload["rows"], use_container_width=True, hide_index=True)
            st.caption(f"{payload.get('row_count', len(payload['rows']))} row(s)")
        elif not payload.get("error"):
            st.caption("No rows returned.")

        if payload.get("sql"):
            with st.expander("View SQL"):
                st.code(payload["sql"], language="sql")

        # Persist assistant turn
        st.session_state.ask_messages.append({
            "role": "assistant",
            "explanation": payload.get("explanation"),
            "rows": payload.get("rows") or [],
            "row_count": payload.get("row_count", 0),
            "sql": payload.get("sql"),
            "error": payload.get("error"),
        })
