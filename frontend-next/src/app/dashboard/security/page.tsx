"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import Topbar from "@/components/layout/Topbar";
import { ShieldAlert, ExternalLink } from "lucide-react";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell,
} from "recharts";
import { fmtDate } from "@/lib/utils";

const BACKEND = "/api/backend";

/* ─── Backend shapes ──────────────────────────────────────────────────────── */

interface EventDetails {
  source?: string;
  matched_text?: string;
  context?: string;
  description?: string;
  confidence?: number;
  character_count?: number;
  rule?: string;
  flagged_patterns?: string[];
}

interface SecurityEvent {
  contract_id?: number;
  filename?: string;
  event_type: string;
  severity: string;
  details?: EventDetails;
  created_at?: string;
}

interface SecuritySummary {
  total_events: number;         // backend field (was total_security_events)
  blocked_injections: number;
  quarantined_contracts: number;
  events_by_type: Record<string, number>;
  events_by_severity: Record<string, number>;
  recent_events: SecurityEvent[];
}

interface QuarantinedContract {
  id: number;
  filename: string;
  status: string;
  uploaded_at?: string;
  n_clauses: number;
}

/* ─── Constants ──────────────────────────────────────────────────────────── */

const SEVERITY_COLORS: Record<string, string> = {
  critical: "#DC2626",
  high:     "#F97316",
  medium:   "#FACC15",
  low:      "#22C55E",
};

const SEVERITY_EMOJI: Record<string, string> = {
  critical: "🔴",
  high:     "🟠",
  medium:   "🟡",
  low:      "🟢",
};

const EVENT_TYPE_LABELS: Record<string, string> = {
  instruction_override:    "Instruction Override",
  decision_manipulation:   "Decision Manipulation",
  role_override:           "Role Override",
  policy_bypass:           "Policy Bypass",
  suspicious_metadata:     "Suspicious Metadata",
  prompt_injection:        "Prompt Injection",
  jailbreak_attempt:       "Jailbreak Attempt",
  adversarial_payload:     "Adversarial Payload",
};

/* ─── Quarantine reason card ─────────────────────────────────────────────── */

function QuarantineCard({
  contract,
  events,
}: {
  contract: QuarantinedContract;
  events: SecurityEvent[];
}) {
  const [open, setOpen] = useState(false);
  const related = events.filter(e => e.contract_id === contract.id);
  const topEvent = related[0];

  const reasonLabel = topEvent
    ? (EVENT_TYPE_LABELS[topEvent.event_type] ?? topEvent.event_type)
    : "Security violation detected";

  const description = topEvent?.details?.description
    ?? topEvent?.details?.matched_text
    ?? "A security pattern was matched during pre-processing. The contract was quarantined before reaching any LLM agent.";

  const detectorSource = topEvent?.details?.source === "offline_detector"
    ? "🧱 Offline Detector"
    : "🪤 Lobster Trap";

  return (
    <div className="rounded-xl border p-5"
      style={{ background: "var(--bg-card)", borderColor: "#F9731640" }}>
      <div className="flex flex-wrap items-start gap-3 mb-3">
        <span className="text-xl">🚫</span>
        <div className="flex-1 min-w-0">
          <div className="flex flex-wrap items-center gap-2 mb-1">
            <span className="font-semibold text-sm truncate" style={{ color: "var(--text-primary)" }}>
              {contract.filename}
            </span>
            <span className="text-xs px-2 py-0.5 rounded-full"
              style={{ background: "#F9731620", color: "#F97316", border: "1px solid #F9731640" }}>
              Quarantined
            </span>
            {topEvent && (
              <span className="text-xs px-2 py-0.5 rounded-full"
                style={{ background: "#DC262618", color: "#f87171", border: "1px solid #DC262640" }}>
                {SEVERITY_EMOJI[topEvent.severity?.toLowerCase() ?? ""] ?? "⚪"}{" "}
                {topEvent.severity?.toUpperCase() ?? "UNKNOWN"}
              </span>
            )}
          </div>
          {contract.uploaded_at && (
            <p className="text-xs" style={{ color: "var(--text-muted)" }}>
              Uploaded {fmtDate(contract.uploaded_at)}
            </p>
          )}
        </div>
        <Link href={`/contracts/${contract.id}`}
          className="flex items-center gap-1 text-xs px-3 py-1.5 rounded-lg"
          style={{ background: "var(--bg-surface)", color: "var(--text-muted)", border: "1px solid var(--border)" }}>
          View <ExternalLink size={11} />
        </Link>
      </div>

      {/* Primary reason */}
      <div className="rounded-lg p-3 mb-2"
        style={{ background: "#DC262610", border: "1px solid #DC262630" }}>
        <div className="flex items-center gap-2 mb-1">
          <span className="text-xs font-bold" style={{ color: "#f87171" }}>
            {reasonLabel}
          </span>
          {topEvent && (
            <span className="text-xs px-2 py-0.5 rounded"
              style={{ background: "var(--bg-card)", color: "var(--text-muted)", border: "1px solid var(--border)" }}>
              {detectorSource}
            </span>
          )}
        </div>
        <p className="text-xs leading-relaxed" style={{ color: "var(--text-secondary)" }}>
          {description}
        </p>
      </div>

      {/* Matched text snippet (if available) */}
      {topEvent?.details?.matched_text && topEvent.details.matched_text !== description && (
        <pre className="text-xs rounded p-2 overflow-x-auto mb-2"
          style={{ background: "#DC262608", color: "#f87171", border: "1px solid #DC262620", fontFamily: "monospace", maxHeight: 80 }}>
          {topEvent.details.matched_text}
        </pre>
      )}

      {/* All events for this contract (expandable) */}
      {related.length > 1 && (
        <button onClick={() => setOpen(v => !v)}
          className="text-xs mt-1"
          style={{ color: "var(--text-muted)" }}>
          {open ? "▾" : "▸"} {related.length} security events total
        </button>
      )}
      {open && related.length > 1 && (
        <div className="mt-2 flex flex-col gap-1.5">
          {related.slice(1).map((ev, i) => (
            <div key={i} className="rounded p-2 text-xs"
              style={{ background: "var(--bg-surface)", border: "1px solid var(--border)" }}>
              <span style={{ color: "var(--text-muted)" }}>
                {SEVERITY_EMOJI[ev.severity?.toLowerCase() ?? ""] ?? "⚪"}{" "}
                {EVENT_TYPE_LABELS[ev.event_type] ?? ev.event_type}
                {ev.details?.description && ` — ${ev.details.description}`}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/* ─── Page ───────────────────────────────────────────────────────────────── */

export default function SecurityDashboardPage() {
  const [data, setData] = useState<SecuritySummary | null>(null);
  const [quarantined, setQuarantined] = useState<QuarantinedContract[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    async function load() {
      try {
        const [secRes, contractRes] = await Promise.all([
          fetch(`${BACKEND}/dashboard/security-summary`),
          fetch(`${BACKEND}/contracts?status=quarantined&limit=50&offset=0`),
        ]);
        if (!secRes.ok) throw new Error(`${secRes.status}: ${await secRes.text()}`);
        setData(await secRes.json());
        if (contractRes.ok) {
          const cd = await contractRes.json();
          const items: QuarantinedContract[] = Array.isArray(cd) ? cd : (cd.items ?? []);
          // Sort newest first
          items.sort((a, b) =>
            new Date(b.uploaded_at ?? 0).getTime() - new Date(a.uploaded_at ?? 0).getTime()
          );
          setQuarantined(items);
        }
      } catch (e) {
        setError(String(e));
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  const eventsByType = data
    ? Object.entries(data.events_by_type).map(([name, value]) => ({
        name: EVENT_TYPE_LABELS[name] ?? name.replace(/_/g, " "),
        value,
      }))
    : [];

  const eventsBySeverity = data
    ? Object.entries(data.events_by_severity).map(([name, value]) => ({ name, value }))
    : [];

  return (
    <>
      <Topbar title="Security Dashboard" />
      <main className="flex-1 overflow-y-auto min-h-0 p-4 sm:p-6 flex flex-col gap-6">

        {error && (
          <div className="rounded-lg p-4 text-sm border"
            style={{ color: "#f87171", background: "#DC262620", borderColor: "#DC262640" }}>
            Backend unreachable: {error}
          </div>
        )}

        {/* Architecture banner */}
        <div className="rounded-xl border p-5"
          style={{ background: "var(--bg-card)", borderColor: "var(--border)" }}>
          <h2 className="text-base font-semibold mb-4" style={{ color: "var(--text-primary)" }}>
            Agent 4 — Security Gate Architecture
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div>
              <p className="text-xs font-medium uppercase tracking-wider mb-3" style={{ color: "var(--text-muted)" }}>
                Two-Layer Defence
              </p>
              <div className="flex flex-col gap-3">
                <div className="rounded-lg p-4 border"
                  style={{ background: "var(--bg-surface)", borderColor: "var(--border)" }}>
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-lg">🪤</span>
                    <span className="font-semibold text-sm" style={{ color: "var(--text-primary)" }}>
                      Lobster Trap (Primary)
                    </span>
                  </div>
                  <p className="text-xs" style={{ color: "var(--text-secondary)" }}>
                    Pattern-based prompt injection detector. Scans every input for known injection
                    signatures, adversarial payloads, and jailbreak attempts. Blocks and quarantines
                    on match.
                  </p>
                </div>
                <div className="rounded-lg p-4 border"
                  style={{ background: "var(--bg-surface)", borderColor: "var(--border)" }}>
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-lg">🧱</span>
                    <span className="font-semibold text-sm" style={{ color: "var(--text-primary)" }}>
                      Offline Detector (Fallback)
                    </span>
                  </div>
                  <p className="text-xs" style={{ color: "var(--text-secondary)" }}>
                    Heuristic classifier that runs when the Lobster Trap is unavailable or uncertain.
                    Uses flag-based regex analysis to detect suspicious content without network dependency.
                  </p>
                </div>
              </div>
            </div>

            <div>
              <p className="text-xs font-medium uppercase tracking-wider mb-3" style={{ color: "var(--text-muted)" }}>
                What triggers quarantine
              </p>
              <div className="flex flex-col gap-2">
                {[
                  { icon: "💉", label: "Prompt injection", desc: "Instructions attempting to override AI behaviour" },
                  { icon: "🎭", label: "Role override", desc: "Commands trying to change the AI's persona or permissions" },
                  { icon: "🔓", label: "Policy bypass", desc: "Phrases designed to circumvent safety guardrails" },
                  { icon: "🕵️", label: "Suspicious metadata", desc: "Zero-width / invisible characters hiding instructions" },
                  { icon: "⚙️", label: "Decision manipulation", desc: "Content trying to force a specific approval outcome" },
                ].map(({ icon, label, desc }) => (
                  <div key={label} className="flex items-start gap-2 text-xs">
                    <span>{icon}</span>
                    <span>
                      <strong style={{ color: "var(--text-secondary)" }}>{label}</strong>
                      <span style={{ color: "var(--text-muted)" }}> — {desc}</span>
                    </span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>

        {/* Metrics row */}
        {loading ? (
          <div className="flex items-center gap-3 text-sm" style={{ color: "var(--text-muted)" }}>
            <div className="w-4 h-4 rounded-full border-2 border-t-transparent animate-spin"
              style={{ borderColor: "var(--accent)", borderTopColor: "transparent" }} />
            Loading security data…
          </div>
        ) : data ? (
          <>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              {[
                { label: "Blocked Injections",    value: data.blocked_injections,    color: "#DC2626" },
                { label: "Quarantined Contracts",  value: data.quarantined_contracts, color: "#F97316" },
                { label: "Total Security Events",  value: data.total_events ?? 0,     color: "var(--accent)" },
              ].map(m => (
                <div key={m.label} className="rounded-xl border p-5"
                  style={{ background: "var(--bg-card)", borderColor: "var(--border)" }}>
                  <p className="text-xs font-medium uppercase tracking-wider mb-2" style={{ color: "var(--text-muted)" }}>
                    {m.label}
                  </p>
                  <p className="text-2xl font-bold" style={{ color: m.color }}>
                    {m.value ?? 0}
                  </p>
                </div>
              ))}
            </div>

            {/* Quarantined contracts with reasons — newest first */}
            <div className="rounded-xl border p-5"
              style={{ background: "var(--bg-card)", borderColor: "#F9731640" }}>
              <div className="flex items-center justify-between mb-4">
                <div>
                  <p className="text-sm font-semibold" style={{ color: "var(--text-primary)" }}>
                    🚫 Quarantine History
                  </p>
                  <p className="text-xs mt-0.5" style={{ color: "var(--text-muted)" }}>
                    {quarantined.length > 0
                      ? `${quarantined.length} contract${quarantined.length !== 1 ? "s" : ""} quarantined · newest first`
                      : "No quarantined contracts"}
                  </p>
                </div>
                {quarantined.length > 0 && (
                  <span className="text-xs px-3 py-1.5 rounded-full font-semibold"
                    style={{ background: "#F9731620", color: "#F97316", border: "1px solid #F9731640" }}>
                    {quarantined.length} blocked
                  </span>
                )}
              </div>

              {quarantined.length === 0 ? (
                <div className="flex flex-col items-center py-8 gap-2">
                  <span className="text-3xl">✅</span>
                  <p className="text-sm" style={{ color: "var(--text-muted)" }}>
                    No contracts have been quarantined. All uploads passed the security gate.
                  </p>
                </div>
              ) : (
                <div className="flex flex-col gap-3">
                  {quarantined.map(contract => (
                    <QuarantineCard
                      key={contract.id}
                      contract={contract}
                      events={data.recent_events}
                    />
                  ))}
                </div>
              )}
            </div>

            {/* Charts row */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="rounded-xl border p-5"
                style={{ background: "var(--bg-card)", borderColor: "var(--border)" }}>
                <p className="text-sm font-semibold mb-4" style={{ color: "var(--text-primary)" }}>
                  Events by Type
                </p>
                {eventsByType.length === 0 ? (
                  <p className="text-sm text-center py-8" style={{ color: "var(--text-muted)" }}>No data</p>
                ) : (
                  <ResponsiveContainer width="100%" height={220}>
                    <BarChart data={eventsByType} layout="vertical" margin={{ left: 20, right: 10 }}>
                      <XAxis type="number" tick={{ fill: "var(--text-muted)", fontSize: 11 }} />
                      <YAxis dataKey="name" type="category" tick={{ fill: "var(--text-secondary)", fontSize: 10 }} width={150} />
                      <Tooltip
                        contentStyle={{ background: "var(--bg-surface)", border: "1px solid var(--border)", borderRadius: 8 }}
                        labelStyle={{ color: "var(--text-primary)" }}
                        itemStyle={{ color: "var(--text-secondary)" }}
                      />
                      <Bar dataKey="value" fill="#DC2626" radius={[0, 4, 4, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                )}
              </div>

              <div className="rounded-xl border p-5"
                style={{ background: "var(--bg-card)", borderColor: "var(--border)" }}>
                <p className="text-sm font-semibold mb-4" style={{ color: "var(--text-primary)" }}>
                  Events by Severity
                </p>
                {eventsBySeverity.length === 0 ? (
                  <p className="text-sm text-center py-8" style={{ color: "var(--text-muted)" }}>No data</p>
                ) : (
                  <ResponsiveContainer width="100%" height={220}>
                    <BarChart data={eventsBySeverity} margin={{ bottom: 10 }}>
                      <XAxis dataKey="name" tick={{ fill: "var(--text-secondary)", fontSize: 11 }} />
                      <YAxis tick={{ fill: "var(--text-muted)", fontSize: 11 }} />
                      <Tooltip
                        contentStyle={{ background: "var(--bg-surface)", border: "1px solid var(--border)", borderRadius: 8 }}
                        labelStyle={{ color: "var(--text-primary)" }}
                        itemStyle={{ color: "var(--text-secondary)" }}
                      />
                      <Bar dataKey="value" radius={[4, 4, 0, 0]}>
                        {eventsBySeverity.map(entry => (
                          <Cell key={entry.name}
                            fill={SEVERITY_COLORS[entry.name.toLowerCase()] ?? "var(--accent)"} />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                )}
              </div>
            </div>

            {/* Recent events feed */}
            <div className="rounded-xl border p-5"
              style={{ background: "var(--bg-card)", borderColor: "var(--border)" }}>
              <p className="text-sm font-semibold mb-4" style={{ color: "var(--text-primary)" }}>
                Recent Security Events
              </p>
              {!data.recent_events || data.recent_events.length === 0 ? (
                <div className="flex flex-col items-center py-12 gap-3">
                  <ShieldAlert size={40} style={{ color: "var(--text-muted)" }} className="opacity-40" />
                  <p className="text-sm" style={{ color: "var(--text-muted)" }}>
                    No security events recorded yet. The system is monitoring all agent inputs.
                  </p>
                </div>
              ) : (
                <div className="flex flex-col gap-3">
                  {data.recent_events.map((ev, idx) => {
                    const sev = ev.severity?.toLowerCase() ?? "low";
                    const isLobster = (ev.details?.source ?? "").toLowerCase().includes("lobster");
                    const description = ev.details?.description ?? ev.details?.matched_text;
                    const matchedText = ev.details?.matched_text;
                    const confidence = ev.details?.confidence;

                    return (
                      <div key={idx} className="rounded-lg border p-4"
                        style={{ background: "var(--bg-surface)", borderColor: "var(--border)" }}>
                        <div className="flex flex-wrap items-center gap-2 mb-2">
                          <span>{SEVERITY_EMOJI[sev] ?? "⚪"}</span>
                          <span className="font-medium text-sm" style={{ color: "var(--text-primary)" }}>
                            {EVENT_TYPE_LABELS[ev.event_type] ?? ev.event_type}
                          </span>
                          {ev.filename && (
                            <span className="text-xs" style={{ color: "var(--text-secondary)" }}>
                              — {ev.filename}
                            </span>
                          )}
                          {ev.contract_id != null && (
                            <Link href={`/contracts/${ev.contract_id}`}
                              className="text-xs px-2 py-0.5 rounded-full hover:opacity-80"
                              style={{ background: "var(--bg-card)", color: "var(--text-muted)", border: "1px solid var(--border)" }}>
                              Contract #{ev.contract_id} ↗
                            </Link>
                          )}
                          <span className="text-xs px-2 py-0.5 rounded-full"
                            style={{
                              background: isLobster ? "#DC262620" : "#6C72FF20",
                              color: isLobster ? "#DC2626" : "var(--accent)",
                              border: `1px solid ${isLobster ? "#DC262640" : "#6C72FF40"}`,
                            }}>
                            {isLobster ? "🪤 Lobster Trap" : "🧱 Offline Detector"}
                          </span>
                          {confidence != null && (
                            <span className="text-xs ml-auto" style={{ color: "var(--text-muted)" }}>
                              {Math.round(confidence * 100)}% confidence
                            </span>
                          )}
                          {ev.created_at && (
                            <span className="text-xs" style={{ color: "var(--text-muted)" }}>
                              {fmtDate(ev.created_at)}
                            </span>
                          )}
                        </div>

                        {/* Human-readable reason */}
                        {description && (
                          <p className="text-xs mb-2 leading-relaxed" style={{ color: "var(--text-secondary)" }}>
                            {description}
                          </p>
                        )}

                        {/* Matched text (only if different from description) */}
                        {matchedText && matchedText !== description && (
                          <pre className="text-xs rounded p-2 overflow-x-auto"
                            style={{ background: "#DC262610", color: "#f87171", border: "1px solid #DC262630", fontFamily: "monospace", maxHeight: 80 }}>
                            {matchedText}
                          </pre>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          </>
        ) : null}
      </main>
    </>
  );
}
