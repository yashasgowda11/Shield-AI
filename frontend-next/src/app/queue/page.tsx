"use client";

import { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import Topbar from "@/components/layout/Topbar";
import StatusPill from "@/components/ui/StatusPill";
import ScoreBar from "@/components/ui/ScoreBar";
import { useRole } from "@/hooks/useRole";
import { api, type ContractDetail, type ContractSummary } from "@/lib/api";
import { ROLE_QUEUES, CAN_ASSIGN_ROLES, can } from "@/lib/roles";
import { fmtDate } from "@/lib/utils";
import { ChevronDown, ChevronUp, MessageSquare, ArrowUpRight, UserPlus } from "lucide-react";

/* ─── Role display helpers ───────────────────────────────────────────────── */

const ROLE_COLOR: Record<string, string> = {
  "Executive":          "#9B59B6",
  "Auditor":            "#1ABC9C",
  "Legal Reviewer":     "#38bdf8",
  "Compliance Officer": "#fbbf24",
  "system":             "#7E89AC",
};

const COMMENT_ICONS: Record<string, string> = {
  comment:        "💬",
  recommendation: "📝",
  escalation:     "🔵",
};

const ASSIGNABLE_ROLES = ["Executive", "Auditor", "Legal Reviewer", "Compliance Officer"] as const;

/* ─── Read-only banner ───────────────────────────────────────────────────── */
function ReadOnlyBanner({ role }: { role: string }) {
  const isAuditor = role === "Auditor";
  return (
    <div className="inline-flex items-center gap-1.5 text-xs px-3 py-1 rounded-full"
      style={{
        background: isAuditor ? "#1ABC9C18" : "#9B59B618",
        color: isAuditor ? "#1ABC9C" : "#9B59B6",
        border: `1px solid ${isAuditor ? "#1ABC9C40" : "#9B59B640"}`,
      }}>
      {isAuditor ? "🔍 Auditor" : "👔 Executive"} · Read-only · Can comment
    </div>
  );
}

/* ─── Assign panel ───────────────────────────────────────────────────────── */
function AssignPanel({
  contractId,
  onDone,
}: {
  contractId: number;
  onDone: () => void;
}) {
  const { role } = useRole();
  const [targetRole, setTargetRole] = useState("Executive");
  const [canApprove, setCanApprove] = useState(false);
  const [note, setNote] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [msg, setMsg] = useState<{ text: string; ok: boolean } | null>(null);

  async function submit() {
    setSubmitting(true);
    setMsg(null);
    try {
      await api.contracts.assign(
        contractId,
        targetRole,
        `user:${role}`,
        role,
        canApprove,
        note,
      );
      setMsg({ text: `Assigned to ${targetRole}${canApprove ? " with approve permission" : " (advisory)"}`, ok: true });
      setTimeout(onDone, 1500);
    } catch (e) {
      setMsg({ text: String(e), ok: false });
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="rounded-lg border p-4"
      style={{ background: "var(--bg-surface)", borderColor: "var(--accent)44" }}>
      <p className="text-xs font-bold uppercase tracking-wider mb-3" style={{ color: "var(--accent)" }}>
        Assign / Escalate to Role
      </p>

      <div className="flex flex-wrap gap-3 mb-3">
        <div>
          <label className="text-xs mb-1 block" style={{ color: "var(--text-muted)" }}>Target role</label>
          <select value={targetRole} onChange={e => setTargetRole(e.target.value)}
            className="text-sm rounded-lg px-3 py-1.5 border outline-none"
            style={{ background: "var(--bg-card)", borderColor: "var(--border)", color: "var(--text-secondary)" }}>
            {ASSIGNABLE_ROLES.map(r => (
              <option key={r} value={r}>{r}</option>
            ))}
          </select>
        </div>

        <div className="flex items-end pb-1">
          <label className="flex items-center gap-2 cursor-pointer text-xs" style={{ color: "var(--text-secondary)" }}>
            <input type="checkbox" checked={canApprove} onChange={e => setCanApprove(e.target.checked)}
              className="rounded" />
            Grant approve/reject permission
          </label>
        </div>
      </div>

      <textarea rows={2} value={note} onChange={e => setNote(e.target.value)}
        placeholder="Optional note to the assignee…"
        className="w-full text-sm rounded-lg px-3 py-2 border outline-none resize-none mb-3"
        style={{ background: "var(--bg-card)", borderColor: "var(--border)", color: "var(--text-secondary)" }}
      />

      <div className="flex items-center gap-2">
        <button onClick={submit} disabled={submitting}
          className="text-xs px-4 py-1.5 rounded-lg font-medium disabled:opacity-40"
          style={{ background: "var(--accent)", color: "#fff" }}>
          {submitting ? "Assigning…" : "Confirm Assignment"}
        </button>
        <button onClick={onDone}
          className="text-xs px-3 py-1.5 rounded-lg"
          style={{ background: "var(--bg-card)", color: "var(--text-muted)", border: "1px solid var(--border)" }}>
          Cancel
        </button>
      </div>

      {msg && (
        <p className="mt-2 text-xs" style={{ color: msg.ok ? "#22C55E" : "#f87171" }}>
          {msg.text}
        </p>
      )}
    </div>
  );
}

/* ─── Contract card ──────────────────────────────────────────────────────── */
function ContractCard({
  summary,
  onRefresh,
}: {
  summary: ContractSummary & { _assigned?: boolean };
  onRefresh: () => void;
}) {
  const { role } = useRole();
  const [open, setOpen]       = useState(false);
  const [detail, setDetail]   = useState<ContractDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [commentText, setCommentText] = useState("");
  const [commentType, setCommentType] = useState("comment");
  const [pendingAction, setPendingAction] = useState<string | null>(null);
  const [reason, setReason]   = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [msg, setMsg]         = useState<{ text: string; ok: boolean } | null>(null);
  const [showAssign, setShowAssign] = useState(false);

  const isReadOnly = role === "Executive" || role === "Auditor";
  const canAssign  = CAN_ASSIGN_ROLES.has(role as never);

  const loadDetail = useCallback(async () => {
    setLoading(true);
    try { setDetail(await api.contracts.get(summary.id)); }
    finally { setLoading(false); }
  }, [summary.id]);

  useEffect(() => { if (open && !detail) loadDetail(); }, [open, detail, loadDetail]);

  const aiDec  = detail?.decisions.find(d => d.reviewer_role.startsWith("agent:"));
  const sd     = aiDec?.scoring_details;
  const roleAssignment   = detail?.assignments.find(a => a.assigned_role === role && a.active);
  const canApproveViaAss = roleAssignment?.can_approve ?? false;

  const approveStatus = summary.status === "legal_review" ? "approve_legal" : "approve_manager";
  const canDecide = !isReadOnly && (can(role as never, approveStatus) || can(role as never, "reject") || canApproveViaAss);

  async function submitDecision() {
    if (!reason.trim() || !pendingAction) return;
    setSubmitting(true);
    try {
      await api.contracts.decide(summary.id, pendingAction, reason, `user:${role}`, role);
      setMsg({ text: `${pendingAction} recorded.`, ok: true });
      setPendingAction(null);
      setReason("");
      setDetail(null);
      onRefresh();
    } catch (e) {
      setMsg({ text: String(e), ok: false });
    } finally {
      setSubmitting(false);
    }
  }

  async function postComment() {
    if (!commentText.trim()) return;
    setSubmitting(true);
    try {
      await api.contracts.addComment(summary.id, commentText, role, `user:${role}`, commentType);
      setCommentText("");
      setDetail(null);
      await loadDetail();
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="rounded-xl border overflow-hidden"
      style={{ borderColor: "var(--border)", background: "var(--bg-card)" }}>

      {/* ── Header row ── */}
      <button className="w-full flex items-center justify-between px-5 py-4 text-left hover:brightness-110 transition"
        onClick={() => setOpen(o => !o)}>
        <div className="flex items-center gap-3 min-w-0 flex-1">
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="font-semibold text-sm text-white truncate max-w-xs">
                {summary.filename}
              </span>
              <StatusPill status={summary.status} />
              {summary._assigned && (
                <span className="text-xs px-2 py-0.5 rounded-full"
                  style={{ background: "#8B5CF618", color: "#A78BFA", border: "1px solid #8B5CF640" }}>
                  Escalated to you
                </span>
              )}
              {canApproveViaAss && (
                <span className="text-xs px-2 py-0.5 rounded-full"
                  style={{ background: "#22C55E15", color: "#22C55E", border: "1px solid #22C55E40" }}>
                  ✅ Approve permission
                </span>
              )}
              {isReadOnly && <ReadOnlyBanner role={role} />}
            </div>
            <p className="text-xs mt-0.5 truncate" style={{ color: "var(--text-muted)" }}>
              Uploaded {fmtDate(summary.uploaded_at)} · {summary.n_clauses} clause{summary.n_clauses !== 1 ? "s" : ""}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-3 shrink-0 ml-3">
          {sd && (
            <span className="text-base font-bold tabular-nums"
              style={{ color: sd.composite_score >= 82 ? "#4ade80" : sd.composite_score >= 63 ? "#fbbf24" : sd.composite_score >= 38 ? "#38bdf8" : "#f87171" }}>
              {sd.composite_score.toFixed(0)}
              <span className="text-xs font-normal" style={{ color: "var(--text-muted)" }}>/100</span>
            </span>
          )}
          {open
            ? <ChevronUp size={15} style={{ color: "var(--text-muted)" }} />
            : <ChevronDown size={15} style={{ color: "var(--text-muted)" }} />
          }
        </div>
      </button>

      {/* ── Expanded detail ── */}
      {open && (
        <div className="border-t px-5 pb-5 pt-4 flex flex-col gap-4" style={{ borderColor: "var(--border)" }}>
          {loading && (
            <div className="flex items-center gap-2 text-sm" style={{ color: "var(--text-muted)" }}>
              <div className="w-3 h-3 rounded-full border-2 border-t-transparent animate-spin"
                style={{ borderColor: "var(--accent)", borderTopColor: "transparent" }} />
              Loading…
            </div>
          )}

          {sd && <ScoreBar score={sd.composite_score} />}

          {/* AI rationale */}
          {sd?.rationale && sd.rationale.length > 0 && (
            <div>
              <p className="text-xs font-bold uppercase tracking-wider mb-2" style={{ color: "var(--text-muted)" }}>
                AI Rationale
              </p>
              <ul className="space-y-1">
                {sd.rationale.map((r, i) => (
                  <li key={i} className="text-sm flex gap-2" style={{ color: "var(--text-secondary)" }}>
                    <span className="shrink-0 mt-0.5" style={{ color: "var(--accent)" }}>·</span>
                    <span className="break-words">{r}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Active assignments */}
          {detail?.assignments && detail.assignments.filter(a => a.active).length > 0 && (
            <div>
              <p className="text-xs font-bold uppercase tracking-wider mb-2" style={{ color: "var(--text-muted)" }}>
                Assigned To
              </p>
              <div className="flex flex-wrap gap-2">
                {detail.assignments.filter(a => a.active).map(a => (
                  <div key={a.id} className="text-xs px-3 py-1.5 rounded-lg flex items-center gap-1.5"
                    style={{ background: "var(--bg-surface)", border: "1px solid var(--border)", color: "var(--text-secondary)" }}>
                    <span style={{ color: ROLE_COLOR[a.assigned_role] ?? "var(--accent)" }}>●</span>
                    <span>{a.assigned_role}</span>
                    {a.can_approve && (
                      <span className="text-xs ml-1" style={{ color: "#22C55E" }}>✓ approve</span>
                    )}
                    <span style={{ color: "var(--text-muted)" }}>· by {a.assigned_by?.replace("user:", "") ?? "?"}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Comments */}
          <div>
            <p className="text-xs font-bold uppercase tracking-wider mb-2 flex items-center gap-1"
              style={{ color: "var(--text-muted)" }}>
              <MessageSquare size={11} /> Comments ({detail?.comments?.length ?? 0})
            </p>
            <div className="space-y-2 mb-3">
              {(detail?.comments ?? []).map(c => (
                <div key={c.id} className="flex gap-2 text-sm rounded-lg p-2.5"
                  style={{
                    borderLeft: `3px solid ${ROLE_COLOR[c.role] ?? "#7E89AC"}`,
                    background: "var(--bg-surface)",
                  }}>
                  <span className="text-base shrink-0">{COMMENT_ICONS[c.comment_type] ?? "💬"}</span>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2 flex-wrap mb-0.5">
                      <span className="font-semibold text-xs" style={{ color: ROLE_COLOR[c.role] ?? "#7E89AC" }}>
                        {c.role}
                      </span>
                      <span className="text-xs" style={{ color: "var(--text-muted)" }}>
                        {fmtDate(c.created_at)}
                      </span>
                    </div>
                    <p className="text-xs leading-relaxed break-words" style={{ color: "var(--text-secondary)" }}>
                      {c.comment}
                    </p>
                  </div>
                </div>
              ))}
            </div>

            {/* Comment box — available to all roles that can comment */}
            {can(role as never, "comment") && (
              <div className="flex flex-col gap-2">
                <div className="flex gap-2 items-center flex-wrap">
                  <select value={commentType} onChange={e => setCommentType(e.target.value)}
                    className="text-xs rounded-lg px-2 py-1.5 border outline-none"
                    style={{ background: "var(--bg-surface)", borderColor: "var(--border)", color: "var(--text-secondary)" }}>
                    <option value="comment">💬 Comment</option>
                    <option value="recommendation">📝 Recommendation</option>
                  </select>
                  {isReadOnly && (
                    <span className="text-xs" style={{ color: "var(--text-muted)" }}>
                      Your {commentType === "recommendation" ? "recommendation" : "comment"} will be visible to reviewers.
                    </span>
                  )}
                </div>
                <textarea rows={2} value={commentText}
                  onChange={e => setCommentText(e.target.value)}
                  placeholder={commentType === "recommendation"
                    ? "Add your recommendation for reviewers…"
                    : "Add a comment…"}
                  className="w-full text-sm rounded-lg px-3 py-2 border outline-none resize-none"
                  style={{ background: "var(--bg-surface)", borderColor: "var(--border)", color: "var(--text-secondary)" }}
                />
                <div className="flex items-center gap-2">
                  <button onClick={postComment} disabled={submitting || !commentText.trim()}
                    className="text-xs px-3 py-1.5 rounded-lg font-medium disabled:opacity-40"
                    style={{ background: "var(--accent)", color: "#fff" }}>
                    {submitting ? "Posting…" : "Post"}
                  </button>
                </div>
              </div>
            )}
          </div>

          {/* Assign panel toggle — Legal/Compliance only */}
          {canAssign && !showAssign && (
            <button onClick={() => setShowAssign(true)}
              className="self-start flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg transition-opacity hover:opacity-80"
              style={{ background: "var(--bg-surface)", color: "var(--text-muted)", border: "1px solid var(--border)" }}>
              <UserPlus size={12} /> Assign to another role
            </button>
          )}
          {showAssign && (
            <AssignPanel
              contractId={summary.id}
              onDone={() => { setShowAssign(false); setDetail(null); loadDetail(); }}
            />
          )}

          {/* Decision buttons — non-read-only roles */}
          {canDecide && !pendingAction && (
            <div className="flex gap-2 flex-wrap">
              <button onClick={() => setPendingAction("APPROVED")}
                className="px-4 py-2 rounded-lg text-sm font-semibold transition hover:brightness-110"
                style={{ background: "#22C55E20", color: "#22C55E", border: "1px solid #22C55E40" }}>
                ✅ Approve
              </button>
              <button onClick={() => setPendingAction("REJECTED")}
                className="px-4 py-2 rounded-lg text-sm font-semibold transition hover:brightness-110"
                style={{ background: "#EF444420", color: "#EF4444", border: "1px solid #EF444440" }}>
                ❌ Reject
              </button>
              {summary.status === "manager_review" && can(role as never, "approve_manager") && (
                <button onClick={() => setPendingAction("ESCALATED_LEGAL")}
                  className="px-4 py-2 rounded-lg text-sm font-semibold transition hover:brightness-110"
                  style={{ background: "#38BDF820", color: "#38BDF8", border: "1px solid #38BDF840" }}>
                  🔵 Escalate to Legal
                </button>
              )}
            </div>
          )}

          {/* Reason + confirm */}
          {pendingAction && (
            <div className="rounded-lg p-4 border"
              style={{ borderColor: "var(--accent)44", background: "var(--bg-surface)" }}>
              <p className="text-xs font-bold uppercase tracking-wider mb-1" style={{ color: "var(--accent)" }}>
                Confirm: {pendingAction}
              </p>
              <p className="text-xs mb-3" style={{ color: "var(--text-muted)" }}>
                💡 Your reason is stored in the audit log and used to improve future AI decisions for this vendor.
              </p>
              <textarea rows={3} value={reason} onChange={e => setReason(e.target.value)}
                placeholder="Explain your decision. Be specific — e.g. 'Liability cap is 2× fees, acceptable for SaaS vendors.'"
                className="w-full text-sm rounded-lg px-3 py-2 border outline-none resize-none mb-3"
                style={{ background: "var(--bg-card)", borderColor: "var(--border)", color: "var(--text-secondary)" }}
              />
              <div className="flex gap-2">
                <button onClick={submitDecision} disabled={submitting || !reason.trim()}
                  className="px-4 py-2 rounded-lg text-sm font-semibold disabled:opacity-40"
                  style={{ background: "var(--accent)", color: "#fff" }}>
                  {submitting ? "Submitting…" : `Confirm ${pendingAction}`}
                </button>
                <button onClick={() => { setPendingAction(null); setReason(""); }}
                  className="px-4 py-2 rounded-lg text-sm border"
                  style={{ borderColor: "var(--border)", color: "var(--text-muted)" }}>
                  Cancel
                </button>
              </div>
            </div>
          )}

          {msg && (
            <p className="text-sm" style={{ color: msg.ok ? "#22C55E" : "#f87171" }}>
              {msg.text}
            </p>
          )}

          <Link href={`/contracts/${summary.id}`}
            className="self-start inline-flex items-center gap-1 text-xs hover:underline"
            style={{ color: "var(--text-muted)" }}>
            Full contract detail <ArrowUpRight size={11} />
          </Link>
        </div>
      )}
    </div>
  );
}

/* ─── Page ───────────────────────────────────────────────────────────────── */

export default function QueuePage() {
  const { role } = useRole();
  const [items, setItems] = useState<(ContractSummary & { _assigned?: boolean })[]>([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    const seen = new Set<number>();
    const all: (ContractSummary & { _assigned?: boolean })[] = [];

    for (const status of ROLE_QUEUES[role as keyof typeof ROLE_QUEUES] ?? []) {
      const res = await api.contracts
        .list({ status, limit: 100 })
        .catch(() => ({ items: [] as ContractSummary[], total: 0, limit: 100, offset: 0 }));
      res.items.forEach(r => { if (!seen.has(r.id)) { seen.add(r.id); all.push(r); } });
    }

    // Contracts explicitly assigned to this role
    const assignedRes = await api.contracts
      .list({ assigned_role: role, limit: 100 })
      .catch(() => ({ items: [] as ContractSummary[], total: 0, limit: 100, offset: 0 }));
    assignedRes.items.forEach(r => {
      if (!seen.has(r.id)) { seen.add(r.id); all.push({ ...r, _assigned: true }); }
    });

    // Sort newest first
    all.sort((a, b) => new Date(b.uploaded_at ?? 0).getTime() - new Date(a.uploaded_at ?? 0).getTime());
    setItems(all);
    setLoading(false);
  }, [role]);

  useEffect(() => { load(); }, [load]);

  const noAccess = !ROLE_QUEUES[role as keyof typeof ROLE_QUEUES]?.length
    && role !== "Auditor"
    && role !== "Executive";

  const isReadOnly = role === "Executive" || role === "Auditor";

  return (
    <>
      <Topbar title="Review Queue" />
      <main className="flex-1 overflow-y-auto min-h-0 p-4 sm:p-6 flex flex-col gap-4">

        {noAccess && (
          <div className="rounded-lg p-4 text-sm"
            style={{ background: "#F59E0B18", border: "1px solid #F59E0B40", color: "#F59E0B" }}>
            The <strong>{role}</strong> role doesn't have queue access. Switch to Legal Reviewer,
            Compliance Officer, Auditor, or Executive.
          </div>
        )}

        {/* Role info banner */}
        {isReadOnly && !noAccess && (
          <div className="rounded-lg px-4 py-3 flex items-center gap-3"
            style={{ background: "var(--bg-card)", border: "1px solid var(--border)" }}>
            <span className="text-lg">{role === "Executive" ? "👔" : "🔍"}</span>
            <div>
              <p className="text-sm font-medium" style={{ color: "var(--text-primary)" }}>
                {role} — Read-only queue access
              </p>
              <p className="text-xs" style={{ color: "var(--text-muted)" }}>
                You can view all queued contracts and leave comments or recommendations.
                Decisions are made by Legal Reviewers and Compliance Officers.
              </p>
            </div>
          </div>
        )}

        {loading ? (
          <div className="flex items-center gap-2 text-sm" style={{ color: "var(--text-muted)" }}>
            <div className="w-4 h-4 rounded-full border-2 border-t-transparent animate-spin"
              style={{ borderColor: "var(--accent)", borderTopColor: "transparent" }} />
            Loading queue…
          </div>
        ) : items.length === 0 ? (
          <div className="rounded-xl border p-12 text-center"
            style={{ background: "var(--bg-card)", borderColor: "var(--border)" }}>
            <p className="text-2xl mb-3">📭</p>
            <p className="text-sm font-medium" style={{ color: "var(--text-secondary)" }}>
              {isReadOnly
                ? "No contracts currently in the review queues."
                : "Your queue is empty — no contracts awaiting your review."}
            </p>
            <p className="text-xs mt-1" style={{ color: "var(--text-muted)" }}>
              Contracts in <em>manager_review</em> or <em>legal_review</em> status will appear here.
            </p>
          </div>
        ) : (
          <>
            <div className="flex items-center justify-between">
              <p className="text-xs" style={{ color: "var(--text-muted)" }}>
                {items.length} contract{items.length !== 1 ? "s" : ""} · newest first
              </p>
              <button onClick={load}
                className="text-xs px-3 py-1.5 rounded-lg"
                style={{ background: "var(--bg-card)", color: "var(--text-muted)", border: "1px solid var(--border)" }}>
                ↺ Refresh
              </button>
            </div>
            <div className="flex flex-col gap-3">
              {items.map(c => (
                <ContractCard key={c.id} summary={c} onRefresh={load} />
              ))}
            </div>
          </>
        )}
      </main>
    </>
  );
}
