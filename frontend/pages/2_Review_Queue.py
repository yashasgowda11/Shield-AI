"""Review Queue — contracts awaiting human approval.

Filter by status based on the active role:
  - Compliance Officer  → manager_review queue
  - Legal Reviewer      → legal_review queue
  - Auditor             → both queues, read-only

Approve / Reject / Escalate buttons POST to /contracts/{id}/decide.
"""
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

import streamlit as st
from utils import api_get, api_post, can, current_role, render_file_preview

st.title("✅ Review Queue")
role = current_role()
st.caption(f"Active role: **{role}**")


SEVERITY_BADGE = {
    "Low": "🟢", "Medium": "🟡", "High": "🟠", "Critical": "🔴",
}


def _queue_for_role(r: str) -> list[str]:
    """Which status queues this role can see."""
    if r == "Legal Reviewer":
        return ["legal_review"]
    if r == "Compliance Officer":
        return ["manager_review"]
    if r == "Auditor":
        return ["manager_review", "legal_review"]
    return []


queues = _queue_for_role(role)
if not queues:
    st.info(
        f"The **{role}** role doesn't review contracts. "
        "Switch to Legal Reviewer, Compliance Officer, or Auditor in the sidebar."
    )
    st.stop()

# Pull all contracts in the relevant queues
items: list[dict] = []
for status in queues:
    try:
        items.extend(api_get(f"/contracts/?status={status}").json())
    except Exception as e:
        st.warning(f"Couldn't reach backend for status={status}: {e}")

if not items:
    st.success("Queue is empty. Nothing pending review.")
    st.stop()

st.caption(f"{len(items)} contract(s) awaiting review.")

for c in items:
    contract_id = c["id"]
    detail = api_get(f"/contracts/{contract_id}").json()

    # Most recent AI decision (used to surface the recommendation reason)
    decisions = detail.get("decisions") or []
    ai_dec = next(
        (d for d in decisions if (d.get("reviewer_role") or "").startswith("agent:")),
        None,
    )
    risk = (detail.get("agent_outputs") or {}).get("risk", {}).get("output", {})
    score = risk.get("score", 0)

    with st.container(border=True):
        head_l, head_r = st.columns([3, 1])
        head_l.markdown(f"### {c['filename']}  ·  _status: {c['status']}_")
        head_r.metric("Risk score", f"{score}/100")

        if ai_dec:
            st.markdown(
                f"**AI recommendation:** `{ai_dec['recommendation']}`"
            )
            st.caption(ai_dec.get("reasoning") or "")

        # Top findings
        findings = risk.get("findings") or []
        if findings:
            st.markdown("**Top findings**")
            for f in findings[:3]:
                badge = SEVERITY_BADGE.get(f.get("severity", "?"), "")
                st.write(
                    f"{badge} **{f.get('severity', '?')}** · "
                    f"{f.get('risk', '?')} (§{f.get('clause_ref', '?')})"
                )

        # Compliance summary
        comp = (detail.get("agent_outputs") or {}).get("compliance", {}).get("output", {})
        if comp.get("frameworks"):
            line = "  ·  ".join(
                f"{'✅' if fw.get('passed') else '❌'} {fw['framework']}"
                for fw in comp["frameworks"]
            )
            st.markdown(f"**Compliance:** {line}")

        # ---- File preview ----
        with st.expander("📄  Preview original document"):
            render_file_preview(
                contract_id=contract_id,
                filename=c["filename"],
                raw_text=detail.get("raw_text"),
            )

        # Actions
        approve_perm = "approve_legal" if c["status"] == "legal_review" else "approve_manager"
        cols = st.columns(4)
        with cols[0]:
            if st.button("✅ Approve", key=f"approve_{contract_id}",
                         disabled=not can(approve_perm), type="primary"):
                r = api_post(
                    f"/contracts/{contract_id}/decide",
                    data={
                        "decision": "APPROVED",
                        "reasoning": f"Approved by {role}.",
                        "actor": f"user:{role}",
                    },
                )
                if r.status_code == 200:
                    st.success("Approved.")
                    st.rerun()
                else:
                    st.error(f"Failed: {r.text}")
        with cols[1]:
            if st.button("❌ Reject", key=f"reject_{contract_id}",
                         disabled=not can("reject")):
                r = api_post(
                    f"/contracts/{contract_id}/decide",
                    data={
                        "decision": "REJECTED",
                        "reasoning": f"Rejected by {role}.",
                        "actor": f"user:{role}",
                    },
                )
                if r.status_code == 200:
                    st.warning("Rejected.")
                    st.rerun()
                else:
                    st.error(f"Failed: {r.text}")
        with cols[2]:
            # Only managers escalate to legal; legal reviewers are the end of the line
            if c["status"] == "manager_review":
                if st.button("🔵 Escalate to legal",
                             key=f"escalate_{contract_id}",
                             disabled=not can("approve_manager")):
                    r = api_post(
                        f"/contracts/{contract_id}/decide",
                        data={
                            "decision": "ESCALATED_LEGAL",
                            "reasoning": f"Escalated to legal by {role}.",
                            "actor": f"user:{role}",
                        },
                    )
                    if r.status_code == 200:
                        st.info("Escalated.")
                        st.rerun()
                    else:
                        st.error(f"Failed: {r.text}")
        with cols[3]:
            st.caption(f"Uploaded {(c.get('uploaded_at') or '')[:19]}")
