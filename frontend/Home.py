"""Shield AI — About page (home).

Animated landing page introducing Shield AI and its five AI agents.
Role selector lives in the top-right corner via render_topbar().
"""
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).parent))

import streamlit as st
from style import apply_theme
from utils import ROLES, ROLE_ICON, setup_sidebar, health_check

st.set_page_config(
    page_title="Shield AI",
    page_icon="🛡",
    layout="wide",
    initial_sidebar_state="expanded",
)

apply_theme()
setup_sidebar()

# ── Role selector — top right corner ─────────────────────────────────────────
if "role" not in st.session_state:
    st.session_state.role = ROLES[0]

_tc, _sc, _rc = st.columns([5, 2, 3])
with _rc:
    _chosen = st.selectbox(
        "role",
        ROLES,
        index=ROLES.index(st.session_state.role),
        label_visibility="collapsed",
        format_func=lambda r: f"{ROLE_ICON.get(r, '👤')} {r}",
        key="_about_role",
    )
    if _chosen != st.session_state.role:
        st.session_state.role = _chosen
        st.rerun()

# ── Hero Banner ───────────────────────────────────────────────────────────────
st.markdown("""
<div class="hero-banner">
    <div class="hero-badge">🛡 Enterprise Contract Intelligence</div>
    <h1 class="hero-title">Shield AI</h1>
    <p class="hero-subtitle">
        A multi-agent AI platform that reads, scores, and routes enterprise contracts —
        combining Gemini LLMs, RAG over your policy corpus, and a deterministic
        approval engine to eliminate manual review bottlenecks.
    </p>
    <div class="hero-stats">
        <div class="hero-stat">
            <div class="hero-stat-value">5</div>
            <div class="hero-stat-label">AI Agents</div>
        </div>
        <div class="hero-stat">
            <div class="hero-stat-value">3</div>
            <div class="hero-stat-label">Frameworks</div>
        </div>
        <div class="hero-stat">
            <div class="hero-stat-value">100%</div>
            <div class="hero-stat-label">Auditable</div>
        </div>
        <div class="hero-stat">
            <div class="hero-stat-value">0</div>
            <div class="hero-stat-label">LLMs in approval path</div>
        </div>
    </div>
</div>
""", unsafe_allow_html=True)


# ── Agent Pipeline Cards ──────────────────────────────────────────────────────
st.markdown(
    "<h2 style='font-size:1.4rem;font-weight:700;color:#FFFFFF;margin-bottom:0.25rem;'>"
    "🤖 The AI Pipeline</h2>"
    "<p style='color:#7E89AC;font-size:0.9rem;margin-bottom:1.5rem;'>"
    "Five specialised agents run sequentially on every uploaded contract."
    "</p>",
    unsafe_allow_html=True,
)

_agents = [
    {
        "cls": "a1", "num": "Agent 1", "delay": "0.1s",
        "name": "Document Extraction",
        "model": "Gemini 1.5 Flash",
        "icon": "📄",
        "desc": (
            "Parses the raw contract and extracts structured fields — parties, "
            "effective date, governing law, payment terms, obligations and summary. "
            "Two-pass: the second pass injects vendor history so anomalies vs past "
            "submissions are flagged in the summary."
        ),
        "outputs": "Parties · Dates · Obligations · Summary",
    },
    {
        "cls": "a2", "num": "Agent 2", "delay": "0.2s",
        "name": "Risk Assessment",
        "model": "Gemini 1.5 Pro + Pinecone RAG",
        "icon": "⚠️",
        "desc": (
            "Evaluates every clause against similar clauses from past contracts "
            "retrieved from Pinecone. Each finding is rated Low / Medium / High / "
            "Critical and an overall risk score 0–100 is assigned. "
            "0 = no material risk, 100 = extremely risky."
        ),
        "outputs": "Risk score · Per-clause findings · Severity ratings",
    },
    {
        "cls": "a3", "num": "Agent 3", "delay": "0.3s",
        "name": "Compliance Check",
        "model": "Gemini 1.5 Pro + Pinecone RAG",
        "icon": "📋",
        "desc": (
            "Checks the contract against HIPAA, SOC 2, and GDPR requirements "
            "retrieved from your internal policy corpus. Critical gaps count 3× "
            "more than Medium gaps in the weighted compliance average. "
            "Vendor compliance history is prepended so recurring failures are "
            "rated more severely."
        ),
        "outputs": "Framework pass/fail · Compliance average · Gap descriptions",
    },
    {
        "cls": "a4", "num": "Agent 4", "delay": "0.4s",
        "name": "Security Gate",
        "model": "Lobster Trap + Offline detector",
        "icon": "🔒",
        "desc": (
            "Pre-LLM security layer that scans for prompt injection, credential "
            "leaks, role impersonation, and data exfiltration patterns before any "
            "AI agent sees the document. Contracts that trigger a rule are "
            "quarantined immediately — no LLM call is made."
        ),
        "outputs": "Security events · Quarantine decision · Threat classification",
    },
    {
        "cls": "a5", "num": "Agent 5", "delay": "0.5s",
        "name": "Approval Recommendation",
        "model": "Policy-based · No LLM",
        "icon": "🎯",
        "desc": (
            "Deterministic scoring engine that combines Agent 2 risk (50%), "
            "Agent 3 compliance (35%), and Agent 1 quality (15%) into a composite "
            "score 0–100. Hard override rules can force REJECT regardless of score. "
            "Thresholds are configurable in the Scoring Policy page."
        ),
        "outputs": "AUTO_APPROVE · MANAGER_REVIEW · LEGAL_REVIEW · REJECT",
    },
]

cols = st.columns(3)
for i, agent in enumerate(_agents[:3]):
    with cols[i]:
        st.markdown(f"""
        <div class="agent-card {agent['cls']}" style="animation-delay:{agent['delay']};">
            <div class="agent-num">{agent['num']}</div>
            <div class="agent-name">{agent['icon']} {agent['name']}</div>
            <div class="agent-model">{agent['model']}</div>
            <div class="agent-desc">{agent['desc']}</div>
            <div style="margin-top:1rem;padding-top:0.75rem;border-top:1px solid #212C4D;">
                <span style="font-size:0.7rem;color:#7E89AC;font-weight:600;text-transform:uppercase;letter-spacing:0.05em;">Outputs</span><br>
                <span style="font-size:0.78rem;color:#AEB9E1;">{agent['outputs']}</span>
            </div>
        </div>
        """, unsafe_allow_html=True)

st.markdown("<div style='height:1rem'></div>", unsafe_allow_html=True)

col_a, col_b = st.columns(2)
for col, agent in zip([col_a, col_b], _agents[3:]):
    with col:
        st.markdown(f"""
        <div class="agent-card {agent['cls']}" style="animation-delay:{agent['delay']};">
            <div class="agent-num">{agent['num']}</div>
            <div class="agent-name">{agent['icon']} {agent['name']}</div>
            <div class="agent-model">{agent['model']}</div>
            <div class="agent-desc">{agent['desc']}</div>
            <div style="margin-top:1rem;padding-top:0.75rem;border-top:1px solid #212C4D;">
                <span style="font-size:0.7rem;color:#7E89AC;font-weight:600;text-transform:uppercase;letter-spacing:0.05em;">Outputs</span><br>
                <span style="font-size:0.78rem;color:#AEB9E1;">{agent['outputs']}</span>
            </div>
        </div>
        """, unsafe_allow_html=True)

# ── Data layer ────────────────────────────────────────────────────────────────
st.markdown("<div style='height:1.5rem'></div>", unsafe_allow_html=True)
st.markdown(
    "<h2 style='font-size:1.4rem;font-weight:700;color:#FFFFFF;margin-bottom:0.25rem;'>"
    "🗄️ Data Layer</h2>"
    "<p style='color:#7E89AC;font-size:0.9rem;margin-bottom:1.25rem;'>"
    "Two storage systems work in parallel — PostgreSQL for structured data, "
    "Pinecone for semantic retrieval."
    "</p>",
    unsafe_allow_html=True,
)

db_col, pc_col = st.columns(2)

with db_col:
    st.markdown("""
    <div class="agent-card" style="animation-delay:0.6s;">
        <div class="agent-name">🐘 PostgreSQL</div>
        <div class="agent-model">Structured data store</div>
        <div class="agent-desc">
            Stores contracts, clauses, agent outputs, decisions, audit logs,
            security events, scoring policies, and reviewer feedback. Every
            agent action is versioned and auditable.
        </div>
        <div style="margin-top:1rem;padding-top:0.75rem;border-top:1px solid #212C4D;">
            <span style="font-size:0.78rem;color:#AEB9E1;">
            contracts · agent_outputs · decisions · audit_logs · scoring_policies · scoring_feedback
            </span>
        </div>
    </div>
    """, unsafe_allow_html=True)

with pc_col:
    st.markdown("""
    <div class="agent-card" style="animation-delay:0.7s;">
        <div class="agent-name">🌲 Pinecone</div>
        <div class="agent-model">Vector semantic retrieval</div>
        <div class="agent-desc">
            Two namespaces: <strong style="color:#9A91FB;">contracts</strong> stores
            clause embeddings from past uploads (used by Agent 2 for risk comparators).
            <strong style="color:#57C3FF;">policies</strong> stores your internal policy
            corpus (used by Agent 3 for HIPAA / SOC 2 / GDPR requirement retrieval).
        </div>
        <div style="margin-top:1rem;padding-top:0.75rem;border-top:1px solid #212C4D;">
            <span style="font-size:0.78rem;color:#AEB9E1;">
            contracts namespace · policies namespace · clause-level embeddings
            </span>
        </div>
    </div>
    """, unsafe_allow_html=True)

# ── Nav quick-links ───────────────────────────────────────────────────────────
st.markdown("<div style='height:1.5rem'></div>", unsafe_allow_html=True)
st.markdown(
    "<h2 style='font-size:1.4rem;font-weight:700;color:#FFFFFF;margin-bottom:1rem;'>"
    "📍 Quick Navigation</h2>",
    unsafe_allow_html=True,
)

_pages = [
    ("📄", "Upload Contract",   "Drop a PDF/DOCX and watch the agents run in real-time."),
    ("🗂️", "Recent Uploads",    "Table view of all uploaded contracts with analysis highlights."),
    ("📊", "Risk Dashboard",    "Score distributions, vendor ranking, and anomaly callouts."),
    ("✅", "Review Queue",      "Contracts pending human approval, filtered by your role."),
    ("🔒", "Security Dashboard","Captured injection attempts and quarantine queue."),
    ("💬", "Ask Shield AI",     "Natural-language queries over the contracts database."),
    ("📒", "Audit Log",         "Every agent action and human decision, fully filterable."),
    ("⚖️", "Scoring Policy",    "Tune the hybrid scoring engine — weights, thresholds, rules."),
]

_pc = st.columns(4)
for i, (icon, name, desc) in enumerate(_pages):
    with _pc[i % 4]:
        st.markdown(
            f"<div style='background:#101935;border:1px solid #212C4D;border-radius:12px;"
            f"padding:1rem;margin-bottom:0.75rem;transition:border-color 0.2s;'>"
            f"<div style='font-size:1.3rem;margin-bottom:0.4rem;'>{icon}</div>"
            f"<div style='font-size:0.9rem;font-weight:600;color:#FFFFFF;margin-bottom:0.25rem;'>{name}</div>"
            f"<div style='font-size:0.78rem;color:#7E89AC;line-height:1.5;'>{desc}</div>"
            f"</div>",
            unsafe_allow_html=True,
        )

# ── Footer ────────────────────────────────────────────────────────────────────
st.markdown("<div style='height:2rem'></div>", unsafe_allow_html=True)
st.markdown(
    "<div style='text-align:center;color:#37446B;font-size:0.78rem;padding:1rem 0;border-top:1px solid #212C4D;'>"
    "Shield AI v0.3.0 · Built for the Hackathon · Powered by Gemini + Pinecone + PostgreSQL"
    "</div>",
    unsafe_allow_html=True,
)
