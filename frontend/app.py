"""Shield AI — Streamlit entry.

Hosts the simulated role switcher in the sidebar.
All pages read st.session_state.role to gate actions.

Run with: streamlit run frontend/app.py
"""
import streamlit as st

from utils import health_check

st.set_page_config(
    page_title="Shield AI",
    page_icon="🛡",
    layout="wide",
    initial_sidebar_state="expanded",
)

ROLES = [
    "Procurement Analyst",
    "Legal Reviewer",
    "Compliance Officer",
    "Executive",
    "Auditor",
]

ROLE_DESCRIPTIONS = {
    "Procurement Analyst": "Uploads contracts. Cannot approve.",
    "Legal Reviewer": "Approves / rejects contracts in the legal-review queue.",
    "Compliance Officer": "Approves / rejects contracts in the manager-review queue.",
    "Executive": "Read-only across dashboards.",
    "Auditor": "Read-only across everything, including the audit log.",
}

if "role" not in st.session_state:
    st.session_state.role = ROLES[0]

with st.sidebar:
    st.markdown("# 🛡 Shield AI")
    st.caption("AI Governance Platform")

    st.session_state.role = st.selectbox(
        "Active role",
        ROLES,
        index=ROLES.index(st.session_state.role),
        help="Simulates RBAC. Each page shows actions appropriate to the active role.",
    )
    st.caption(ROLE_DESCRIPTIONS.get(st.session_state.role, ""))

    st.divider()

    # Backend health indicator
    if health_check():
        st.success("Backend reachable")
    else:
        st.error("Backend not reachable — start it with `make backend`")

    st.divider()
    st.caption("v0.2.0 · Hackathon prototype")

# ---- Main panel ----

st.title("🛡 Shield AI")
st.subheader("AI Governance Platform for Enterprise Contracts")

st.markdown(
    """
Welcome. Use the sidebar to navigate.

#### Focus area coverage

- **RAG** over past contracts + policy docs + regulations
- **AI pipeline & validation** with multi-agent cross-checks and a pre-LLM security gate
- **Analytics agent** for natural-language querying ("Ask Shield AI")
- **Anomaly detection** via prompt-injection blocking + risk-score outliers
- **Knowledge graph** of parties, contracts, clauses, and risks
"""
)

st.divider()

st.markdown(
    """
#### Pages at a glance

- **📄 Upload Contract** — drop a PDF/DOCX, watch the agents run, see the recommendation
- **✅ Review Queue** — contracts pending human approval (filtered by role)
- **📊 Risk Dashboard** — score distribution, vendor ranking, anomaly callouts
- **🔒 Security Dashboard** — captured injection payloads, quarantine queue
- **💬 Ask Shield AI** — natural-language queries over the contracts DB
- **🕸 Knowledge Graph** — vendors → contracts → risks, hub view of recurring patterns
- **📒 Audit Log** — every agent action and human decision, filterable
"""
)
