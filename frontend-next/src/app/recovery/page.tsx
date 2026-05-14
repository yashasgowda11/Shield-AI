"use client";

import { useEffect, useState, useCallback } from "react";
import Topbar from "@/components/layout/Topbar";
import { fmtDate } from "@/lib/utils";

const BACKEND = "/api/backend";

// Matches the actual /health/services response from the backend
interface ServiceStatus {
  db?: { connected: boolean };
  pinecone?: { available: boolean };
  cache_pending?: number;
  lt?: { available: boolean; url?: string };
  gemini?: {
    fallback_active?: boolean;
    model_in_use?: string;
    primary_model?: string;
    fallback_reason?: string;
  };
}

interface CacheEntry {
  id: string;
  entity_type: string;
  source?: string;
  error_message?: string;
  created_at?: string;
  timestamp?: string;
  retry_count?: number;
  data?: Record<string, unknown>;
}

const ENTITY_ICONS: Record<string, string> = {
  contract_upload: "📄",
  pipeline_status_update: "🔄",
  pinecone_index: "📌",
  agent_output: "🤖",
};

function entityIcon(type: string): string {
  return ENTITY_ICONS[type] ?? "📦";
}

function CacheCard({ entry, onDelete }: { entry: CacheEntry; onDelete: () => void }) {
  const [expanded, setExpanded] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const ts = entry.created_at ?? entry.timestamp;

  async function doDelete() {
    setDeleting(true);
    try {
      const res = await fetch(`${BACKEND}/health/cache/${entry.id}`, { method: "DELETE" });
      if (!res.ok) throw new Error(await res.text());
      onDelete();
    } catch (e) {
      alert(String(e));
    } finally {
      setDeleting(false);
      setConfirming(false);
    }
  }

  return (
    <div className="rounded-xl border p-4" style={{ background: "var(--bg-card)", borderColor: "var(--border)" }}>
      <div className="flex flex-wrap items-start gap-3">
        <span className="text-2xl">{entityIcon(entry.entity_type)}</span>
        <div className="flex-1 min-w-0">
          <div className="flex flex-wrap items-center gap-2 mb-1">
            <span className="font-medium text-sm" style={{ color: "var(--text-primary)" }}>
              {entry.entity_type}
            </span>
            <code className="text-xs px-2 py-0.5 rounded"
              style={{ background: "var(--bg-surface)", color: "var(--text-muted)", border: "1px solid var(--border)" }}>
              {entry.id.slice(0, 12)}…
            </code>
            {entry.source && (
              <span className="text-xs" style={{ color: "var(--text-muted)" }}>via {entry.source}</span>
            )}
          </div>
          {ts && <p className="text-xs" style={{ color: "var(--text-muted)" }}>{fmtDate(ts)}</p>}
          {entry.error_message && (
            <p className="text-xs mt-1 px-2 py-1 rounded"
              style={{ background: "#DC262618", color: "#f87171", border: "1px solid #DC262640" }}>
              {entry.error_message}
            </p>
          )}
          {entry.retry_count !== undefined && (
            <p className="text-xs mt-1" style={{ color: "var(--text-muted)" }}>Retries: {entry.retry_count}</p>
          )}
        </div>
        <div className="flex gap-2">
          {entry.data && (
            <button onClick={() => setExpanded(v => !v)} className="text-xs px-2 py-1 rounded"
              style={{ background: "var(--bg-surface)", color: "var(--text-muted)", border: "1px solid var(--border)" }}>
              {expanded ? "Hide" : "Data"}
            </button>
          )}
          {confirming ? (
            <div className="flex gap-1">
              <button onClick={doDelete} disabled={deleting} className="text-xs px-2 py-1 rounded"
                style={{ background: "#DC262620", color: "#f87171", border: "1px solid #DC262640" }}>
                {deleting ? "…" : "Confirm"}
              </button>
              <button onClick={() => setConfirming(false)} className="text-xs px-2 py-1 rounded"
                style={{ background: "var(--bg-surface)", color: "var(--text-muted)", border: "1px solid var(--border)" }}>
                Cancel
              </button>
            </div>
          ) : (
            <button onClick={() => setConfirming(true)} className="text-xs px-2 py-1 rounded"
              style={{ background: "#DC262618", color: "#f87171", border: "1px solid #DC262640" }}>
              Delete
            </button>
          )}
        </div>
      </div>
      {expanded && entry.data && (
        <pre className="mt-3 text-xs rounded-lg p-3 overflow-x-auto"
          style={{ background: "var(--bg-base)", color: "var(--text-secondary)", border: "1px solid var(--border)", fontFamily: "monospace", maxHeight: 250 }}>
          {JSON.stringify(entry.data, null, 2)}
        </pre>
      )}
    </div>
  );
}

export default function DataRecoveryPage() {
  const [services, setServices] = useState<ServiceStatus | null>(null);
  const [entries, setEntries] = useState<CacheEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [sRes, cRes] = await Promise.all([
        fetch(`${BACKEND}/health/services`),
        fetch(`${BACKEND}/health/cache`),
      ]);
      if (sRes.ok) setServices(await sRes.json());
      if (cRes.ok) {
        const data = await cRes.json();
        // Backend returns { entries: [...], count: N }
        setEntries(Array.isArray(data) ? data : (data.entries ?? data.items ?? []));
      }
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  function removeEntry(id: string) {
    setEntries(prev => prev.filter(e => e.id !== id));
  }

  // Backend returns: { db: {connected}, pinecone: {available}, cache_pending: N }
  const pgConnected = services?.db?.connected ?? false;
  const pineconeAvail = services?.pinecone?.available ?? false;
  const cacheCount = services?.cache_pending ?? entries.length;
  const ltAvailable = services?.lt?.available;
  const geminiModel = services?.gemini?.model_in_use ?? services?.gemini?.primary_model;
  const geminiFallback = services?.gemini?.fallback_active;

  return (
    <>
      <Topbar title="Data Recovery" />
      <main className="p-4 sm:p-6 flex flex-col gap-5 max-w-5xl w-full mx-auto flex-1 overflow-y-auto min-h-0">
        <div className="rounded-lg border px-4 py-3 text-sm"
          style={{ background: "var(--bg-card)", borderColor: "var(--border)", color: "var(--text-secondary)" }}>
          <strong style={{ color: "var(--text-primary)" }}>Write-ahead cache fallback</strong> — contracts and
          pipeline outputs that failed to persist are stored here and can be retried or deleted once the
          underlying service recovers.
        </div>

        {error && (
          <div className="rounded-lg p-4 text-sm border"
            style={{ color: "#f87171", background: "#DC262618", borderColor: "#DC262640" }}>
            {error}
          </div>
        )}

        {/* ── Service status ── */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {/* PostgreSQL */}
          <div className="rounded-xl border p-5" style={{ background: "var(--bg-card)", borderColor: "var(--border)" }}>
            <div className="flex items-center gap-2 mb-2">
              <span className="text-base">🐘</span>
              <p className="text-xs font-semibold uppercase tracking-wider" style={{ color: "var(--text-muted)" }}>PostgreSQL</p>
            </div>
            <div className="flex items-center gap-2">
              <div className="w-2 h-2 rounded-full flex-shrink-0"
                style={{ background: loading ? "#7E89AC" : pgConnected ? "#22C55E" : "#DC2626" }} />
              <p className="text-sm font-bold"
                style={{ color: loading ? "var(--text-muted)" : pgConnected ? "#22C55E" : "#DC2626" }}>
                {loading ? "Checking…" : pgConnected ? "Connected" : "Unreachable"}
              </p>
            </div>
          </div>

          {/* Pinecone */}
          <div className="rounded-xl border p-5" style={{ background: "var(--bg-card)", borderColor: "var(--border)" }}>
            <div className="flex items-center gap-2 mb-2">
              <span className="text-base">📌</span>
              <p className="text-xs font-semibold uppercase tracking-wider" style={{ color: "var(--text-muted)" }}>Pinecone</p>
            </div>
            <div className="flex items-center gap-2">
              <div className="w-2 h-2 rounded-full flex-shrink-0"
                style={{ background: loading ? "#7E89AC" : pineconeAvail ? "#22C55E" : "#DC2626" }} />
              <p className="text-sm font-bold"
                style={{ color: loading ? "var(--text-muted)" : pineconeAvail ? "#22C55E" : "#DC2626" }}>
                {loading ? "Checking…" : pineconeAvail ? "Available" : "Unreachable"}
              </p>
            </div>
          </div>

          {/* Lobster Trap */}
          <div className="rounded-xl border p-5" style={{ background: "var(--bg-card)", borderColor: "var(--border)" }}>
            <div className="flex items-center gap-2 mb-2">
              <span className="text-base">🦞</span>
              <p className="text-xs font-semibold uppercase tracking-wider" style={{ color: "var(--text-muted)" }}>Security Gate</p>
            </div>
            <div className="flex items-center gap-2">
              <div className="w-2 h-2 rounded-full flex-shrink-0"
                style={{ background: loading ? "#7E89AC" : ltAvailable ? "#22C55E" : ltAvailable === false ? "#DC2626" : "#7E89AC" }} />
              <p className="text-sm font-bold"
                style={{ color: loading ? "var(--text-muted)" : ltAvailable ? "#22C55E" : ltAvailable === false ? "#DC2626" : "var(--text-muted)" }}>
                {loading ? "Checking…" : ltAvailable ? "Available" : ltAvailable === false ? "Offline (fallback)" : "Unknown"}
              </p>
            </div>
          </div>

          {/* Cache */}
          <div className="rounded-xl border p-5" style={{ background: "var(--bg-card)", borderColor: "var(--border)" }}>
            <div className="flex items-center gap-2 mb-2">
              <span className="text-base">💾</span>
              <p className="text-xs font-semibold uppercase tracking-wider" style={{ color: "var(--text-muted)" }}>Cache Pending</p>
            </div>
            <p className="text-2xl font-bold"
              style={{ color: loading ? "var(--text-muted)" : cacheCount > 0 ? "#F97316" : "#22C55E" }}>
              {loading ? "—" : cacheCount}
            </p>
            <p className="text-xs mt-1" style={{ color: "var(--text-muted)" }}>
              {cacheCount > 0 ? "entries need recovery" : "all clear"}
            </p>
          </div>
        </div>

        {/* Gemini model info */}
        {services?.gemini && (
          <div className="rounded-xl border p-4 flex flex-wrap items-center gap-3"
            style={{ background: "var(--bg-card)", borderColor: "var(--border)" }}>
            <span className="text-sm">🤖</span>
            <div>
              <span className="text-xs font-semibold" style={{ color: "var(--text-primary)" }}>
                Gemini: {geminiModel ?? "unknown"}
              </span>
              {geminiFallback && (
                <span className="ml-2 text-xs px-2 py-0.5 rounded-full"
                  style={{ background: "#F9731620", color: "#F97316", border: "1px solid #F9731640" }}>
                  Fallback active
                </span>
              )}
            </div>
            {services.gemini.fallback_reason && (
              <span className="text-xs" style={{ color: "var(--text-muted)" }}>
                Reason: {services.gemini.fallback_reason}
              </span>
            )}
          </div>
        )}

        {/* ── Cache entries ── */}
        {loading ? (
          <div className="flex items-center gap-3 text-sm" style={{ color: "var(--text-muted)" }}>
            <div className="w-4 h-4 rounded-full border-2 border-t-transparent animate-spin"
              style={{ borderColor: "var(--accent)", borderTopColor: "transparent" }} />
            Loading cache entries…
          </div>
        ) : entries.length === 0 ? (
          <div className="rounded-xl border p-12 flex flex-col items-center gap-3"
            style={{ background: "var(--bg-card)", borderColor: "#22C55E40" }}>
            <span className="text-4xl">✅</span>
            <p className="text-base font-semibold" style={{ color: "#22C55E" }}>All data persisted successfully</p>
            <p className="text-xs text-center max-w-sm" style={{ color: "var(--text-muted)" }}>
              No pending cache entries. All pipeline outputs have been written to permanent storage.
            </p>
          </div>
        ) : (
          <div className="flex flex-col gap-3">
            <div className="flex items-center justify-between">
              <p className="text-xs font-semibold" style={{ color: "var(--text-muted)" }}>
                {entries.length} pending cache {entries.length === 1 ? "entry" : "entries"}
              </p>
              <button onClick={load} className="text-xs px-3 py-1.5 rounded-lg font-medium transition-opacity hover:opacity-80"
                style={{ background: "var(--accent)", color: "#fff" }}>
                Refresh
              </button>
            </div>
            {entries.map(entry => (
              <CacheCard key={entry.id} entry={entry} onDelete={() => removeEntry(entry.id)} />
            ))}
          </div>
        )}
      </main>
    </>
  );
}
