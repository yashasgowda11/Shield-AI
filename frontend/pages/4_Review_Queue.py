"""Review Queue — contracts awaiting human approval.

Filter by status based on the active role:
  - Compliance Officer  → manager_review queue
  - Legal Reviewer      → legal_review queue
  - Auditor             → both queues, read-only

Score display:
  - User view   → composite score (0-100, higher=better), sub-scores, rationale
  - LLM raw     → Agent 2 risk score, individual findings (collapsible)

Reinforcement:
  - Reviewers can mark AI scores as Too High / Too Low / Correct
  - Feedback is sent to /scoring-policy/feedback and surfaces in the Scoring Policy page
"""
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

import streamlit as st
from utils import api_get, api_post, can, current_role, render_file_preview, render_topbar, setup_sidebar
from score_descriptions import AGENT_SCORES, SEVERITY, FEEDBACK
from style import score_bar_html, score_color, status_pill

st.set_page_config(page_title="Review Queue — Shield AI", page_icon="✅", layout="wide")
setup_sidebar()
render_topbar("Review Queue", "✅")
role = current_role()


SEVERITY_BADGE = {"Low": "🟢", "Medium": "🟡", "High": "🟠", "Critical": "🔴"}
DECISION_COLOR = {
    "AUTO_APPROVE":   "green",
    "MANAGER_REVIEW": "orange",
    "LEGAL_REVIEW":   "red",
    "REJECT":         "red",
}



# ── Role capabilities ─────────────────────────────────────────────────────────

# Which status buckets each role sees by default
_ROLE_QUEUES = {
    "Legal Reviewer":     ["legal_review"],
    "Compliance Officer": ["manager_review"],
    "Auditor":            ["manager_review", "legal_review"],
    "Executive":          [],   # sees only what's assigned to them
}

# Roles that can leave comments / recommendations (all roles)
_CAN_COMMENT = {"Legal Reviewer", "Compliance Officer", "Auditor", "Executive", "Procurement Analyst"}

# Roles that can escalate to other roles
_CAN_ESCALATE = {"Legal Reviewer", "Compliance Officer"}

# Possible escalation targets per source role
_ESCALATION_TARGETS = {
    "Legal Reviewer":     ["Compliance Officer", "Executive", "Auditor"],
    "Compliance Officer": ["Legal Reviewer",     "Executive", "Auditor"],
}


def _load_queue(r: str) -> list[dict]:
    """Return all contracts this role should see in the queue."""
    items: list[dict] = []
    seen_ids: set[int] = set()

    # Default status-based queue
    for status in _ROLE_QUEUES.get(r, []):
        try:
            for c in api_get(f"/contracts/?status={status}").json():
                if c["id"] not in seen_ids:
                    items.append(c)
                    seen_ids.add(c["id"])
        except Exception as e:
            st.warning(f"Couldn't reach backend for status={status}: {e}")

    # Assignment-based queue (escalated contracts)
    try:
        for c in api_get(f"/contracts/?assigned_role={r}").json():
            if c["id"] not in seen_ids:
                c["_assigned"] = True   # flag so UI can show "escalated" badge
                items.append(c)
                seen_ids.add(c["id"])
    except Exception:
        pass

    return items


if role not in _ROLE_QUEUES and role not in _CAN_COMMENT:
    st.info(
        f"The **{role}** role doesn't have queue access. "
        "Switch to Legal Reviewer, Compliance Officer, Auditor, or Executive."
    )
    st.stop()

items = _load_queue(role)

if not items:
    if role == "Executive":
        st.info(
            "No contracts have been escalated to **Executive** yet. "
            "Legal or Compliance reviewers can escalate contracts to you from the Review Queue."
        )
    else:
        st.success("Queue is empty — nothing pending review.")
    st.stop()

st.caption(f"{len(items)} contract(s) in your queue.")


# ── Scoring display helpers ───────────────────────────────────────────────────

def _render_user_score_view(sd: dict, contract_id: int) -> None:
    """Composite score panel — what the reviewer needs to make a decision."""
    composite  = sd.get("composite_score", 0)
    risk_raw   = sd.get("risk_score", 0)
    comp_avg   = sd.get("compliance_average", 0)
    quality    = sd.get("quality_score", 0)
    critical_n = sd.get("critical_findings", 0)
    high_n     = sd.get("high_findings", 0)
    rationale  = sd.get("rationale") or []
    actions    = sd.get("required_actions") or []
    triggered  = sd.get("triggered_rules") or []

    # ── Composite score — full-width HTML bar (never truncates) ────────────────
    _comp_info = AGENT_SCORES["composite"]
    color = score_color(composite)
    pct   = min(max(composite, 0), 100)
    _BAND = (
        "AUTO APPROVE" if composite >= 82 else
        "MANAGER REVIEW" if composite >= 63 else
        "LEGAL REVIEW"  if composite >= 38 else
        "REJECT"
    )
    st.markdown(
        f"<div style='background:#0D1628;border:1px solid #212C4D;border-radius:12px;"
        f"padding:1.1rem 1.25rem;margin-bottom:0.75rem;'>"
        f"<div style='display:flex;justify-content:space-between;align-items:baseline;"
        f"margin-bottom:0.5rem;'>"
        f"  <span style='font-size:0.72rem;font-weight:700;color:#7E89AC;"
        f"  text-transform:uppercase;letter-spacing:0.07em;'>Composite Approval Score</span>"
        f"  <span style='font-size:0.78rem;font-weight:600;color:{color};"
        f"  background:rgba(0,0,0,0.2);padding:0.15rem 0.6rem;border-radius:999px;"
        f"  border:1px solid {color}55;'>{_BAND}</span>"
        f"</div>"
        f"<div style='display:flex;align-items:center;gap:0.75rem;'>"
        f"  <div style='flex:1;background:#1a2540;border-radius:6px;height:12px;overflow:hidden;'>"
        f"    <div style='width:{pct}%;height:100%;background:{color};"
        f"    border-radius:6px;transition:width 0.5s ease;'></div>"
        f"  </div>"
        f"  <span style='font-size:1.4rem;font-weight:800;color:{color};white-space:nowrap;'>"
        f"  {composite:.0f}<span style='font-size:0.85rem;color:#7E89AC;font-weight:500;'>/100</span>"
        f"  </span>"
        f"</div>"
        f"<div style='margin-top:0.35rem;font-size:0.75rem;color:#7E89AC;'>"
        f"  {_comp_info['threshold_hint']}"
        f"</div>"
        f"</div>",
        unsafe_allow_html=True,
    )
    with st.expander("ℹ️ What is the composite score?", expanded=False):
        st.markdown(_comp_info["description"])
        st.caption(f"**Thresholds:** {_comp_info['threshold_hint']}")

    # Sub-score breakdown
    sub_cols = st.columns(3)
    _risk_info = AGENT_SCORES["agent2_risk"]
    sub_cols[0].metric(
        "Risk contribution",
        f"{100 - risk_raw:.0f}/100",
        help=(
            f"{_risk_info['label']} · {_risk_info['range']}\n\n"
            f"{_risk_info['description']}\n\n"
            f"Threshold: {_risk_info['threshold_hint']}"
        ),
    )
    _comp_avg_info = AGENT_SCORES["agent3_compliance"]
    sub_cols[1].metric(
        "Compliance avg",
        f"{comp_avg:.0f}%",
        help=(
            f"{_comp_avg_info['label']} · {_comp_avg_info['range']}\n\n"
            f"{_comp_avg_info['description']}\n\n"
            f"Threshold: {_comp_avg_info['threshold_hint']}"
        ),
    )
    _qual_info = AGENT_SCORES["agent1_quality"]
    sub_cols[2].metric(
        "Contract quality",
        f"{quality:.0f}%",
        help=(
            f"{_qual_info['label']} · {_qual_info['range']}\n\n"
            f"{_qual_info['description']}\n\n"
            f"Note: {_qual_info['threshold_hint']}"
        ),
    )

    # Findings count
    finding_cols = st.columns(2)
    finding_cols[0].metric(
        "Critical findings", critical_n,
        delta=f"-{critical_n}" if critical_n else None,
        delta_color="inverse",
        help=f"🔴 Critical — {SEVERITY['Critical']}",
    )
    finding_cols[1].metric(
        "High findings", high_n,
        delta=f"-{high_n}" if high_n else None,
        delta_color="inverse",
        help=f"🟠 High — {SEVERITY['High']}",
    )

    # Triggered rules
    if triggered:
        st.markdown("**Triggered rules:**  " + "  ·  ".join(f"`{t}`" for t in triggered))

    # Rationale
    if rationale:
        st.markdown("**Why this decision:**")
        for line in rationale:
            st.markdown(f"- {line}")

    # Required actions
    if actions:
        st.markdown("**Required actions before approval:**")
        for a in actions:
            st.markdown(f"- ⚠️ {a}")


def _render_llm_raw_view(risk_output: dict, compliance_output: dict) -> None:
    """Collapsible panel showing the raw LLM outputs that fed the scoring engine."""
    with st.expander("🤖 Raw LLM outputs (Agent 2 risk + Agent 3 compliance)"):
        st.caption(
            "These are the unprocessed outputs from Gemini — "
            "the scoring engine used these to compute the composite score above."
        )

        risk_score = risk_output.get("score", "n/a")
        st.markdown(f"**Agent 2 raw risk score:** `{risk_score}/100`  "
                    f"_(0 = safe, 100 = risky — higher is worse here)_")

        findings = risk_output.get("findings") or []
        if findings:
            st.markdown("**Risk findings:**")
            for f in findings:
                sev = f.get("severity", "?")
                badge = SEVERITY_BADGE.get(sev, "•")
                sev_desc = SEVERITY.get(sev, "")
                st.markdown(
                    f"{badge} **{sev}** · {f.get('risk')} "
                    f"_(§{f.get('clause_ref', '?')})_ — {f.get('reasoning', '')}  \n"
                    f"<small style='color:grey'>*{sev_desc}*</small>" if sev_desc else
                    f"{badge} **{sev}** · {f.get('risk')} "
                    f"_(§{f.get('clause_ref', '?')})_ — {f.get('reasoning', '')}",
                    unsafe_allow_html=True,
                )

        frameworks = compliance_output.get("frameworks") or []
        if frameworks:
            st.markdown("**Agent 3 compliance results:**")
            for fw in frameworks:
                icon = "✅" if fw.get("passed") else "❌"
                st.markdown(f"{icon} **{fw.get('framework')}**")
                for chk in (fw.get("checks") or []):
                    p = "✓" if chk.get("present") else "✗"
                    st.caption(
                        f"  {p} {chk.get('requirement', '?')} "
                        f"({chk.get('severity', '?')})"
                    )


def _render_feedback_ui(contract_id: int, decision_id: int | None,
                         ai_decision: str | None, composite: float | None) -> None:
    """Inline reinforcement feedback widget."""
    st.markdown("**Score feedback** — help improve future AI decisions:")
    fb_cols = st.columns([1, 1, 1, 2])

    def _send(ftype: str, human_dec: str | None = None, notes: str = ""):
        payload = {
            "contract_id":    contract_id,
            "decision_id":    decision_id,
            "feedback_type":  ftype,
            "ai_decision":    ai_decision,
            "human_decision": human_dec,
            "composite_score": composite,
            "notes":          notes,
            "reviewer_role":  role,
        }
        try:
            import requests, os
            BACKEND = os.getenv("BACKEND_URL", "http://localhost:8000")
            r = requests.post(f"{BACKEND}/scoring-policy/feedback", json=payload, timeout=5)
            return r.ok
        except Exception:
            return False

    with fb_cols[0]:
        if st.button("✅ Score correct", key=f"fb_ok_{contract_id}",
                      help=FEEDBACK["correct"]):
            if _send("correct"):
                st.success("Recorded!")
    with fb_cols[1]:
        if st.button("📈 Too low", key=f"fb_low_{contract_id}",
                      help=FEEDBACK["too_low"]):
            if _send("too_low", notes="reviewer flagged score as too low"):
                st.warning("Feedback recorded — marked as too low.")
    with fb_cols[2]:
        if st.button("📉 Too high", key=f"fb_high_{contract_id}",
                      help=FEEDBACK["too_high"]):
            if _send("too_high", notes="reviewer flagged score as too high"):
                st.warning("Feedback recorded — marked as too high.")
    with fb_cols[3]:
        with st.expander("Add note + suggested decision"):
            note = st.text_input("Note", key=f"fb_note_{contract_id}", label_visibility="collapsed",
                                  placeholder="Optional context...")
            suggested = st.selectbox(
                "What should the decision have been?",
                ["(no change)", "AUTO_APPROVE", "MANAGER_REVIEW", "LEGAL_REVIEW", "REJECT"],
                key=f"fb_suggest_{contract_id}",
            )
            if st.button("Submit", key=f"fb_submit_{contract_id}"):
                human_dec = None if suggested == "(no change)" else suggested
                ftype = "correct" if not human_dec else (
                    "too_low" if ["AUTO_APPROVE","MANAGER_REVIEW"].index(human_dec or "") <
                                  ["AUTO_APPROVE","MANAGER_REVIEW","LEGAL_REVIEW","REJECT"].index(ai_decision or "REJECT")
                    else "too_high"
                ) if human_dec and ai_decision and human_dec in ["AUTO_APPROVE","MANAGER_REVIEW"] else "too_high"
                if _send(ftype, human_dec, note):
                    st.success("Feedback submitted.")


# ── Comments panel ───────────────────────────────────────────────────────────

_COMMENT_TYPE_ICON = {
    "comment":        "💬",
    "recommendation": "📝",
    "escalation":     "🔵",
}
_ROLE_COLOR = {
    "Executive":          "#9B59B6",
    "Auditor":            "#1ABC9C",
    "Legal Reviewer":     "#57C3FF",
    "Compliance Officer": "#FDB52A",
    "system":             "#7E89AC",
}

def _render_comments(contract_id: int, detail: dict) -> None:
    comments = detail.get("comments") or []
    with st.expander(
        f"💬 Comments & recommendations ({len(comments)})",
        expanded=bool(comments),
    ):
        if comments:
            for c in comments:
                r_color = _ROLE_COLOR.get(c["role"], "#7E89AC")
                icon    = _COMMENT_TYPE_ICON.get(c["comment_type"], "💬")
                ts      = (c.get("created_at") or "")[:16].replace("T", " ")
                st.markdown(
                    f"<div style='border-left:3px solid {r_color};padding:0.5rem 0.75rem;"
                    f"margin-bottom:0.5rem;background:#0D1628;border-radius:0 6px 6px 0;'>"
                    f"<span style='font-size:0.72rem;font-weight:700;color:{r_color};"
                    f"text-transform:uppercase;letter-spacing:0.05em;'>"
                    f"{icon} {c['role']}</span>"
                    f"<span style='font-size:0.68rem;color:#7E89AC;margin-left:0.5rem;'>{ts}</span><br>"
                    f"<span style='font-size:0.85rem;color:#D1D5E8;'>{c['comment']}</span>"
                    f"</div>",
                    unsafe_allow_html=True,
                )
        else:
            st.caption("No comments yet.")

        # Comment input — available to all roles
        if role in _CAN_COMMENT:
            st.markdown("---")
            ctype_options = {"General comment 💬": "comment", "Formal recommendation 📝": "recommendation"}
            ctype_label   = st.selectbox(
                "Type",
                list(ctype_options.keys()),
                key=f"ctype_{contract_id}",
                label_visibility="collapsed",
            )
            new_comment = st.text_area(
                "Leave a comment",
                key=f"comment_text_{contract_id}",
                placeholder=(
                    "Add your observations or recommendation. "
                    "All reviewers assigned to this contract will see this."
                ),
                height=80,
                label_visibility="collapsed",
            )
            if st.button("Post comment", key=f"post_comment_{contract_id}"):
                if not new_comment.strip():
                    st.warning("Comment cannot be empty.")
                else:
                    r2 = api_post(f"/contracts/{contract_id}/comment", data={
                        "comment":      new_comment.strip(),
                        "role":         role,
                        "actor":        f"user:{role}",
                        "comment_type": ctype_options[ctype_label],
                    })
                    if r2.status_code == 200:
                        st.success("Comment posted.")
                        st.rerun()
                    else:
                        st.error(f"Failed: {r2.text}")


def _render_escalation(contract_id: int, detail: dict) -> None:
    """Escalation panel — only shown for Legal Reviewer and Compliance Officer."""
    if role not in _CAN_ESCALATE:
        return

    assignments = detail.get("assignments") or []
    active_assignments = [a for a in assignments if a["active"]]
    targets = _ESCALATION_TARGETS.get(role, [])

    with st.expander(
        f"🔵 Escalate to another role"
        + (f"  ·  {len(active_assignments)} active assignment(s)" if active_assignments else ""),
        expanded=False,
    ):
        # Show existing active assignments
        if active_assignments:
            st.markdown("**Currently assigned to:**")
            for a in active_assignments:
                a_color = _ROLE_COLOR.get(a["assigned_role"], "#7E89AC")
                perm_badge = "✅ can approve/reject" if a["can_approve"] else "👁 advisory only"
                st.markdown(
                    f"<span style='color:{a_color};font-weight:600;'>{a['assigned_role']}</span> "
                    f"— <span style='color:#7E89AC;font-size:0.8rem;'>{perm_badge}</span>",
                    unsafe_allow_html=True,
                )
                if a.get("note"):
                    st.caption(f"  Note: {a['note']}")

            st.markdown("---")

        # New escalation form
        st.markdown("**Assign to an additional role:**")
        esc_target = st.selectbox(
            "Role to assign",
            targets,
            key=f"esc_target_{contract_id}",
        )
        esc_note = st.text_input(
            "Reason for escalation",
            key=f"esc_note_{contract_id}",
            placeholder="e.g. Contract value exceeds $5M — Executive sign-off required.",
        )
        esc_can_approve = st.checkbox(
            f"Grant **{esc_target}** approve / reject permission on this contract",
            key=f"esc_approve_{contract_id}",
            help=(
                "When checked, the assigned role can approve or reject this specific contract "
                "even if they normally only have read-only access."
            ),
        )

        if st.button(f"Escalate to {esc_target}", key=f"esc_submit_{contract_id}", type="primary"):
            if not esc_note.strip():
                st.warning("Please provide a reason for the escalation.")
            else:
                r2 = api_post(f"/contracts/{contract_id}/assign", data={
                    "assigned_role":   esc_target,
                    "assigned_by":     f"user:{role}",
                    "assigning_role":  role,
                    "can_approve":     str(esc_can_approve).lower(),
                    "note":            esc_note.strip(),
                })
                if r2.status_code == 200:
                    perm_msg = "with approve/reject permission" if esc_can_approve else "for advisory review"
                    st.success(f"Escalated to **{esc_target}** {perm_msg}.")
                    st.rerun()
                else:
                    st.error(f"Failed: {r2.text}")


# ── Main render loop ──────────────────────────────────────────────────────────

for c in items:
    contract_id = c["id"]
    detail      = api_get(f"/contracts/{contract_id}").json()

    decisions = detail.get("decisions") or []
    ai_dec    = next(
        (d for d in decisions if (d.get("reviewer_role") or "").startswith("agent:")),
        None,
    )
    scoring_details = (ai_dec or {}).get("scoring_details")

    # Check if this role has an active assignment with can_approve=True
    assignments = detail.get("assignments") or []
    role_assignment = next(
        (a for a in assignments if a["assigned_role"] == role and a["active"]),
        None,
    )
    assignment_can_approve = role_assignment and role_assignment.get("can_approve", False)

    risk_output = (detail.get("agent_outputs") or {}).get("risk",       {}).get("output", {})
    comp_output = (detail.get("agent_outputs") or {}).get("compliance", {}).get("output", {})

    # Fallback: if scoring_details not yet populated (old decisions), use raw risk score
    if scoring_details:
        _comp_val = scoring_details.get('composite_score', 0)
        _comp_color = score_color(_comp_val)
        _score_html = (
            f"<div style='text-align:right;'>"
            f"<div style='font-size:0.68rem;color:#7E89AC;font-weight:600;"
            f"text-transform:uppercase;letter-spacing:0.06em;'>Composite</div>"
            f"<div style='font-size:1.6rem;font-weight:800;color:{_comp_color};line-height:1.1;'>"
            f"{_comp_val:.0f}"
            f"<span style='font-size:0.85rem;color:#7E89AC;font-weight:400;'>/100</span>"
            f"</div></div>"
        )
    else:
        _raw = risk_output.get('score', '—')
        _score_html = (
            f"<div style='text-align:right;'>"
            f"<div style='font-size:0.68rem;color:#7E89AC;font-weight:600;"
            f"text-transform:uppercase;letter-spacing:0.06em;'>Risk score</div>"
            f"<div style='font-size:1.6rem;font-weight:800;color:#ef4444;line-height:1.1;'>"
            f"{_raw}"
            f"<span style='font-size:0.85rem;color:#7E89AC;font-weight:400;'>/100</span>"
            f"</div></div>"
        )

    with st.container(border=True):
        head_l, head_r = st.columns([4, 1])
        with head_l:
            escalated_badge = (
                "<span style='font-size:0.7rem;background:#9B59B622;color:#9B59B6;"
                "border:1px solid #9B59B655;border-radius:999px;padding:0.1rem 0.5rem;"
                "margin-left:0.5rem;'>Escalated to you</span>"
                if c.get("_assigned") else ""
            )
            assigned_advisory = (
                "<span style='font-size:0.7rem;background:#1ABC9C22;color:#1ABC9C;"
                "border:1px solid #1ABC9C55;border-radius:999px;padding:0.1rem 0.5rem;"
                "margin-left:0.5rem;'>Advisory review</span>"
                if role_assignment and not assignment_can_approve else ""
            )
            assigned_approve = (
                "<span style='font-size:0.7rem;background:#22c55e22;color:#22c55e;"
                "border:1px solid #22c55e55;border-radius:999px;padding:0.1rem 0.5rem;"
                "margin-left:0.5rem;'>✅ Approve permission granted</span>"
                if assignment_can_approve else ""
            )
            st.markdown(
                f"<div style='font-size:1rem;font-weight:700;color:#FFFFFF;'>"
                f"{c['filename']}{escalated_badge}{assigned_advisory}{assigned_approve}</div>"
                f"<div style='margin-top:0.2rem;'>{status_pill(c['status'])}</div>",
                unsafe_allow_html=True,
            )
        with head_r:
            st.markdown(_score_html, unsafe_allow_html=True)

        if ai_dec:
            decision_code = ai_dec.get("recommendation", "")
            _REC = {"AUTO_APPROVE":"#22c55e","MANAGER_REVIEW":"#FDB52A",
                    "LEGAL_REVIEW":"#57C3FF","REJECT":"#ef4444"}
            _dc = _REC.get(decision_code, "#7E89AC")
            st.markdown(
                f"<span style='font-size:0.8rem;color:{_dc};font-weight:600;"
                f"background:rgba(0,0,0,0.2);padding:0.15rem 0.6rem;border-radius:999px;"
                f"border:1px solid {_dc}44;'>AI: {decision_code}</span>",
                unsafe_allow_html=True,
            )

        # ── Score breakdown tab ────────────────────────────────────────────────
        tab_user, tab_llm = st.tabs(["📊 Score breakdown (user view)", "🤖 Raw LLM output"])

        with tab_user:
            if scoring_details:
                _render_user_score_view(scoring_details, contract_id)
            else:
                st.info("Detailed scoring breakdown not available for this contract — "
                        "reprocess it to generate composite scores.")
                # Fallback: show what we have
                findings = risk_output.get("findings") or []
                if findings:
                    st.markdown("**Top findings from Agent 2:**")
                    for f in findings[:3]:
                        badge = SEVERITY_BADGE.get(f.get("severity", "?"), "")
                        st.write(f"{badge} **{f.get('severity')}** · {f.get('risk')} (§{f.get('clause_ref', '?')})")
                if comp_output.get("frameworks"):
                    line = "  ·  ".join(
                        f"{'✅' if fw.get('passed') else '❌'} {fw['framework']}"
                        for fw in comp_output["frameworks"]
                    )
                    st.markdown(f"**Compliance:** {line}")

        with tab_llm:
            _render_llm_raw_view(risk_output, comp_output)

        # ── Comments & recommendations (all roles) ────────────────────────────
        _render_comments(contract_id, detail)

        # ── Escalation (Legal / Compliance only) ──────────────────────────────
        _render_escalation(contract_id, detail)

        # ── Feedback ──────────────────────────────────────────────────────────
        with st.expander("💬 Score feedback & reinforcement"):
            _render_feedback_ui(
                contract_id=contract_id,
                decision_id=(ai_dec or {}).get("id"),
                ai_decision=(ai_dec or {}).get("recommendation"),
                composite=(scoring_details or {}).get("composite_score"),
            )

        # ── Document preview ──────────────────────────────────────────────────
        with st.expander("📄 Preview original document"):
            render_file_preview(
                contract_id=contract_id,
                filename=c["filename"],
                raw_text=detail.get("raw_text"),
            )

        # ── Actions ───────────────────────────────────────────────────────────
        # A role can approve/reject if they hold the normal permission for this
        # queue status, OR if they have an active assignment with can_approve=True.
        approve_perm   = "approve_legal" if c["status"] == "legal_review" else "approve_manager"
        _default_can   = can(approve_perm)
        _decide_enabled = _default_can or assignment_can_approve

        # Track which action is pending confirmation per contract
        _pending_key = f"pending_action_{contract_id}"
        if _pending_key not in st.session_state:
            st.session_state[_pending_key] = None

        action_cols = st.columns([1, 1, 1, 2])

        with action_cols[0]:
            _approve_help = (
                "Approve/reject permission granted via escalation" if assignment_can_approve and not _default_can
                else ""
            )
            if st.button("✅ Approve", key=f"approve_{contract_id}",
                          disabled=not _decide_enabled, type="primary",
                          help=_approve_help or None):
                st.session_state[_pending_key] = "APPROVED"

        with action_cols[1]:
            if st.button("❌ Reject", key=f"reject_{contract_id}",
                          disabled=not (can("reject") or assignment_can_approve),
                          help=_approve_help or None):
                st.session_state[_pending_key] = "REJECTED"

        with action_cols[2]:
            if c["status"] == "manager_review" and can("approve_manager"):
                if st.button("🔵 Escalate to legal", key=f"escalate_{contract_id}"):
                    st.session_state[_pending_key] = "ESCALATED_LEGAL"

        with action_cols[3]:
            st.caption(f"Uploaded {(c.get('uploaded_at') or '')[:19]}")

        # ── Reason panel — shown after clicking an action button ──────────────
        pending = st.session_state.get(_pending_key)
        if pending:
            _action_labels = {
                "APPROVED":       ("✅ Approve",          "green",  "#22c55e"),
                "REJECTED":       ("❌ Reject",           "red",    "#ef4444"),
                "ESCALATED_LEGAL":("🔵 Escalate to legal","blue",  "#57C3FF"),
            }
            _label, _color, _hex = _action_labels[pending]

            st.markdown(
                f"<div style='border:1px solid {_hex}44;border-radius:10px;"
                f"padding:1rem 1.1rem;margin-top:0.5rem;background:#0D1628;'>"
                f"<div style='font-size:0.8rem;font-weight:700;color:{_hex};"
                f"text-transform:uppercase;letter-spacing:0.06em;margin-bottom:0.4rem;'>"
                f"{_label} — Confirm with reason</div>"
                f"<div style='font-size:0.72rem;color:#7E89AC;margin-bottom:0.6rem;'>"
                f"💡 Your reason is stored and used by the AI to improve future decisions "
                f"for this vendor. Be specific — e.g. <em>\"Liability cap is 2× fees, "
                f"acceptable for SaaS vendors of this size.\"</em>"
                f"</div></div>",
                unsafe_allow_html=True,
            )

            reason = st.text_area(
                "Reason for your decision",
                key=f"reason_text_{contract_id}_{pending}",
                placeholder=(
                    "Required — explain why you are making this decision. "
                    "This is shared with the AI to calibrate future recommendations."
                ),
                height=90,
                label_visibility="collapsed",
            )

            confirm_col, cancel_col, _ = st.columns([1, 1, 4])

            with confirm_col:
                if st.button(f"Confirm {_label}", key=f"confirm_{contract_id}_{pending}",
                              type="primary"):
                    if not reason.strip():
                        st.warning("Please enter a reason before confirming.")
                    else:
                        r = api_post(f"/contracts/{contract_id}/decide", data={
                            "decision":  pending,
                            "reasoning": reason.strip(),
                            "actor":     f"user:{role}",
                            "role":      role,
                        })
                        if r.status_code == 200:
                            st.session_state[_pending_key] = None
                            _msgs = {
                                "APPROVED":        ("✅ Approved. Your reason has been recorded and will inform future AI decisions.", "success"),
                                "REJECTED":        ("❌ Rejected. Your reason has been recorded.", "warning"),
                                "ESCALATED_LEGAL": ("🔵 Escalated to legal review.", "info"),
                            }
                            _msg, _kind = _msgs[pending]
                            getattr(st, _kind)(_msg)
                            st.rerun()
                        else:
                            st.error(f"Failed: {r.text}")

            with cancel_col:
                if st.button("Cancel", key=f"cancel_{contract_id}_{pending}"):
                    st.session_state[_pending_key] = None
                    st.rerun()
