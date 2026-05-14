"use client";

import { useEffect, useState, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import Topbar from "@/components/layout/Topbar";
import StatusPill from "@/components/ui/StatusPill";
import { fmtDate, scoreColor } from "@/lib/utils";
import type { ContractDetail, Decision, ScoringDetails } from "@/lib/api";

const BACKEND = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";

type Tab = "score" | "extraction" | "risk" | "compliance" | "audit";

const TABS: { id: Tab; label: string }[] = [
  { id: "score", label: "Score Breakdown" },
  { id: "extraction", label: "Extraction" },
  { id: "risk", label: "Risk" },
  { id: "compliance", label: "Compliance" },
  { id: "audit", label: "Audit Report" },
];

const SEVERITY_COLORS: Record<string, string> = {
  critical: "#DC2626",
  high: "#F97316",
  medium: "#FACC15",
  low: "#22C55E",
};

const SEVERITY_EMOJI: Record<string, string> = {
  critical: "🔴",
  high: "🟠",
  medium: "🟡",
  low: "🟢",
};

const DECISION_COLORS: Record<string, string> = {
  AUTO_APPROVE: "#22C55E",
  MANAGER_REVIEW: "#FBBF24",
  LEGAL_REVIEW: "#38BDF8",
  REJECT: "#DC2626",
  approved: "#22C55E",
  rejected: "#DC2626",
};

function ScoreBarRow({ label, value, max = 100, color }: { label: string; value: number; max?: number; color?: string }) {
  const pct = Math.min(100, Math.max(0, (value / max) * 100));
  const barColor = color ?? "var(--accent)";
  return (
    <div>
      <div className="flex items-center justify-between mb-1 text-xs">
        <span style={{ color: "var(--text-muted)" }}>{label}</span>
        <span className="font-bold" style={{ color: barColor }}>{Math.round(value)}</span>
      </div>
      <div className="rounded-full h-2 overflow-hidden" style={{ background: "var(--bg-surface)" }}>
        <div
          className="h-2 rounded-full"
          style={{ width: `${pct}%`, background: barColor, transition: "width 0.3s ease" }}
        />
      </div>
    </div>
  );
}

/* These mirror the backend Pydantic schemas exactly */

interface Party {
  name: string;
  role: string;
}

interface Obligation {
  party: string;
  description: string;
  clause_ref?: string;
}

interface RiskFinding {
  risk: string;          // short label, e.g. "Unlimited liability"
  severity: string;      // Low | Medium | High | Critical
  clause_ref: string;
  reasoning: string;
}

interface ComplianceCheckItem {
  requirement: string;
  present: boolean;
  evidence_quote?: string;
  gap_description?: string;
  severity?: string;
}

interface FrameworkResult {
  framework: string;
  passed: boolean;
  checks: ComplianceCheckItem[];
}

interface ComplianceOutput {
  frameworks: FrameworkResult[];
}

interface ExtractionOutput {
  parties?: Party[];
  effective_date?: string;
  term?: string;
  payment_terms?: string;
  governing_law?: string;
  summary?: string;
  obligations?: Obligation[];
}

function getAgentOutput<T>(contract: ContractDetail, agentKey: string): T | null {
  const agentData = contract.agent_outputs?.[agentKey];
  if (!agentData) return null;
  return agentData.output as T;
}

function getScoringDetails(contract: ContractDetail): ScoringDetails | null {
  // Try from most recent decision
  for (const d of [...(contract.decisions ?? [])].reverse()) {
    if (d.scoring_details) return d.scoring_details;
  }
  // Try from agent_outputs
  const scoringOut = getAgentOutput<{ scoring_details?: ScoringDetails } & Partial<ScoringDetails>>(contract, "scoring");
  if (scoringOut) {
    if (scoringOut.scoring_details) return scoringOut.scoring_details;
    // flat shape
    if (scoringOut.composite_score !== undefined) return scoringOut as unknown as ScoringDetails;
  }
  return null;
}

export default function ContractDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const contractId = Number(params.id);

  const [contract, setContract] = useState<ContractDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [tab, setTab] = useState<Tab>("score");
  const [expandedFindings, setExpandedFindings] = useState<Set<number>>(new Set());
  const [expandedClauses, setExpandedClauses] = useState<Set<number>>(new Set());
  const [downloadingReport, setDownloadingReport] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const res = await fetch(`${BACKEND}/contracts/${contractId}`);
      if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);
      setContract(await res.json());
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }, [contractId]);

  useEffect(() => { load(); }, [load]);

  async function downloadReport() {
    setDownloadingReport(true);
    try {
      const res = await fetch(`${BACKEND}/contracts/${contractId}/audit-report`);
      const data = await res.json();
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `audit-report-${contractId}.json`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      alert(String(e));
    } finally {
      setDownloadingReport(false);
    }
  }

  function toggleFinding(idx: number) {
    setExpandedFindings((prev) => {
      const next = new Set(prev);
      next.has(idx) ? next.delete(idx) : next.add(idx);
      return next;
    });
  }

  function toggleClause(idx: number) {
    setExpandedClauses((prev) => {
      const next = new Set(prev);
      next.has(idx) ? next.delete(idx) : next.add(idx);
      return next;
    });
  }

  if (loading) {
    return (
      <>
        <Topbar title="Loading…" />
        <main className="p-6 flex-1 overflow-y-auto min-h-0">
          <p className="text-sm" style={{ color: "var(--text-muted)" }}>Fetching contract…</p>
        </main>
      </>
    );
  }

  if (error || !contract) {
    return (
      <>
        <Topbar title="Contract" />
        <main className="p-6 flex-1 overflow-y-auto min-h-0">
          <div
            className="rounded-lg p-4 text-sm border"
            style={{ color: "#f87171", background: "#DC262618", borderColor: "#DC262640" }}
          >
            {error || "Contract not found."}
          </div>
        </main>
      </>
    );
  }

  const scoring = getScoringDetails(contract);
  const extractionOut = getAgentOutput<ExtractionOutput>(contract, "extraction");
  const riskFindings: RiskFinding[] =
    (getAgentOutput<{ findings?: RiskFinding[] }>(contract, "risk") as { findings?: RiskFinding[] } | null)?.findings ?? [];
  // Compliance output shape: { frameworks: FrameworkResult[] }
  const complianceFrameworks: FrameworkResult[] =
    (getAgentOutput<ComplianceOutput>(contract, "compliance") as ComplianceOutput | null)?.frameworks ?? [];

  const findingsBySeverity: Record<string, RiskFinding[]> = {};
  riskFindings.forEach((f) => {
    const sev = (f.severity ?? "Low").toLowerCase();
    if (!findingsBySeverity[sev]) findingsBySeverity[sev] = [];
    findingsBySeverity[sev].push(f);
  });

  const decisionColor = scoring?.decision ? DECISION_COLORS[scoring.decision] ?? "var(--accent)" : "var(--accent)";
  const compositeScore = scoring?.composite_score ?? 0;

  return (
    <>
      <Topbar title={contract.filename} />
      <main className="p-6 flex flex-col gap-5 max-w-5xl flex-1 overflow-y-auto min-h-0">
        {/* Back button */}
        <button
          onClick={() => router.push("/contracts")}
          className="self-start text-sm flex items-center gap-1"
          style={{ color: "var(--text-muted)" }}
        >
          ← Back to Contracts
        </button>

        {/* Header card */}
        <div
          className="rounded-xl border p-5"
          style={{ background: "var(--bg-card)", borderColor: "var(--border)" }}
        >
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="flex-1 min-w-0">
              <h1 className="text-lg font-bold truncate mb-2" style={{ color: "var(--text-primary)" }}>
                {contract.filename}
              </h1>
              <div className="flex flex-wrap items-center gap-3">
                <StatusPill status={contract.status} />
                {scoring && (
                  <>
                    <span className="text-sm font-bold" style={{ color: decisionColor }}>
                      {scoring.decision}
                    </span>
                    <span className="text-sm" style={{ color: "var(--text-muted)" }}>
                      Composite: <strong className={scoreColor(compositeScore)}>{compositeScore}</strong>/100
                    </span>
                    <span className="text-sm" style={{ color: "var(--text-muted)" }}>
                      Risk: <strong style={{ color: SEVERITY_COLORS.high }}>{scoring.risk_score}</strong>/100
                    </span>
                    {scoring.critical_findings > 0 && (
                      <span className="text-xs px-2 py-0.5 rounded-full" style={{ background: "#DC262618", color: "#f87171", border: "1px solid #DC262640" }}>
                        {scoring.critical_findings} critical
                      </span>
                    )}
                    {scoring.high_findings > 0 && (
                      <span className="text-xs px-2 py-0.5 rounded-full" style={{ background: "#F9731618", color: "#F97316", border: "1px solid #F9731640" }}>
                        {scoring.high_findings} high
                      </span>
                    )}
                  </>
                )}
              </div>
            </div>
          </div>
        </div>

        {/* Tab switcher */}
        <div className="flex flex-wrap gap-2">
          {TABS.map((t) => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className="px-4 py-2 rounded-lg text-sm font-medium transition-colors"
              style={{
                background: tab === t.id ? "var(--accent)" : "var(--bg-card)",
                color: tab === t.id ? "#fff" : "var(--text-secondary)",
                border: `1px solid ${tab === t.id ? "var(--accent)" : "var(--border)"}`,
              }}
            >
              {t.label}
            </button>
          ))}
        </div>

        {/* ── Score Breakdown ── */}
        {tab === "score" && (
          <div className="flex flex-col gap-4">
            {!scoring ? (
              <div className="rounded-xl border p-8 text-center" style={{ background: "var(--bg-card)", borderColor: "var(--border)" }}>
                <p className="text-sm" style={{ color: "var(--text-muted)" }}>Score data not available yet — run the scoring pipeline first.</p>
              </div>
            ) : (
              <>
                {/* Composite score bar */}
                <div className="rounded-xl border p-5" style={{ background: "var(--bg-card)", borderColor: "var(--border)" }}>
                  <p className="text-sm font-semibold mb-4" style={{ color: "var(--text-primary)" }}>Composite Score</p>
                  <div className="rounded-full h-5 overflow-hidden mb-2" style={{ background: "var(--bg-surface)" }}>
                    <div
                      className="h-5 rounded-full flex items-center pl-2 text-xs font-bold text-white"
                      style={{
                        width: `${compositeScore}%`,
                        background: `linear-gradient(90deg, var(--accent) 0%, ${decisionColor} 100%)`,
                        transition: "width 0.4s ease",
                        minWidth: compositeScore > 0 ? 40 : 0,
                      }}
                    >
                      {compositeScore}
                    </div>
                  </div>

                  <div className="flex flex-col gap-3 mt-4">
                    <ScoreBarRow
                      label="Risk Contribution (100 − risk_score)"
                      value={100 - (scoring.risk_score ?? 0)}
                      color={SEVERITY_COLORS.high}
                    />
                    <ScoreBarRow
                      label="Compliance Average"
                      value={scoring.compliance_average ?? 0}
                      color="#38BDF8"
                    />
                    <ScoreBarRow
                      label="Quality Score"
                      value={scoring.quality_score ?? 0}
                      color="#9A91FB"
                    />
                  </div>

                  <div className="grid grid-cols-2 gap-3 mt-4">
                    <div className="rounded-lg p-3 text-center" style={{ background: "#DC262618", border: "1px solid #DC262640" }}>
                      <p className="text-xs" style={{ color: "var(--text-muted)" }}>Critical Findings</p>
                      <p className="text-xl font-bold" style={{ color: "#DC2626" }}>{scoring.critical_findings}</p>
                    </div>
                    <div className="rounded-lg p-3 text-center" style={{ background: "#F9731618", border: "1px solid #F9731640" }}>
                      <p className="text-xs" style={{ color: "var(--text-muted)" }}>High Findings</p>
                      <p className="text-xl font-bold" style={{ color: "#F97316" }}>{scoring.high_findings}</p>
                    </div>
                  </div>
                </div>

                {/* Triggered rules */}
                {scoring.triggered_rules && scoring.triggered_rules.length > 0 && (
                  <div className="rounded-xl border p-5" style={{ background: "var(--bg-card)", borderColor: "var(--border)" }}>
                    <p className="text-sm font-semibold mb-3" style={{ color: "var(--text-primary)" }}>Triggered Rules</p>
                    <div className="flex flex-wrap gap-2">
                      {scoring.triggered_rules.map((r, i) => (
                        <code key={i} className="text-xs px-2 py-1 rounded" style={{ background: "#DC262618", color: "#f87171", border: "1px solid #DC262640" }}>
                          {r}
                        </code>
                      ))}
                    </div>
                  </div>
                )}

                {/* Decision rationale */}
                {scoring.rationale && scoring.rationale.length > 0 && (
                  <div className="rounded-xl border p-5" style={{ background: "var(--bg-card)", borderColor: "var(--border)" }}>
                    <p className="text-sm font-semibold mb-3" style={{ color: "var(--text-primary)" }}>Decision Rationale</p>
                    <ul className="flex flex-col gap-1">
                      {scoring.rationale.map((r, i) => (
                        <li key={i} className="text-sm flex items-start gap-2" style={{ color: "var(--text-secondary)" }}>
                          <span style={{ color: "var(--accent)" }}>•</span> {r}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {/* Required actions */}
                {scoring.required_actions && scoring.required_actions.length > 0 && (
                  <div className="rounded-xl border p-5" style={{ background: "var(--bg-card)", borderColor: "var(--border)" }}>
                    <p className="text-sm font-semibold mb-3" style={{ color: "var(--text-primary)" }}>Required Actions</p>
                    <ul className="flex flex-col gap-1">
                      {scoring.required_actions.map((a, i) => (
                        <li key={i} className="text-sm flex items-start gap-2" style={{ color: "var(--text-secondary)" }}>
                          <span style={{ color: "#F97316" }}>→</span> {a}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {/* AI Recommendation */}
                {contract.decisions && contract.decisions.length > 0 && (
                  <div
                    className="rounded-xl border p-5"
                    style={{
                      background: "var(--bg-card)",
                      borderColor: decisionColor,
                      borderLeftWidth: 4,
                    }}
                  >
                    <p className="text-sm font-semibold mb-2" style={{ color: decisionColor }}>
                      AI Recommendation
                    </p>
                    <p className="text-sm" style={{ color: "var(--text-secondary)" }}>
                      {contract.decisions[contract.decisions.length - 1].reasoning}
                    </p>
                  </div>
                )}
              </>
            )}
          </div>
        )}

        {/* ── Extraction ── */}
        {tab === "extraction" && (
          <div className="flex flex-col gap-4">
            {!extractionOut ? (
              <div className="rounded-xl border p-8 text-center" style={{ background: "var(--bg-card)", borderColor: "var(--border)" }}>
                <p className="text-sm" style={{ color: "var(--text-muted)" }}>Extraction data not available yet.</p>
              </div>
            ) : (
              <>
                {/* Parties */}
                {extractionOut.parties && extractionOut.parties.length > 0 && (
                  <div className="rounded-xl border p-5" style={{ background: "var(--bg-card)", borderColor: "var(--border)" }}>
                    <p className="text-sm font-semibold mb-3" style={{ color: "var(--text-primary)" }}>Parties</p>
                    <div className="flex flex-wrap gap-2">
                      {extractionOut.parties.map((p, i) => (
                        <div key={i} className="flex items-center gap-2 px-3 py-1.5 rounded-lg"
                          style={{ background: "var(--bg-surface)", border: "1px solid var(--border)" }}>
                          <span className="text-sm font-medium" style={{ color: "var(--text-primary)" }}>{p.name}</span>
                          <span className="text-xs px-1.5 py-0.5 rounded" style={{ background: "var(--accent)22", color: "var(--accent)" }}>{p.role}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Key fields */}
                <div className="rounded-xl border p-5" style={{ background: "var(--bg-card)", borderColor: "var(--border)" }}>
                  <p className="text-sm font-semibold mb-3" style={{ color: "var(--text-primary)" }}>Key Details</p>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    {[
                      { label: "Effective Date", value: extractionOut.effective_date },
                      { label: "Term", value: extractionOut.term },
                      { label: "Payment Terms", value: extractionOut.payment_terms },
                      { label: "Governing Law", value: extractionOut.governing_law },
                    ].map(({ label, value }) =>
                      value ? (
                        <div key={label}>
                          <p className="text-xs mb-0.5" style={{ color: "var(--text-muted)" }}>{label}</p>
                          <p className="text-sm font-medium" style={{ color: "var(--text-secondary)" }}>{value}</p>
                        </div>
                      ) : null
                    )}
                  </div>
                </div>

                {/* Summary */}
                {extractionOut.summary && (
                  <div className="rounded-xl border p-5" style={{ background: "var(--bg-card)", borderColor: "var(--border)" }}>
                    <p className="text-sm font-semibold mb-2" style={{ color: "var(--text-primary)" }}>Summary</p>
                    <p className="text-sm" style={{ color: "var(--text-secondary)" }}>{extractionOut.summary}</p>
                  </div>
                )}

                {/* Obligations */}
                {extractionOut.obligations && extractionOut.obligations.length > 0 && (
                  <div className="rounded-xl border p-5" style={{ background: "var(--bg-card)", borderColor: "var(--border)" }}>
                    <p className="text-sm font-semibold mb-3" style={{ color: "var(--text-primary)" }}>
                      Obligations ({extractionOut.obligations.length})
                    </p>
                    <ul className="flex flex-col gap-2">
                      {extractionOut.obligations.map((o, i) => (
                        <li key={i} className="rounded-lg px-3 py-2.5 flex items-start gap-2"
                          style={{ background: "var(--bg-surface)", border: "1px solid var(--border)" }}>
                          <span className="text-xs font-bold mt-0.5 flex-shrink-0" style={{ color: "var(--accent)" }}>
                            {o.clause_ref ? `§${o.clause_ref}` : "•"}
                          </span>
                          <div>
                            <span className="text-xs font-semibold" style={{ color: "var(--text-muted)" }}>{o.party}: </span>
                            <span className="text-sm" style={{ color: "var(--text-secondary)" }}>{o.description}</span>
                          </div>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {/* Clauses */}
                {contract.clauses && contract.clauses.length > 0 && (
                  <div className="rounded-xl border p-5" style={{ background: "var(--bg-card)", borderColor: "var(--border)" }}>
                    <p className="text-sm font-semibold mb-3" style={{ color: "var(--text-primary)" }}>
                      Clauses ({contract.clauses.length})
                    </p>
                    <div className="flex flex-col gap-2">
                      {contract.clauses.map((cl, idx) => (
                        <div key={idx} className="rounded-lg border" style={{ borderColor: "var(--border)" }}>
                          <button
                            className="w-full flex items-center justify-between px-4 py-3 text-left"
                            onClick={() => toggleClause(idx)}
                          >
                            <div className="flex items-center gap-2">
                              <span className="text-xs font-bold" style={{ color: "var(--accent)" }}>§{cl.number}</span>
                              <span className="text-sm font-medium" style={{ color: "var(--text-primary)" }}>{cl.title}</span>
                            </div>
                            <span style={{ color: "var(--text-muted)" }}>{expandedClauses.has(idx) ? "▾" : "▸"}</span>
                          </button>
                          {expandedClauses.has(idx) && (
                            <div className="px-4 pb-4">
                              <p className="text-sm" style={{ color: "var(--text-secondary)" }}>{cl.text}</p>
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </>
            )}
          </div>
        )}

        {/* ── Risk ── */}
        {tab === "risk" && (
          <div className="flex flex-col gap-4">
            {scoring && (
              <div className="rounded-xl border p-5" style={{ background: "var(--bg-card)", borderColor: "var(--border)" }}>
                <p className="text-sm font-semibold mb-3" style={{ color: "var(--text-primary)" }}>Overall Risk Score</p>
                <div className="flex items-center gap-4 mb-3">
                  <span className="text-4xl font-bold" style={{ color: SEVERITY_COLORS.high }}>{scoring.risk_score}</span>
                  <div className="flex-1">
                    <div className="rounded-full h-3 overflow-hidden" style={{ background: "var(--bg-surface)" }}>
                      <div
                        className="h-3 rounded-full"
                        style={{ width: `${scoring.risk_score}%`, background: SEVERITY_COLORS.high }}
                      />
                    </div>
                    <p className="text-xs mt-1" style={{ color: "var(--text-muted)" }}>Higher = more risk</p>
                  </div>
                </div>
              </div>
            )}

            {riskFindings.length === 0 ? (
              <div className="rounded-xl border p-8 text-center" style={{ background: "var(--bg-card)", borderColor: "var(--border)" }}>
                <p className="text-sm" style={{ color: "var(--text-muted)" }}>No risk findings available.</p>
              </div>
            ) : (
              ["critical", "high", "medium", "low"].map((sev) => {
                const findings = findingsBySeverity[sev];
                if (!findings || findings.length === 0) return null;
                return (
                  <div key={sev} className="rounded-xl border p-5" style={{ background: "var(--bg-card)", borderColor: "var(--border)" }}>
                    <p className="text-sm font-semibold mb-3 capitalize" style={{ color: SEVERITY_COLORS[sev] }}>
                      {SEVERITY_EMOJI[sev]} {sev} ({findings.length})
                    </p>
                    <div className="flex flex-col gap-2">
                      {findings.map((f, i) => {
                        const key = `${sev}-${i}`;
                        const numKey = parseInt(key.replace(/\D/g, ""), 10);
                        return (
                          <div key={i} className="rounded-lg border" style={{ borderColor: `${SEVERITY_COLORS[sev]}40` }}>
                            <button
                              className="w-full flex items-center justify-between px-4 py-3 text-left"
                              onClick={() => toggleFinding(numKey)}
                            >
                              <span className="text-sm font-medium" style={{ color: "var(--text-primary)" }}>
                                {f.risk}
                              </span>
                              <span style={{ color: "var(--text-muted)" }}>{expandedFindings.has(numKey) ? "▾" : "▸"}</span>
                            </button>
                            {expandedFindings.has(numKey) && (
                              <div className="px-4 pb-4 flex flex-col gap-2">
                                {f.reasoning && (
                                  <p className="text-sm" style={{ color: "var(--text-secondary)" }}>{f.reasoning}</p>
                                )}
                                {f.clause_ref && (
                                  <p className="text-xs" style={{ color: "var(--accent)" }}>
                                    Clause reference: {f.clause_ref}
                                  </p>
                                )}
                              </div>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  </div>
                );
              })
            )}
          </div>
        )}

        {/* ── Compliance ── */}
        {tab === "compliance" && (
          <div className="flex flex-col gap-4">
            {complianceFrameworks.length === 0 ? (
              <div className="rounded-xl border p-8 text-center" style={{ background: "var(--bg-card)", borderColor: "var(--border)" }}>
                <p className="text-sm" style={{ color: "var(--text-muted)" }}>No compliance data available.</p>
              </div>
            ) : (
              <>
                {/* Framework summary cards */}
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                  {complianceFrameworks.map((fw, i) => (
                    <div
                      key={i}
                      className="rounded-xl border p-4 text-center"
                      style={{
                        background: "var(--bg-card)",
                        borderColor: fw.passed ? "#22C55E40" : "#DC262640",
                      }}
                    >
                      <p className="text-sm font-bold mb-1" style={{ color: "var(--text-primary)" }}>
                        {fw.framework}
                      </p>
                      <span
                        className="text-xs px-3 py-1 rounded-full font-medium"
                        style={{
                          background: fw.passed ? "#22C55E20" : "#DC262618",
                          color: fw.passed ? "#22C55E" : "#f87171",
                        }}
                      >
                        {fw.passed ? "✓ Pass" : "✗ Fail"}
                      </span>
                    </div>
                  ))}
                </div>

                {/* Per-framework check details */}
                {complianceFrameworks.map((fw, i) => (
                  <div
                    key={i}
                    className="rounded-xl border p-5"
                    style={{ background: "var(--bg-card)", borderColor: "var(--border)" }}
                  >
                    <div className="flex items-center gap-3 mb-4">
                      <span className="text-sm font-semibold" style={{ color: "var(--text-primary)" }}>
                        {fw.framework}
                      </span>
                      <span
                        className="text-xs px-2 py-0.5 rounded-full"
                        style={{
                          background: fw.passed ? "#22C55E20" : "#DC262618",
                          color: fw.passed ? "#22C55E" : "#f87171",
                        }}
                      >
                        {fw.passed ? "Pass" : "Fail"}
                      </span>
                    </div>
                    {fw.checks && fw.checks.length > 0 && (
                      <div className="flex flex-col gap-2">
                        {fw.checks.map((check, j) => (
                          <div
                            key={j}
                            className="rounded-lg px-3 py-2.5 border"
                            style={{
                              borderColor: check.present ? "#22C55E30" : "#F9731630",
                              background: check.present ? "#22C55E08" : "#F9731608",
                            }}
                          >
                            <div className="flex items-start gap-2">
                              <span className="text-sm flex-shrink-0 mt-0.5">
                                {check.present ? "✅" : "⚠️"}
                              </span>
                              <div className="min-w-0">
                                <p className="text-xs font-medium" style={{ color: "var(--text-primary)" }}>
                                  {check.requirement}
                                </p>
                                {check.present && check.evidence_quote && (
                                  <p className="text-xs mt-1 italic" style={{ color: "var(--text-muted)" }}>
                                    &ldquo;{check.evidence_quote}&rdquo;
                                  </p>
                                )}
                                {!check.present && check.gap_description && (
                                  <p className="text-xs mt-1" style={{ color: "#F97316" }}>
                                    Gap: {check.gap_description}
                                  </p>
                                )}
                                {check.severity && (
                                  <span
                                    className="inline-block text-xs px-1.5 py-0.5 rounded mt-1 font-medium"
                                    style={{
                                      background: `${SEVERITY_COLORS[check.severity.toLowerCase()] ?? "#7E89AC"}22`,
                                      color: SEVERITY_COLORS[check.severity.toLowerCase()] ?? "#7E89AC",
                                    }}
                                  >
                                    {check.severity}
                                  </span>
                                )}
                              </div>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
              </>
            )}
          </div>
        )}

        {/* ── Audit Report ── */}
        {tab === "audit" && (
          <div className="flex flex-col gap-4">
            <div className="rounded-xl border p-5" style={{ background: "var(--bg-card)", borderColor: "var(--border)" }}>
              <p className="text-sm font-semibold mb-3" style={{ color: "var(--text-primary)" }}>Download Audit Report</p>
              <p className="text-sm mb-4" style={{ color: "var(--text-secondary)" }}>
                The full audit report includes all agent outputs, decisions, security events, and compliance details in JSON format.
              </p>
              <button
                onClick={downloadReport}
                disabled={downloadingReport}
                className="px-5 py-2.5 rounded-lg text-sm font-medium transition-opacity disabled:opacity-60"
                style={{ background: "var(--accent)", color: "#fff" }}
              >
                {downloadingReport ? "Preparing…" : "⬇ Download audit-report.json"}
              </button>
            </div>

            {/* Decision history */}
            {contract.decisions && contract.decisions.length > 0 && (
              <div className="rounded-xl border p-5" style={{ background: "var(--bg-card)", borderColor: "var(--border)" }}>
                <p className="text-sm font-semibold mb-3" style={{ color: "var(--text-primary)" }}>
                  Decision History ({contract.decisions.length})
                </p>
                <div className="flex flex-col gap-3">
                  {(contract.decisions as Decision[]).map((d, i) => {
                    const dColor = DECISION_COLORS[d.recommendation] ?? "var(--accent)";
                    return (
                      <div
                        key={d.id ?? i}
                        className="rounded-lg border p-4"
                        style={{ background: "var(--bg-surface)", borderColor: "var(--border)" }}
                      >
                        <div className="flex flex-wrap items-center gap-2 mb-2">
                          <span
                            className="text-xs font-bold px-2 py-0.5 rounded-full"
                            style={{ background: `${dColor}20`, color: dColor, border: `1px solid ${dColor}40` }}
                          >
                            {d.recommendation}
                          </span>
                          <span className="text-xs" style={{ color: "var(--text-muted)" }}>
                            by {d.reviewer_role}
                          </span>
                          <span className="text-xs ml-auto" style={{ color: "var(--text-muted)" }}>
                            {fmtDate(d.decided_at)}
                          </span>
                        </div>
                        {d.reasoning && (
                          <p className="text-sm" style={{ color: "var(--text-secondary)" }}>{d.reasoning}</p>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </div>
        )}
      </main>
    </>
  );
}
