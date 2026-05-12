"""Ask Shield AI — natural-language chat with two modes.

  📊 Analytics            → NL → SQL across the contracts DB (Agent 6, analytics)
  ❓ Ask about a contract → grounded answer with clause citations (contract_qa)

The mode toggle at the top determines which agent is called. The backend
endpoint (POST /query/) routes on the presence of `contract_id`.
"""
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

import streamlit as st
from utils import api_get, api_post, current_role

st.set_page_config(page_title="Ask Shield AI", layout="wide")

st.title("💬 Ask Shield AI")
st.caption(f"Active role: **{current_role()}**")


# ─── Mode toggle ─────────────────────────────────────────────────────────────

if "ask_mode" not in st.session_state:
    st.session_state.ask_mode = "📊 Analytics"
if "ask_messages" not in st.session_state:
    st.session_state.ask_messages = []
if "pending_question" not in st.session_state:
    st.session_state.pending_question = None
if "selected_contract_id" not in st.session_state:
    st.session_state.selected_contract_id = None

new_mode = st.radio(
    "Mode",
    options=["📊 Analytics", "❓ Ask about a contract"],
    horizontal=True,
    key="ask_mode_radio",
    index=["📊 Analytics", "❓ Ask about a contract"].index(st.session_state.ask_mode),
)
if new_mode != st.session_state.ask_mode:
    # Mode switch — clear history so SQL rows and Q&A answers don't intermix
    st.session_state.ask_mode = new_mode
    st.session_state.ask_messages = []
    st.session_state.pending_question = None

mode = st.session_state.ask_mode
is_analytics = mode == "📊 Analytics"


# ─── Mode-specific description + controls ────────────────────────────────────

if is_analytics:
    st.markdown(
        "Ask anything about the contracts corpus in plain English. Shield AI "
        "translates your question to SQL, runs it against a read-only view of "
        "the database, and shows you both the answer **and the SQL it generated**."
    )

    SUGGESTIONS = [
        "Show me all contracts with HIPAA gaps",
        "Which vendors have the highest average risk score?",
        "How many contracts were quarantined in total?",
        "List contracts pending legal review",
    ]
else:
    st.markdown(
        "Pick a contract, then ask questions about its terms. Every factual "
        "claim is **cited to a specific clause** so you can verify the answer."
    )

    # Contract picker
    try:
        all_contracts = api_get("/contracts/").json()
    except Exception as e:
        st.error(f"Couldn't reach backend: {e}")
        st.stop()

    # Only contracts that have extracted clauses are answerable
    answerable = [c for c in all_contracts if (c.get("n_clauses") or 0) > 0]
    if not answerable:
        st.warning(
            "No processed contracts available. Upload one and let extraction "
            "finish, then come back."
        )
        st.stop()

    def _label(c: dict) -> str:
        return f"#{c['id']}  ·  {c['filename']}  ·  {c['status']}  ·  {c['n_clauses']} clauses"

    options = {_label(c): c["id"] for c in answerable}
    default_index = 0
    if st.session_state.selected_contract_id is not None:
        for i, cid in enumerate(options.values()):
            if cid == st.session_state.selected_contract_id:
                default_index = i
                break

    picked_label = st.selectbox(
        "Contract", list(options.keys()), index=default_index, key="contract_picker"
    )
    new_contract_id = options[picked_label]
    if new_contract_id != st.session_state.selected_contract_id:
        # Different contract — wipe history so citations stay coherent
        st.session_state.selected_contract_id = new_contract_id
        st.session_state.ask_messages = []
        st.session_state.pending_question = None

    SUGGESTIONS = [
        "What is the liability cap?",
        "What are the termination terms?",
        "Does this contract include a Business Associate Agreement?",
        "What's the governing law?",
    ]


# ─── Quick suggestion chips ──────────────────────────────────────────────────

st.markdown("**Quick suggestions:**")
chip_cols = st.columns(len(SUGGESTIONS))
for col, suggestion in zip(chip_cols, SUGGESTIONS):
    if col.button(suggestion, key=f"chip_{mode}_{suggestion}"):
        st.session_state.pending_question = suggestion


# ─── Render helpers ──────────────────────────────────────────────────────────

def _render_analytics_assistant(msg: dict) -> None:
    if msg.get("error"):
        st.error(msg["error"])
    if msg.get("explanation"):
        st.write(msg["explanation"])
    rows = msg.get("rows") or []
    if rows:
        st.dataframe(rows, use_container_width=True, hide_index=True)
        st.caption(f"{msg.get('row_count', len(rows))} row(s)")
    elif not msg.get("error"):
        st.caption("No rows returned.")
    if msg.get("sql"):
        with st.expander("View SQL"):
            st.code(msg["sql"], language="sql")


_RELEVANCE_EMOJI = {"high": "🟢", "medium": "🟡", "low": "⚪"}


def _render_qa_assistant(msg: dict) -> None:
    if msg.get("error"):
        st.error(msg["error"])
        return

    answer = msg.get("answer")
    if answer:
        st.markdown(answer)

    confidence = msg.get("confidence")
    if confidence is not None:
        bar = "▓" * int(confidence * 10) + "░" * (10 - int(confidence * 10))
        st.caption(f"Confidence: `{bar}` {confidence:.2f}")

    cited = msg.get("cited_clauses") or []
    if cited:
        st.markdown("**Cited clauses**")
        contract_id = msg.get("contract_id")
        # Pull contract clauses once for inline rendering
        clauses_by_number: dict[str, dict] = {}
        if contract_id:
            try:
                detail = api_get(f"/contracts/{contract_id}").json()
                for c in detail.get("clauses") or []:
                    clauses_by_number[str(c.get("number"))] = c
            except Exception:
                pass

        for cit in cited:
            emoji = _RELEVANCE_EMOJI.get((cit.get("relevance") or "").lower(), "•")
            num = cit.get("number", "?")
            title = cit.get("title", "")
            with st.expander(f"{emoji} § {num} — {title}"):
                clause = clauses_by_number.get(str(num))
                if clause and clause.get("text"):
                    st.write(clause["text"])
                else:
                    st.caption("_clause text unavailable_")


# ─── Render chat history ─────────────────────────────────────────────────────

for msg in st.session_state.ask_messages:
    with st.chat_message(msg["role"]):
        if msg["role"] == "user":
            st.write(msg["content"])
        else:
            if msg.get("mode") == "contract_qa":
                _render_qa_assistant(msg)
            else:
                _render_analytics_assistant(msg)


# ─── Capture next question ───────────────────────────────────────────────────

placeholder = (
    "Ask a question about your contracts…" if is_analytics
    else "Ask about this contract…"
)
typed = st.chat_input(placeholder)
question = st.session_state.pending_question or typed
if not question:
    st.stop()
st.session_state.pending_question = None


# ─── Send + render ───────────────────────────────────────────────────────────

st.session_state.ask_messages.append({"role": "user", "content": question})
with st.chat_message("user"):
    st.write(question)

payload_in: dict = {"question": question}
if not is_analytics:
    payload_in["contract_id"] = st.session_state.selected_contract_id

with st.chat_message("assistant"):
    spinner_msg = (
        "Translating to SQL and running…" if is_analytics
        else "Reading the contract and grounding the answer…"
    )
    with st.spinner(spinner_msg):
        try:
            resp = api_post("/query/", json=payload_in)
            payload = resp.json()
        except Exception as e:
            payload = {"error": f"Backend unreachable: {e}"}

    payload["mode"] = payload.get("mode") or ("analytics" if is_analytics else "contract_qa")
    if payload["mode"] == "contract_qa":
        _render_qa_assistant(payload)
    else:
        _render_analytics_assistant(payload)

    # Persist for history. Store everything we might need to re-render.
    st.session_state.ask_messages.append({
        "role": "assistant",
        **{k: v for k, v in payload.items() if k != "question"},
    })
