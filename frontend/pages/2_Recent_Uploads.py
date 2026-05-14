"""Recent Uploads — table view of all contracts with analysis highlights.

Clicking a contract name navigates to the Contract Detail page.
Procurement Analysts can delete from here too.
"""
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

import streamlit as st
from utils import (
    api_get, api_delete, can, current_role,
    render_topbar, setup_sidebar,
)
from style import apply_theme, status_pill, score_color

st.set_page_config(page_title="Recent Uploads — Shield AI", page_icon="🗂️", layout="wide")
setup_sidebar()
render_topbar("Recent Uploads", "🗂️")

# ── Fetch contracts ───────────────────────────────────────────────────────────
try:
    contracts = api_get("/contracts/").json()
except Exception as e:
    st.error(f"Cannot reach backend: {e}")
    st.stop()

if not contracts:
    st.markdown(
        "<div style='text-align:center;padding:4rem;color:#7E89AC;'>"
        "<div style='font-size:3rem;margin-bottom:1rem;'>📂</div>"
        "<div style='font-size:1.1rem;font-weight:600;color:#FFFFFF;margin-bottom:0.5rem;'>No contracts yet</div>"
        "<div>Upload your first contract using the <strong>Upload Contract</strong> page.</div>"
        "</div>",
        unsafe_allow_html=True,
    )
    st.stop()

# ── Summary bar ───────────────────────────────────────────────────────────────
from collections import Counter
status_counts = Counter(c["status"] for c in contracts)

m_cols = st.columns(5)
_summary = [
    ("Total", len(contracts), "#6C72FF"),
    ("✅ Approved", status_counts.get("approved", 0), "#22c55e"),
    ("🔵 Legal review", status_counts.get("legal_review", 0), "#57C3FF"),
    ("🟡 Manager review", status_counts.get("manager_review", 0), "#FDB52A"),
    ("🔴 Rejected", status_counts.get("rejected", 0) + status_counts.get("quarantined", 0), "#ef4444"),
]
for col, (label, val, color) in zip(m_cols, _summary):
    col.markdown(
        f"<div style='background:#101935;border:1px solid #212C4D;border-radius:12px;"
        f"padding:1rem 1.25rem;text-align:center;'>"
        f"<div style='font-size:1.6rem;font-weight:700;color:{color};'>{val}</div>"
        f"<div style='font-size:0.72rem;color:#7E89AC;font-weight:600;text-transform:uppercase;"
        f"letter-spacing:0.05em;margin-top:2px;'>{label}</div>"
        f"</div>",
        unsafe_allow_html=True,
    )

st.markdown("<div style='height:1.25rem'></div>", unsafe_allow_html=True)

# ── Filter bar ────────────────────────────────────────────────────────────────
fc1, fc2, fc3 = st.columns([3, 2, 2])
with fc1:
    search = st.text_input("🔍  Search filename", placeholder="Type to filter…",
                            label_visibility="collapsed")
with fc2:
    all_statuses = sorted(set(c["status"] for c in contracts))
    status_filter = st.selectbox("Filter by status", ["All"] + all_statuses,
                                  label_visibility="collapsed")
with fc3:
    sort_by = st.selectbox("Sort by", ["Newest first", "Oldest first", "Risk score (high→low)"],
                            label_visibility="collapsed")

# Apply filters
filtered = contracts
if search:
    filtered = [c for c in filtered if search.lower() in c["filename"].lower()]
if status_filter != "All":
    filtered = [c for c in filtered if c["status"] == status_filter]

if sort_by == "Oldest first":
    filtered = sorted(filtered, key=lambda c: c.get("uploaded_at") or "")
elif sort_by == "Risk score (high→low)":
    # We'll sort after enriching with decisions below — for now keep newest first
    filtered = sorted(filtered, key=lambda c: c.get("uploaded_at") or "", reverse=True)
else:
    filtered = sorted(filtered, key=lambda c: c.get("uploaded_at") or "", reverse=True)

st.caption(f"Showing **{len(filtered)}** of **{len(contracts)}** contracts")
st.markdown("<div style='height:0.25rem'></div>", unsafe_allow_html=True)

# ── Table header ──────────────────────────────────────────────────────────────
_H_STYLE = (
    "font-size:0.7rem;font-weight:700;color:#7E89AC;text-transform:uppercase;"
    "letter-spacing:0.07em;padding:0.5rem 0.25rem;border-bottom:2px solid #212C4D;"
)
hcols = st.columns([4, 2, 1, 2, 2, 1])
for hcol, label in zip(hcols, ["Contract", "Status", "Clauses", "AI Decision", "Uploaded", "Action"]):
    hcol.markdown(f"<div style='{_H_STYLE}'>{label}</div>", unsafe_allow_html=True)

# ── Table rows ────────────────────────────────────────────────────────────────
_RECOMMENDATION_COLOR = {
    "AUTO_APPROVE":   "#22c55e",
    "MANAGER_REVIEW": "#FDB52A",
    "LEGAL_REVIEW":   "#57C3FF",
    "REJECT":         "#ef4444",
}

for c in filtered:
    contract_id = c["id"]
    uploaded_str = (c.get("uploaded_at") or "")[:16].replace("T", " ")

    # Fetch decision info (use cached summary endpoint for speed)
    ai_rec = "—"
    ai_color = "#7E89AC"
    try:
        detail_light = api_get(f"/contracts/{contract_id}").json()
        decisions = detail_light.get("decisions") or []
        ai_dec = next(
            (d for d in decisions if (d.get("reviewer_role") or "").startswith("agent:")),
            None,
        )
        if ai_dec:
            rec = ai_dec.get("recommendation", "")
            ai_rec = rec.replace("_", " ")
            ai_color = _RECOMMENDATION_COLOR.get(rec, "#7E89AC")

        # Also get composite score if available
        sd = (ai_dec or {}).get("scoring_details") or {}
        composite = sd.get("composite_score")
    except Exception:
        composite = None

    row_bg = "background:#101935;" if filtered.index(c) % 2 == 0 else "background:#0D1628;"
    rcols = st.columns([4, 2, 1, 2, 2, 1])

    # ── Filename (clickable button that navigates to detail page) ─────────────
    with rcols[0]:
        st.markdown(f"<div style='padding:0.5rem 0;'>", unsafe_allow_html=True)
        if st.button(
            f"📄 {c['filename'][:45]}{'…' if len(c['filename']) > 45 else ''}",
            key=f"view_{contract_id}",
            use_container_width=True,
            help="Click to view full analysis",
        ):
            st.session_state["view_contract_id"] = contract_id
            st.switch_page("pages/_contract_detail.py")
        st.markdown("</div>", unsafe_allow_html=True)

    # ── Status pill ───────────────────────────────────────────────────────────
    with rcols[1]:
        st.markdown(
            f"<div style='padding:0.6rem 0;'>{status_pill(c['status'])}</div>",
            unsafe_allow_html=True,
        )

    # ── Clause count ──────────────────────────────────────────────────────────
    with rcols[2]:
        st.markdown(
            f"<div style='padding:0.6rem 0;font-size:0.88rem;color:#AEB9E1;'>"
            f"{c.get('n_clauses', '—')}</div>",
            unsafe_allow_html=True,
        )

    # ── AI Decision + composite score ─────────────────────────────────────────
    with rcols[3]:
        score_str = f" · {composite:.0f}/100" if composite is not None else ""
        st.markdown(
            f"<div style='padding:0.6rem 0;font-size:0.82rem;font-weight:600;"
            f"color:{ai_color};'>{ai_rec}{score_str}</div>",
            unsafe_allow_html=True,
        )

    # ── Uploaded date ─────────────────────────────────────────────────────────
    with rcols[4]:
        st.markdown(
            f"<div style='padding:0.6rem 0;font-size:0.82rem;color:#7E89AC;'>"
            f"{uploaded_str} UTC</div>",
            unsafe_allow_html=True,
        )

    # ── Delete action ─────────────────────────────────────────────────────────
    with rcols[5]:
        if can("delete"):
            if st.button("🗑️", key=f"del_{contract_id}", help="Delete contract"):
                st.session_state[f"confirm_del_{contract_id}"] = True

    # Confirm delete (shown below this row)
    if st.session_state.get(f"confirm_del_{contract_id}"):
        with st.container(border=True):
            st.warning(
                f"⚠️ Delete **{c['filename']}**? "
                "This removes the file, all agent outputs, and decisions. "
                "Audit logs are kept."
            )
            cc1, cc2 = st.columns(2)
            if cc1.button("Yes, delete", key=f"yes_del_{contract_id}", type="primary"):
                r = api_delete(
                    f"/contracts/{contract_id}",
                    params={"actor": f"user:{current_role()}"},
                )
                if r.status_code == 200:
                    st.success(f"✅ Contract #{contract_id} deleted.")
                    st.session_state.pop(f"confirm_del_{contract_id}", None)
                    st.rerun()
                else:
                    st.error(f"Delete failed (HTTP {r.status_code}): {r.text}")
            if cc2.button("Cancel", key=f"cancel_del_{contract_id}"):
                st.session_state.pop(f"confirm_del_{contract_id}", None)
                st.rerun()

    st.markdown(
        "<div style='border-bottom:1px solid #1a2340;'></div>",
        unsafe_allow_html=True,
    )
