"""Data Recovery — admin-only page for failed DB/Pinecone writes.

Only accessible to Auditors (highest access level). Shows all entries in
the write-ahead cache that failed to persist to the primary datastore.

Each entry shows:
  - Entity type (what was being written)
  - Source (which module attempted the write)
  - Error (why it failed)
  - Data payload (what was lost)
  - Retry status

Entries can be deleted after manual recovery.
"""
import sys
import pathlib
import json

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

import streamlit as st
from utils import api_get, api_delete, current_role, gate, get_service_status, render_topbar, setup_sidebar

st.set_page_config(page_title="Data Recovery — Shield AI", page_icon="💾", layout="wide")
setup_sidebar()
render_topbar("Data Recovery", "💾")

gate("view_data_recovery", "This page is restricted to **Auditors** only.")

st.markdown(
    "This page shows data that **could not be saved** to the primary datastore "
    "(PostgreSQL or Pinecone) due to connectivity issues. Each entry was written "
    "to the local write-ahead cache instead of being silently dropped. "
    "Review each entry and take manual action to restore it."
)

# Service status banner
try:
    svc = get_service_status()
    db_ok = svc.get("db", {}).get("connected", True)
    pinecone_ok = svc.get("pinecone", {}).get("available", True)

    status_cols = st.columns(3)
    status_cols[0].metric(
        "PostgreSQL",
        "✅ Connected" if db_ok else "❌ Unreachable",
        delta=None,
    )
    status_cols[1].metric(
        "Pinecone",
        "✅ Available" if pinecone_ok else "❌ Unreachable",
        delta=None,
    )
    status_cols[2].metric(
        "Cache entries",
        svc.get("cache_pending", 0),
        delta="pending recovery" if svc.get("cache_pending", 0) > 0 else "all clear",
        delta_color="inverse" if svc.get("cache_pending", 0) > 0 else "normal",
    )
except Exception as e:
    st.warning(f"Could not fetch service status: {e}")

st.divider()

# Fetch cache entries
try:
    resp = api_get("/health/cache")
    cache_data = resp.json()
    entries = cache_data.get("entries", [])
    total = cache_data.get("count", 0)
except Exception as e:
    st.error(f"Could not fetch cache entries: {e}")
    st.stop()

if not entries:
    st.success("✅ No pending cache entries. All data has been successfully persisted.")
    st.stop()

st.subheader(f"Pending entries ({total})")
st.caption(
    "These entries represent data that failed to write to PostgreSQL or Pinecone. "
    "Once you have manually recovered the data or the datastore is back online, "
    "delete the entry to clear it from the cache."
)

ENTITY_ICONS = {
    "contract_upload": "📄",
    "pipeline_status_update": "🔄",
    "pinecone_index": "📌",
    "agent_output": "🤖",
    "security_event": "🔒",
}

for entry in entries:
    icon = ENTITY_ICONS.get(entry.get("entity_type", ""), "📋")
    retried = entry.get("retried", False)
    retry_ok = entry.get("last_retry_success", False)

    status_badge = ""
    if retried and retry_ok:
        status_badge = "  ·  ✅ Retry succeeded"
    elif retried:
        status_badge = f"  ·  ⚠️ Retry attempted ({entry.get('retry_count', 0)}x)"

    with st.container(border=True):
        head_l, head_r = st.columns([4, 1])
        head_l.markdown(
            f"**{icon} {entry.get('entity_type', '?')}**  ·  "
            f"`{entry.get('id', '?')[:8]}…`  ·  "
            f"{entry.get('timestamp_iso', '')}"
            f"{status_badge}"
        )

        if head_r.button("🗑 Delete", key=f"del_{entry['id']}", help="Remove after manual recovery"):
            st.session_state[f"confirm_del_{entry['id']}"] = True

        if st.session_state.get(f"confirm_del_{entry['id']}"):
            c1, c2 = st.columns(2)
            if c1.button("Yes, delete", key=f"yes_{entry['id']}", type="primary"):
                r = api_delete(f"/health/cache/{entry['id']}")
                if r.status_code == 200:
                    st.success("Entry deleted.")
                    st.session_state.pop(f"confirm_del_{entry['id']}", None)
                    st.rerun()
                else:
                    st.error(f"Delete failed: {r.text}")
            if c2.button("Cancel", key=f"cancel_{entry['id']}"):
                st.session_state.pop(f"confirm_del_{entry['id']}", None)
                st.rerun()

        detail_cols = st.columns(2)
        detail_cols[0].markdown(f"**Source:** `{entry.get('source', '?')}`")
        if entry.get("error"):
            detail_cols[1].markdown(f"**Error:** {entry['error'][:100]}")

        with st.expander("📋 Data payload"):
            st.json(entry.get("data", {}))

        if entry.get("last_retry_at"):
            st.caption(
                f"Last retry: {entry['last_retry_at']}  ·  "
                f"Success: {entry.get('last_retry_success', False)}"
            )
