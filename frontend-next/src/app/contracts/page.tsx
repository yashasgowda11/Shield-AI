"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import Link from "next/link";
import Topbar from "@/components/layout/Topbar";
import StatusPill from "@/components/ui/StatusPill";
import { api, type ContractSummary } from "@/lib/api";
import { fmtDate } from "@/lib/utils";
import { FileText, Search, ChevronLeft, ChevronRight, SlidersHorizontal, Trash2, AlertTriangle } from "lucide-react";

const STATUS_OPTIONS = [
  { value: "",                label: "All statuses" },
  { value: "auto_approved",   label: "Auto-Approved" },
  { value: "manager_review",  label: "Manager Review" },
  { value: "legal_review",    label: "Legal Review" },
  { value: "rejected",        label: "Rejected" },
  { value: "processing",      label: "Processing" },
  { value: "extracted",       label: "Extracted" },
  { value: "quarantined",     label: "Quarantined" },
  { value: "uploaded",        label: "Uploaded" },
];

const SORT_OPTIONS = [
  { value: "newest", label: "Newest first" },
  { value: "oldest", label: "Oldest first" },
  { value: "clauses_desc", label: "Most clauses" },
  { value: "clauses_asc",  label: "Fewest clauses" },
];

const STATUS_META: Record<string, { color: string; bg: string; label: string }> = {
  auto_approved:  { color: "#22C55E", bg: "#22C55E18", label: "Auto-Approved" },
  manager_review: { color: "#F59E0B", bg: "#F59E0B18", label: "Manager Review" },
  legal_review:   { color: "#38BDF8", bg: "#38BDF818", label: "Legal Review" },
  rejected:       { color: "#EF4444", bg: "#EF444418", label: "Rejected" },
  processing:     { color: "#6C72FF", bg: "#6C72FF18", label: "Processing" },
  extracted:      { color: "#10B981", bg: "#10B98118", label: "Extracted" },
  quarantined:    { color: "#F97316", bg: "#F9731618", label: "Quarantined" },
  uploaded:       { color: "#7E89AC", bg: "#7E89AC18", label: "Uploaded" },
};

const LIMIT = 50;

function sortContracts(items: ContractSummary[], sort: string): ContractSummary[] {
  const copy = [...items];
  switch (sort) {
    case "oldest":
      return copy.sort((a, b) => new Date(a.uploaded_at ?? 0).getTime() - new Date(b.uploaded_at ?? 0).getTime());
    case "clauses_desc":
      return copy.sort((a, b) => b.n_clauses - a.n_clauses);
    case "clauses_asc":
      return copy.sort((a, b) => a.n_clauses - b.n_clauses);
    case "newest":
    default:
      return copy.sort((a, b) => new Date(b.uploaded_at ?? 0).getTime() - new Date(a.uploaded_at ?? 0).getTime());
  }
}

/* ── Delete confirmation modal ───────────────────────────────────────────── */
function DeleteModal({
  contract,
  onConfirm,
  onCancel,
  deleting,
}: {
  contract: ContractSummary;
  onConfirm: () => void;
  onCancel: () => void;
  deleting: boolean;
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ background: "rgba(0,0,0,0.6)", backdropFilter: "blur(4px)" }}>
      <div className="rounded-2xl border p-6 w-full max-w-md fade-in-up"
        style={{ background: "var(--bg-card)", borderColor: "var(--border)" }}>
        <div className="flex items-center gap-3 mb-4">
          <div className="rounded-full p-2" style={{ background: "#EF444420" }}>
            <AlertTriangle size={20} className="text-red-400" />
          </div>
          <h2 className="font-semibold text-base" style={{ color: "var(--text-primary)" }}>
            Delete Contract
          </h2>
        </div>
        <p className="text-sm mb-1" style={{ color: "var(--text-secondary)" }}>
          Are you sure you want to permanently delete:
        </p>
        <p className="text-sm font-medium mb-4 truncate" style={{ color: "var(--text-primary)" }}>
          {contract.filename}
        </p>
        <p className="text-xs mb-6 rounded-lg p-3" style={{ background: "#EF444410", color: "#EF4444", border: "1px solid #EF444430" }}>
          This removes the contract, all extracted clauses, risk scores, and Pinecone vectors. This cannot be undone.
        </p>
        <div className="flex gap-3 justify-end">
          <button
            onClick={onCancel}
            disabled={deleting}
            className="px-4 py-2 rounded-lg text-sm font-medium disabled:opacity-50"
            style={{ background: "var(--bg-surface)", color: "var(--text-secondary)", border: "1px solid var(--border)" }}
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            disabled={deleting}
            className="px-4 py-2 rounded-lg text-sm font-medium flex items-center gap-2 disabled:opacity-50"
            style={{ background: "#EF4444", color: "#fff" }}
          >
            {deleting
              ? <><div className="w-3.5 h-3.5 rounded-full border-2 border-white border-t-transparent spin" /> Deleting…</>
              : <><Trash2 size={14} /> Delete</>}
          </button>
        </div>
      </div>
    </div>
  );
}

export default function ContractsPage() {
  const [contracts, setContracts] = useState<ContractSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [deleteTarget, setDeleteTarget] = useState<ContractSummary | null>(null);
  const [deleting, setDeleting] = useState(false);

  // Filters
  const [statusFilter, setStatusFilter] = useState("");
  const [sort, setSort] = useState("newest");
  const [minClauses, setMinClauses] = useState("");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [filtersOpen, setFiltersOpen] = useState(false);

  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const handleDelete = async () => {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      await api.contracts.delete(deleteTarget.id, "Legal Reviewer");
      setContracts(prev => prev.filter(c => c.id !== deleteTarget.id));
      setTotal(prev => prev - 1);
      setDeleteTarget(null);
    } catch (e) {
      setError(`Delete failed: ${String(e)}`);
      setDeleteTarget(null);
    } finally {
      setDeleting(false);
    }
  };

  const load = useCallback(async (st: string, pg: number) => {
    setLoading(true);
    setError("");
    try {
      const offset = (pg - 1) * LIMIT;
      const res = await api.contracts.list({ status: st || undefined, limit: LIMIT, offset });
      setContracts(res.items);
      setTotal(res.total);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => load(statusFilter, page), 300);
  }, [statusFilter, page, load]);

  // Client-side filter + sort
  const visible = sortContracts(
    contracts.filter(c => {
      const mc = minClauses ? c.n_clauses >= Number(minClauses) : true;
      const sq = search ? c.filename.toLowerCase().includes(search.toLowerCase()) : true;
      return mc && sq;
    }),
    sort
  );

  const totalPages = Math.max(1, Math.ceil(total / LIMIT));

  // Status breakdown counts
  const breakdown = contracts.reduce<Record<string, number>>((acc, c) => {
    acc[c.status] = (acc[c.status] ?? 0) + 1;
    return acc;
  }, {});

  return (
    <>
      {deleteTarget && (
        <DeleteModal
          contract={deleteTarget}
          onConfirm={handleDelete}
          onCancel={() => setDeleteTarget(null)}
          deleting={deleting}
        />
      )}
      <Topbar title="Recent Uploads" />
      <main className="p-4 sm:p-6 flex flex-col gap-5 flex-1 overflow-y-auto min-h-0">

        {/* Status breakdown row */}
        {!loading && contracts.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {Object.entries(breakdown).map(([status, count]) => {
              const m = STATUS_META[status] ?? { color: "#7E89AC", bg: "#7E89AC18", label: status };
              return (
                <button
                  key={status}
                  onClick={() => { setStatusFilter(status === statusFilter ? "" : status); setPage(1); }}
                  className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-semibold transition-all hover:brightness-125"
                  style={{
                    background: statusFilter === status ? m.color : m.bg,
                    color: statusFilter === status ? "#fff" : m.color,
                    border: `1px solid ${m.color}40`,
                  }}
                >
                  <span>{count}</span>
                  <span>{m.label}</span>
                </button>
              );
            })}
            {statusFilter && (
              <button
                onClick={() => { setStatusFilter(""); setPage(1); }}
                className="inline-flex items-center gap-1 px-3 py-1.5 rounded-full text-xs"
                style={{ background: "var(--bg-card)", color: "var(--text-muted)", border: "1px solid var(--border)" }}
              >
                ✕ Clear filter
              </button>
            )}
          </div>
        )}

        {/* Filters bar */}
        <div className="flex flex-col gap-3">
          <div className="flex items-center gap-3 flex-wrap">
            {/* Search */}
            <div className="relative flex-1 min-w-[200px]">
              <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2" style={{ color: "var(--text-muted)" }} />
              <input
                type="text"
                value={search}
                onChange={e => setSearch(e.target.value)}
                placeholder="Search by filename…"
                className="w-full pl-9 pr-3 py-2 text-sm rounded-lg border outline-none"
                style={{ background: "var(--bg-card)", borderColor: "var(--border)", color: "var(--text-secondary)" }}
              />
            </div>

            {/* Sort */}
            <select
              value={sort}
              onChange={e => setSort(e.target.value)}
              className="text-sm rounded-lg px-3 py-2 border outline-none"
              style={{ background: "var(--bg-card)", borderColor: "var(--border)", color: "var(--text-secondary)" }}
            >
              {SORT_OPTIONS.map(o => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>

            {/* Toggle advanced filters */}
            <button
              onClick={() => setFiltersOpen(v => !v)}
              className="flex items-center gap-1.5 text-sm px-3 py-2 rounded-lg border transition-colors"
              style={{
                background: filtersOpen ? "var(--accent)" : "var(--bg-card)",
                borderColor: filtersOpen ? "var(--accent)" : "var(--border)",
                color: filtersOpen ? "#fff" : "var(--text-muted)",
              }}
            >
              <SlidersHorizontal size={14} />
              Filters
            </button>

            <p className="text-xs ml-auto" style={{ color: "var(--text-muted)" }}>
              {total} contract{total !== 1 ? "s" : ""} total
              {visible.length !== contracts.length && ` · ${visible.length} shown`}
            </p>
          </div>

          {/* Advanced filters panel */}
          {filtersOpen && (
            <div className="flex flex-wrap gap-4 rounded-xl border p-4 fade-in-up"
              style={{ background: "var(--bg-card)", borderColor: "var(--border)" }}>
              <div>
                <label className="text-xs font-medium block mb-1" style={{ color: "var(--text-muted)" }}>Status</label>
                <select
                  value={statusFilter}
                  onChange={e => { setStatusFilter(e.target.value); setPage(1); }}
                  className="text-sm rounded-lg px-3 py-1.5 border outline-none"
                  style={{ background: "var(--bg-surface)", borderColor: "var(--border)", color: "var(--text-secondary)" }}
                >
                  {STATUS_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
                </select>
              </div>

              <div>
                <label className="text-xs font-medium block mb-1" style={{ color: "var(--text-muted)" }}>Min Clauses</label>
                <input
                  type="number" min={0} value={minClauses}
                  onChange={e => setMinClauses(e.target.value)}
                  placeholder="e.g. 5"
                  className="w-24 text-sm rounded-lg px-3 py-1.5 border outline-none"
                  style={{ background: "var(--bg-surface)", borderColor: "var(--border)", color: "var(--text-secondary)" }}
                />
              </div>

              <div className="flex items-end">
                <button onClick={() => {
                  setStatusFilter(""); setMinClauses(""); setSearch(""); setSort("newest"); setPage(1);
                }} className="text-xs px-3 py-1.5 rounded-lg"
                  style={{ background: "var(--bg-surface)", color: "var(--text-muted)", border: "1px solid var(--border)" }}>
                  Reset all
                </button>
              </div>
            </div>
          )}
        </div>

        {/* Error */}
        {error && (
          <div className="rounded-lg p-4 text-sm text-red-400 bg-red-400/10 border border-red-400/20">
            Backend unreachable: {error}
          </div>
        )}

        {/* Table */}
        <div className="rounded-xl overflow-hidden border" style={{ borderColor: "var(--border)" }}>
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b text-xs uppercase tracking-wider"
                style={{ borderColor: "var(--border)", background: "var(--bg-surface)", color: "var(--text-muted)" }}>
                <th className="px-4 py-3 text-left">Filename</th>
                <th className="px-4 py-3 text-left">Status</th>
                <th className="px-4 py-3 text-left">Clauses</th>
                <th className="px-4 py-3 text-left">Uploaded</th>
                <th className="px-4 py-3 text-left">Action</th>
              </tr>
            </thead>
            <tbody>
              {loading && (
                <tr>
                  <td colSpan={5} className="px-4 py-12 text-center">
                    <div className="flex items-center justify-center gap-2" style={{ color: "var(--text-muted)" }}>
                      <div className="w-4 h-4 rounded-full border-2 border-t-transparent spin"
                        style={{ borderColor: "var(--accent)", borderTopColor: "transparent" }} />
                      Loading contracts…
                    </div>
                  </td>
                </tr>
              )}
              {!loading && visible.length === 0 && !error && (
                <tr>
                  <td colSpan={5} className="px-4 py-16 text-center" style={{ color: "var(--text-muted)" }}>
                    <FileText size={36} className="mx-auto mb-3 opacity-20" />
                    <p className="text-sm mb-2">No contracts found.</p>
                    {statusFilter && (
                      <button onClick={() => { setStatusFilter(""); setPage(1); }}
                        className="text-xs underline" style={{ color: "var(--accent)" }}>
                        Clear filter
                      </button>
                    )}
                    {!statusFilter && (
                      <Link href="/upload" className="text-xs underline" style={{ color: "var(--accent)" }}>
                        Upload a contract
                      </Link>
                    )}
                  </td>
                </tr>
              )}
              {!loading && visible.map((c, i) => {
                const m = STATUS_META[c.status];
                return (
                  <tr key={c.id} className="border-b transition-colors hover:brightness-110"
                    style={{
                      borderColor: "var(--border)",
                      background: i % 2 === 0 ? "var(--bg-card)" : "var(--bg-surface)",
                    }}>
                    <td className="px-4 py-3 font-medium text-white max-w-xs">
                      <div className="truncate">{c.filename}</div>
                      <div className="text-xs mt-0.5" style={{ color: "var(--text-muted)" }}>#{c.id}</div>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <StatusPill status={c.status} />
                        {m && (
                          <span className="text-xs font-medium hidden sm:inline" style={{ color: m.color }}>
                            {m.label}
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="px-4 py-3 text-sm font-medium" style={{ color: "var(--text-muted)" }}>
                      {c.n_clauses > 0 ? c.n_clauses : <span style={{ color: "var(--border)" }}>—</span>}
                    </td>
                    <td className="px-4 py-3 text-xs" style={{ color: "var(--text-muted)" }}>
                      {c.uploaded_at ? fmtDate(c.uploaded_at) : "—"}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <Link href={`/contracts/${c.id}`}
                          className="text-xs font-semibold px-3 py-1.5 rounded-lg transition-opacity hover:opacity-80 inline-flex items-center gap-1"
                          style={{ background: "var(--accent)", color: "#fff" }}>
                          View →
                        </Link>
                        <button
                          onClick={() => setDeleteTarget(c)}
                          className="p-1.5 rounded-lg transition-colors hover:bg-red-400/20 group"
                          title="Delete contract"
                          style={{ color: "var(--text-muted)", border: "1px solid var(--border)" }}
                        >
                          <Trash2 size={13} className="group-hover:text-red-400 transition-colors" />
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="flex items-center justify-center gap-3 mt-2">
            <button onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page === 1}
              className="flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs font-medium disabled:opacity-40"
              style={{ background: "var(--bg-card)", color: "var(--text-secondary)", border: "1px solid var(--border)" }}>
              <ChevronLeft size={14} /> Prev
            </button>
            <span className="text-xs" style={{ color: "var(--text-muted)" }}>
              Page {page} of {totalPages}
            </span>
            <button onClick={() => setPage(p => Math.min(totalPages, p + 1))} disabled={page === totalPages}
              className="flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs font-medium disabled:opacity-40"
              style={{ background: "var(--bg-card)", color: "var(--text-secondary)", border: "1px solid var(--border)" }}>
              Next <ChevronRight size={14} />
            </button>
          </div>
        )}
      </main>
    </>
  );
}
