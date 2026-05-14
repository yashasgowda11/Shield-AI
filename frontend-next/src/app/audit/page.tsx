"use client";

import { useEffect, useState, useCallback } from "react";
import Topbar from "@/components/layout/Topbar";
import { fmtDate } from "@/lib/utils";

const BACKEND = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";

interface AuditEntry {
  id: number;
  actor: string;
  action: string;
  resource?: string;
  contract_id?: number | null;
  before?: Record<string, unknown> | null;
  after?: Record<string, unknown> | null;
  created_at?: string;
  timestamp?: string;
}

function actorEmoji(actor: string): string {
  if (actor.startsWith("agent:")) return "🤖";
  if (actor.startsWith("user:")) return "👤";
  if (actor.startsWith("system")) return "⚙️";
  return "👤";
}

function JsonBlock({ data }: { data: Record<string, unknown> }) {
  return (
    <pre
      className="text-xs rounded-lg p-3 overflow-x-auto mt-1"
      style={{
        background: "var(--bg-base)",
        color: "var(--text-secondary)",
        border: "1px solid var(--border)",
        fontFamily: "monospace",
        maxHeight: 200,
      }}
    >
      {JSON.stringify(data, null, 2)}
    </pre>
  );
}

function AuditCard({ entry }: { entry: AuditEntry }) {
  const [expanded, setExpanded] = useState(false);
  const ts = entry.created_at ?? entry.timestamp;
  const hasBefore = entry.before && Object.keys(entry.before).length > 0;
  const hasAfter = entry.after && Object.keys(entry.after).length > 0;

  return (
    <div
      className="rounded-xl border p-4"
      style={{ background: "var(--bg-card)", borderColor: "var(--border)" }}
    >
      <div className="flex flex-wrap items-start gap-2">
        <span className="text-base">{actorEmoji(entry.actor)}</span>
        <div className="flex-1 min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-medium text-sm" style={{ color: "var(--text-primary)" }}>
              {entry.actor}
            </span>
            <code
              className="text-xs px-2 py-0.5 rounded"
              style={{ background: "var(--bg-surface)", color: "var(--accent)", border: "1px solid var(--border)" }}
            >
              {entry.action}
            </code>
            {entry.resource && (
              <span className="text-xs" style={{ color: "var(--text-secondary)" }}>
                on {entry.resource}
              </span>
            )}
            {entry.contract_id !== undefined && entry.contract_id !== null && (
              <span className="text-xs" style={{ color: "var(--text-muted)" }}>
                (Contract #{entry.contract_id})
              </span>
            )}
          </div>
          {ts && (
            <p className="text-xs mt-0.5" style={{ color: "var(--text-muted)" }}>
              {fmtDate(ts)}
            </p>
          )}
        </div>
        {(hasBefore || hasAfter) && (
          <button
            onClick={() => setExpanded((v) => !v)}
            className="text-xs px-2 py-1 rounded"
            style={{ background: "var(--bg-surface)", color: "var(--text-muted)", border: "1px solid var(--border)" }}
          >
            {expanded ? "Hide" : "Details"}
          </button>
        )}
      </div>

      {expanded && (
        <div className="mt-3 flex flex-col gap-2">
          {hasBefore && (
            <div>
              <p className="text-xs font-medium" style={{ color: "var(--text-muted)" }}>Before</p>
              <JsonBlock data={entry.before!} />
            </div>
          )}
          {hasAfter && (
            <div>
              <p className="text-xs font-medium" style={{ color: "var(--text-muted)" }}>After</p>
              <JsonBlock data={entry.after!} />
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default function AuditLogPage() {
  const [entries, setEntries] = useState<AuditEntry[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const [actor, setActor] = useState("");
  const [action, setAction] = useState("");
  const [contractId, setContractId] = useState("");
  const [limit, setLimit] = useState(100);

  const fetchAudit = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const q = new URLSearchParams();
      if (actor) q.set("actor", actor);
      if (action) q.set("action", action);
      if (contractId) q.set("contract_id", contractId);
      q.set("limit", String(limit));

      const res = await fetch(`${BACKEND}/audit/?${q}`);
      if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);
      const data = await res.json();
      // Support both {items, total} and plain array
      if (Array.isArray(data)) {
        setEntries(data);
        setTotal(data.length);
      } else {
        setEntries(data.items ?? data.entries ?? []);
        setTotal(data.total ?? (data.items ?? data.entries ?? []).length);
      }
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }, [actor, action, contractId, limit]);

  useEffect(() => {
    const t = setTimeout(fetchAudit, 400);
    return () => clearTimeout(t);
  }, [fetchAudit]);

  return (
    <>
      <Topbar title="Audit Log" />
      <main className="p-4 sm:p-6 flex flex-col gap-5 flex-1 overflow-y-auto min-h-0">
        <p className="text-sm" style={{ color: "var(--text-secondary)" }}>
          Append-only log of every action — agent runs, human decisions, security events, status changes.
        </p>

        {/* Filter bar */}
        <div
          className="rounded-xl border p-4 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3"
          style={{ background: "var(--bg-card)", borderColor: "var(--border)" }}
        >
          {[
            { label: "Actor", value: actor, onChange: setActor, placeholder: "e.g. agent:risk" },
            { label: "Action", value: action, onChange: setAction, placeholder: "e.g. pipeline_run" },
            { label: "Contract ID", value: contractId, onChange: setContractId, placeholder: "e.g. 42", type: "number" },
          ].map((f) => (
            <div key={f.label}>
              <label className="text-xs font-medium mb-1 block" style={{ color: "var(--text-muted)" }}>
                {f.label}
              </label>
              <input
                type={f.type ?? "text"}
                value={f.value}
                onChange={(e) => f.onChange(e.target.value)}
                placeholder={f.placeholder}
                className="w-full rounded-lg px-3 py-2 text-sm outline-none"
                style={{
                  background: "var(--bg-surface)",
                  color: "var(--text-primary)",
                  border: "1px solid var(--border)",
                }}
              />
            </div>
          ))}
          <div>
            <label className="text-xs font-medium mb-1 block" style={{ color: "var(--text-muted)" }}>
              Limit
            </label>
            <select
              value={limit}
              onChange={(e) => setLimit(Number(e.target.value))}
              className="w-full rounded-lg px-3 py-2 text-sm outline-none"
              style={{
                background: "var(--bg-surface)",
                color: "var(--text-primary)",
                border: "1px solid var(--border)",
              }}
            >
              {[25, 50, 100, 250].map((v) => (
                <option key={v} value={v}>{v}</option>
              ))}
            </select>
          </div>
        </div>

        {error && (
          <div
            className="rounded-lg p-4 text-sm border"
            style={{ color: "#f87171", background: "#DC262618", borderColor: "#DC262640" }}
          >
            {error}
          </div>
        )}

        {!loading && (
          <p className="text-xs" style={{ color: "var(--text-muted)" }}>
            {entries.length} of {total} entries
          </p>
        )}

        {loading ? (
          <div className="text-sm" style={{ color: "var(--text-muted)" }}>Loading audit entries…</div>
        ) : entries.length === 0 ? (
          <div
            className="rounded-xl border p-12 text-center"
            style={{ background: "var(--bg-card)", borderColor: "var(--border)" }}
          >
            <p className="text-sm" style={{ color: "var(--text-muted)" }}>No audit entries match the current filters.</p>
          </div>
        ) : (
          <div className="flex flex-col gap-3">
            {entries.map((entry) => (
              <AuditCard key={entry.id} entry={entry} />
            ))}
          </div>
        )}
      </main>
    </>
  );
}
