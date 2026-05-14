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
from utils import api_get, api_post, current_role, get_service_status, render_topbar, setup_sidebar

st.set_page_config(page_title="Ask Shield AI", page_icon="💬", layout="wide")
setup_sidebar()
render_topbar("Ask Shield AI", "💬")

st.caption(f"Active role: **{current_role()}**")
st.caption("🪤 All questions are scanned by **Agent 4 — Security Gate (Lobster Trap)** before reaching the AI.")


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

def _render_blocked_assistant(msg: dict) -> None:
    """Render a message that was blocked by Agent 4 (Security Gate)."""
    st.error("🪤 **Agent 4 — Security Gate blocked this query**")
    st.markdown(
        "Your question was flagged as suspicious and was **not sent to any AI model**. "
        "This is Agent 4 (Lobster Trap) stopping a potential prompt-injection attempt."
    )

    reason = msg.get("reason") or msg.get("error") or "Suspicious content detected."
    st.warning(f"**Reason:** {reason}")

    lt_result = msg.get("lt_result")
    if lt_result:
        with st.expander("🪤 Lobster Trap details"):
            if lt_result.get("rule_name"):
                st.markdown(f"**Rule fired:** `{lt_result['rule_name']}`")
            if lt_result.get("deny_message"):
                st.code(lt_result["deny_message"], language="text")
            if lt_result.get("detected"):
                flags = [k for k, v in lt_result["detected"].items() if isinstance(v, bool) and v]
                if flags:
                    st.markdown("**Detected flags:** " + "  ·  ".join(f"`{f}`" for f in flags))
            if lt_result.get("risk_score") is not None:
                st.metric("LT risk score", f"{lt_result['risk_score']:.2f}")
            if lt_result.get("request_id"):
                st.caption(f"Request ID: `{lt_result['request_id']}`")

    offline_events = msg.get("offline_events") or []
    if offline_events and not lt_result:
        with st.expander("🧱 Offline detector details"):
            for ev in offline_events:
                d = ev.get("details") or {}
                if d.get("matched_text"):
                    st.markdown("**Matched text:**")
                    st.code(d["matched_text"], language="text")
                if d.get("description"):
                    st.caption(d["description"])

    st.info("Rephrase your question and try again.")


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
            if msg.get("mode") == "blocked":
                _render_blocked_assistant(msg)
            elif msg.get("mode") == "contract_qa":
                _render_qa_assistant(msg)
            else:
                _render_analytics_assistant(msg)


# ─── Capture next question ───────────────────────────────────────────────────

_svc = get_service_status()
_lt_online = _svc.get("lt", {}).get("available", True)
if not _lt_online:
    st.warning(
        "⚠️ **Agent 4 (Lobster Trap) is offline.** Your questions will only be scanned "
        "by the offline pattern detector. Basic injection patterns will still be caught."
    )

placeholder = (
    "Ask a question about your contracts…" if is_analytics
    else "Ask about this contract…"
)
typed = st.chat_input(placeholder)
question = st.session_state.pending_question or typed

if question and not _lt_online:
    if not st.session_state.get("lt_query_consent_given"):
        col_warn, col_btn = st.columns([3, 1])
        col_warn.warning("Lobster Trap is offline. Your question will only get offline scanning.")
        if col_btn.button("Proceed anyway", key="lt_query_consent_btn"):
            st.session_state.lt_query_consent_given = True
            st.rerun()
        st.stop()
else:
    st.session_state.lt_query_consent_given = False

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
        "🪤 Security gate scanning… then translating to SQL and running…" if is_analytics
        else "🪤 Security gate scanning… then reading the contract…"
    )
    with st.spinner(spinner_msg):
        try:
            resp = api_post("/query/", json=payload_in)
            payload = resp.json()
        except Exception as e:
            payload = {"error": f"Backend unreachable: {e}"}

    payload["mode"] = payload.get("mode") or ("analytics" if is_analytics else "contract_qa")

    # Show which security layer ran (only for successful queries)
    if payload["mode"] not in ("blocked",) and not payload.get("error"):
        scan_info = payload.get("security_scan", {})
        if scan_info.get("lt_used"):
            st.caption("🪤 Agent 4: Lobster Trap scanned this question — no threats detected.")
        else:
            st.caption("🧱 Agent 4: Offline detector scanned this question (Lobster Trap not reachable).")

    if payload["mode"] == "blocked":
        _render_blocked_assistant(payload)
    elif payload["mode"] == "contract_qa":
        _render_qa_assistant(payload)
    else:
        _render_analytics_assistant(payload)

    # Persist for history. Store everything we might need to re-render.
    st.session_state.ask_messages.append({
        "role": "assistant",
        **{k: v for k, v in payload.items() if k != "question"},
    })
