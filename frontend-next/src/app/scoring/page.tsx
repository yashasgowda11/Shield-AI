"use client";

import { useEffect, useState, useCallback } from "react";
import Topbar from "@/components/layout/Topbar";
import { useRole } from "@/hooks/useRole";
import { fmtDate } from "@/lib/utils";

const BACKEND = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";

/* ─── Exact types matching the backend ──────────────────────────────────────── */

interface ThresholdBand {
  composite_min: number;
  critical_max:  number;
  high_max:      number;
}

interface PolicyConfig {
  weights: { risk: number; compliance: number; quality: number };
  thresholds: {
    auto_approve:   ThresholdBand;
    manager_review: ThresholdBand;
    legal_review:   ThresholdBand;
  };
  framework_rejection_rules: {
    GDPR?:  string[];
    HIPAA?: string[];
    SOC2?:  string[];
  };
}

interface PolicyResponse {
  id:         number | null;
  name:       string;
  is_active:  boolean;
  config:     PolicyConfig;
  updated_by: string | null;
  updated_at: string | null;
}

interface FeedbackSummary {
  total:          number;
  breakdown:      Record<string, number>;
  by_ai_decision: Record<string, Record<string, number>>;
  avg_composite:  number | null;
  suggestion?:    string;
}

interface HistoryEntry {
  id:         number;
  name:       string;
  config:     PolicyConfig;
  updated_by: string | null;
  updated_at: string;
}

const ADMIN_ROLES = ["Legal Reviewer", "Admin", "System Administrator"];

/* ─── Simulator ──────────────────────────────────────────────────────────────── */

function simulate(
  risk: number, compliance: number, quality: number,
  criticalN: number, highN: number, config: PolicyConfig
): { score: number; decision: string; color: string } {
  const w = config.weights;
  const score = ((100 - risk) * w.risk + compliance * w.compliance + quality * w.quality);
  const t = config.thresholds;
  const s = Math.round(score);

  if (s >= t.auto_approve.composite_min   && criticalN <= t.auto_approve.critical_max   && highN <= t.auto_approve.high_max)
    return { score: s, decision: "AUTO APPROVE",   color: "#22C55E" };
  if (s >= t.manager_review.composite_min && criticalN <= t.manager_review.critical_max && highN <= t.manager_review.high_max)
    return { score: s, decision: "MANAGER REVIEW", color: "#FBBF24" };
  if (s >= t.legal_review.composite_min   && criticalN <= t.legal_review.critical_max   && highN <= t.legal_review.high_max)
    return { score: s, decision: "LEGAL REVIEW",   color: "#38BDF8" };
  return { score: s, decision: "REJECT", color: "#DC2626" };
}

/* ─── Default blank config (used while loading) ──────────────────────────────── */

const BLANK: PolicyConfig = {
  weights:    { risk: 0.50, compliance: 0.35, quality: 0.15 },
  thresholds: {
    auto_approve:   { composite_min: 82, critical_max: 0, high_max: 1 },
    manager_review: { composite_min: 63, critical_max: 0, high_max: 2 },
    legal_review:   { composite_min: 38, critical_max: 1, high_max: 5 },
  },
  framework_rejection_rules: { GDPR: [], HIPAA: [], SOC2: [] },
};

/* ─── Small reusable helpers ─────────────────────────────────────────────────── */

function Card({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return (
    <div className={`rounded-xl border p-5 ${className}`}
      style={{ background: "var(--bg-card)", borderColor: "var(--border)" }}>
      {children}
    </div>
  );
}

function SectionTitle({ children }: { children: React.ReactNode }) {
  return <p className="text-sm font-semibold mb-4" style={{ color: "var(--text-primary)" }}>{children}</p>;
}

/* ─── Page ───────────────────────────────────────────────────────────────────── */

export default function ScoringPolicyPage() {
  const { role } = useRole();
  const canEdit = ADMIN_ROLES.includes(role);

  const [meta, setMeta]         = useState<Omit<PolicyResponse, "config"> | null>(null);
  const [config, setConfig]     = useState<PolicyConfig>(BLANK);
  const [loading, setLoading]   = useState(true);
  const [saving, setSaving]     = useState(false);
  const [saveMsg, setSaveMsg]   = useState<{ text: string; ok: boolean } | null>(null);
  const [rescoring, setRescoring] = useState(false);
  const [rescoreResult, setRescoreResult] = useState<string>("");
  const [feedback, setFeedback] = useState<FeedbackSummary | null>(null);
  const [history, setHistory]   = useState<HistoryEntry[]>([]);
  const [formulaOpen, setFormulaOpen] = useState(false);
  const [error, setError]       = useState("");

  /* simulator state */
  const [simRisk, setSimRisk]           = useState(50);
  const [simComp, setSimComp]           = useState(80);
  const [simQual, setSimQual]           = useState(70);
  const [simCrit, setSimCrit]           = useState(0);
  const [simHigh, setSimHigh]           = useState(1);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [pRes, fRes, hRes] = await Promise.all([
        fetch(`${BACKEND}/scoring-policy/`),
        fetch(`${BACKEND}/scoring-policy/feedback/summary`),
        fetch(`${BACKEND}/scoring-policy/history`),
      ]);

      if (pRes.ok) {
        const data: PolicyResponse = await pRes.json();
        /* Merge in any missing keys so we never render undefined */
        const cfg: PolicyConfig = {
          weights: { ...BLANK.weights,    ...(data.config?.weights    ?? {}) },
          thresholds: {
            auto_approve:   { ...BLANK.thresholds.auto_approve,   ...(data.config?.thresholds?.auto_approve   ?? {}) },
            manager_review: { ...BLANK.thresholds.manager_review, ...(data.config?.thresholds?.manager_review ?? {}) },
            legal_review:   { ...BLANK.thresholds.legal_review,   ...(data.config?.thresholds?.legal_review   ?? {}) },
          },
          framework_rejection_rules: {
            GDPR:  data.config?.framework_rejection_rules?.GDPR  ?? [],
            HIPAA: data.config?.framework_rejection_rules?.HIPAA ?? [],
            SOC2:  data.config?.framework_rejection_rules?.SOC2  ?? [],
          },
        };
        setConfig(cfg);
        setMeta({ id: data.id, name: data.name, is_active: data.is_active, updated_by: data.updated_by, updated_at: data.updated_at });
      }
      if (fRes.ok) setFeedback(await fRes.json());
      if (hRes.ok) {
        const h = await hRes.json();
        setHistory(Array.isArray(h) ? h : h.items ?? []);
      }
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  /* ── Updaters ── */
  function setWeight(key: keyof PolicyConfig["weights"], val: number) {
    setConfig(c => ({ ...c, weights: { ...c.weights, [key]: val } }));
  }
  function setThreshold(band: keyof PolicyConfig["thresholds"], key: keyof ThresholdBand, val: number) {
    setConfig(c => ({
      ...c,
      thresholds: { ...c.thresholds, [band]: { ...c.thresholds[band], [key]: val } },
    }));
  }
  function setKeywords(fw: "GDPR" | "HIPAA" | "SOC2", text: string) {
    setConfig(c => ({
      ...c,
      framework_rejection_rules: {
        ...c.framework_rejection_rules,
        [fw]: text.split("\n").map(s => s.trim()).filter(Boolean),
      },
    }));
  }

  /* ── Save ── */
  async function save() {
    setSaving(true);
    setSaveMsg(null);
    const weightSum = config.weights.risk + config.weights.compliance + config.weights.quality;
    if (Math.abs(weightSum - 1) > 0.01) {
      setSaveMsg({ text: `Weights must sum to 1.00 (currently ${weightSum.toFixed(2)})`, ok: false });
      setSaving(false);
      return;
    }
    try {
      const res = await fetch(`${BACKEND}/scoring-policy/`, {
        method: "PUT",
        headers: { "Content-Type": "application/json", "X-Role": role },
        body: JSON.stringify({ config, updated_by: `user:${role}` }),
      });
      if (!res.ok) {
        const err = await res.json().catch(async () => ({ detail: await res.text() }));
        throw new Error(typeof err.detail === "string" ? err.detail : JSON.stringify(err.detail));
      }
      setSaveMsg({ text: "Policy saved and will apply to all new scorings.", ok: true });
      load();
    } catch (e) {
      setSaveMsg({ text: String(e), ok: false });
    } finally {
      setSaving(false);
    }
  }

  /* ── Rescore all ── */
  async function rescoreAll() {
    setRescoring(true);
    setRescoreResult("");
    try {
      const res = await fetch(`${BACKEND}/scoring-policy/rescore-all`, {
        method: "POST",
        headers: { "X-Role": role },
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail ?? JSON.stringify(data));
      setRescoreResult(JSON.stringify(data, null, 2));
    } catch (e) {
      setRescoreResult(String(e));
    } finally {
      setRescoring(false);
    }
  }

  const weightSum = config.weights.risk + config.weights.compliance + config.weights.quality;
  const sumOk     = Math.abs(weightSum - 1) < 0.01;
  const simResult = simulate(simRisk, simComp, simQual, simCrit, simHigh, config);

  return (
    <>
      <Topbar title="Scoring Policy" />
      <main className="flex-1 overflow-y-auto min-h-0">
        <div className="p-4 sm:p-6 flex flex-col gap-5 max-w-5xl w-full mx-auto">

          {/* ── Role banner ── */}
          <div className="rounded-lg border px-4 py-3 text-sm"
            style={{ background: "var(--bg-card)", borderColor: "var(--border)", color: "var(--text-muted)" }}>
            Only <strong style={{ color: "var(--text-secondary)" }}>Legal Reviewer, Admin,</strong> and{" "}
            <strong style={{ color: "var(--text-secondary)" }}>System Administrator</strong> roles can save.
            {!canEdit && <span className="ml-2" style={{ color: "#F97316" }}>(Current: {role} — read-only)</span>}
            {meta?.updated_at && (
              <span className="ml-3" style={{ color: "var(--text-muted)" }}>
                · Last saved {fmtDate(meta.updated_at)} by {meta.updated_by ?? "system"}
              </span>
            )}
          </div>

          {error && (
            <div className="rounded-lg p-4 text-sm border"
              style={{ color: "#f87171", background: "#DC262618", borderColor: "#DC262640" }}>
              {error}
            </div>
          )}

          {loading ? (
            <div className="flex items-center gap-3 py-12 justify-center">
              <div className="w-5 h-5 rounded-full border-2 border-t-transparent spin"
                style={{ borderColor: "var(--accent)", borderTopColor: "transparent" }} />
              <span className="text-sm" style={{ color: "var(--text-muted)" }}>Loading policy…</span>
            </div>
          ) : (
            <>

              {/* ── Formula ── */}
              <div className="rounded-xl border" style={{ background: "var(--bg-card)", borderColor: "var(--border)" }}>
                <button className="w-full flex items-center justify-between px-5 py-4 text-left"
                  onClick={() => setFormulaOpen(v => !v)}>
                  <span className="text-sm font-semibold" style={{ color: "var(--text-primary)" }}>
                    How the composite score is calculated
                  </span>
                  <span style={{ color: "var(--text-muted)" }}>{formulaOpen ? "▾" : "▸"}</span>
                </button>
                {formulaOpen && (
                  <div className="px-5 pb-5 flex flex-col gap-3 border-t" style={{ borderColor: "var(--border)" }}>
                    <code className="text-xs rounded-lg p-3 block mt-4"
                      style={{ background: "var(--bg-surface)", color: "#a5b4fc", border: "1px solid var(--border)" }}>
                      composite = (risk_weight × (100 − risk_score) + compliance_weight × compliance_avg + quality_weight × quality_score)
                    </code>
                    <p className="text-xs" style={{ color: "var(--text-muted)" }}>
                      Penalty deductions for jurisdiction rules (e.g. CA non-compete, IL BIPA) and financial risk
                      signals (uncapped indemnification, low liability cap) are subtracted from the base composite.
                      Security events → immediate REJECT. Critical missing compliance requirements → immediate REJECT.
                    </p>
                    {[
                      { name: "Risk sub-score",       desc: "Inverted Agent 2 score (100 − risk). Lower risk = higher contribution." },
                      { name: "Compliance sub-score",  desc: "Severity-weighted pass rate across HIPAA / SOC 2 / GDPR checks." },
                      { name: "Quality sub-score",     desc: "Extraction completeness — parties, dates, obligations, governing law." },
                    ].map(s => (
                      <div key={s.name}>
                        <p className="text-xs font-semibold" style={{ color: "var(--accent)" }}>{s.name}</p>
                        <p className="text-xs" style={{ color: "var(--text-secondary)" }}>{s.desc}</p>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* ── Weights ── */}
              <Card>
                <div className="flex items-center justify-between mb-4">
                  <SectionTitle>Score Weights</SectionTitle>
                  <span className="text-xs px-3 py-1 rounded-full font-semibold"
                    style={{
                      background: sumOk ? "#22C55E20" : "#FBBF2420",
                      color: sumOk ? "#22C55E" : "#FBBF24",
                      border: `1px solid ${sumOk ? "#22C55E40" : "#FBBF2440"}`,
                    }}>
                    Sum: {weightSum.toFixed(2)} {!sumOk && "⚠ must equal 1.00"}
                  </span>
                </div>
                <div className="flex flex-col gap-5">
                  {([
                    { label: "Risk Weight",        key: "risk"        as const, color: "#EF4444" },
                    { label: "Compliance Weight",   key: "compliance"  as const, color: "#10B981" },
                    { label: "Quality Weight",      key: "quality"     as const, color: "#6C72FF" },
                  ] as const).map(({ label, key, color }) => (
                    <div key={key}>
                      <div className="flex items-center justify-between mb-2">
                        <label className="text-xs font-medium" style={{ color: "var(--text-muted)" }}>{label}</label>
                        <span className="text-sm font-bold tabular-nums" style={{ color }}>
                          {config.weights[key].toFixed(2)}
                        </span>
                      </div>
                      <input type="range" min={0} max={1} step={0.05}
                        value={config.weights[key]}
                        onChange={e => setWeight(key, Number(e.target.value))}
                        disabled={!canEdit}
                        className="w-full accent-purple-500 disabled:opacity-50"
                      />
                      {/* Visual fill bar */}
                      <div className="w-full h-1.5 rounded-full mt-1 overflow-hidden"
                        style={{ background: "var(--bg-surface)" }}>
                        <div className="h-full rounded-full transition-all"
                          style={{ width: `${config.weights[key] * 100}%`, background: color }} />
                      </div>
                    </div>
                  ))}
                </div>
              </Card>

              {/* ── Decision band thresholds ── */}
              <Card>
                <SectionTitle>Decision Band Thresholds</SectionTitle>
                <p className="text-xs mb-4" style={{ color: "var(--text-muted)" }}>
                  Bands are evaluated top-to-bottom. A contract must meet ALL three criteria for a band to apply.
                </p>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  {([
                    { label: "AUTO APPROVE",   band: "auto_approve"   as const, color: "#22C55E" },
                    { label: "MANAGER REVIEW", band: "manager_review" as const, color: "#FBBF24" },
                    { label: "LEGAL REVIEW",   band: "legal_review"   as const, color: "#38BDF8" },
                  ] as const).map(({ label, band, color }) => (
                    <div key={band} className="rounded-lg border p-4"
                      style={{ background: "var(--bg-surface)", borderColor: `${color}40` }}>
                      <p className="text-xs font-bold mb-3" style={{ color }}>{label}</p>
                      {([
                        { label: "Composite ≥", key: "composite_min" as const },
                        { label: "Critical ≤",  key: "critical_max"  as const },
                        { label: "High ≤",      key: "high_max"      as const },
                      ] as const).map(({ label: fl, key }) => (
                        <div key={key} className="mb-3">
                          <label className="text-xs mb-1 block" style={{ color: "var(--text-muted)" }}>{fl}</label>
                          <input type="number"
                            value={config.thresholds[band][key]}
                            onChange={e => setThreshold(band, key, Number(e.target.value))}
                            disabled={!canEdit}
                            min={0} max={key === "composite_min" ? 100 : 20}
                            className="w-full rounded px-3 py-1.5 text-sm outline-none disabled:opacity-50"
                            style={{ background: "var(--bg-card)", color: "var(--text-primary)", border: "1px solid var(--border)" }}
                          />
                        </div>
                      ))}
                    </div>
                  ))}
                </div>
              </Card>

              {/* ── Framework rejection rules ── */}
              <Card>
                <SectionTitle>Framework Rejection Rules</SectionTitle>
                <p className="text-xs mb-4" style={{ color: "var(--text-muted)" }}>
                  If a CRITICAL compliance check failure contains any of these keywords, the contract is immediately rejected.
                  One keyword per line — case-insensitive substring match.
                </p>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  {(["GDPR", "HIPAA", "SOC2"] as const).map(fw => (
                    <div key={fw}>
                      <label className="text-xs font-semibold mb-1 block" style={{ color: "var(--text-muted)" }}>
                        {fw} Critical Keywords
                      </label>
                      <textarea rows={6}
                        value={(config.framework_rejection_rules[fw] ?? []).join("\n")}
                        onChange={e => setKeywords(fw, e.target.value)}
                        disabled={!canEdit}
                        placeholder="one keyword per line"
                        className="w-full rounded-lg px-3 py-2 text-xs outline-none resize-none disabled:opacity-50"
                        style={{
                          background: "var(--bg-surface)", color: "var(--text-secondary)",
                          border: "1px solid var(--border)", fontFamily: "monospace",
                        }}
                      />
                    </div>
                  ))}
                </div>
              </Card>

              {/* ── Score simulator ── */}
              <Card>
                <SectionTitle>Live Score Simulator</SectionTitle>
                <p className="text-xs mb-5" style={{ color: "var(--text-muted)" }}>
                  Uses the <em>current unsaved</em> weights and thresholds above — drag sliders to preview the decision.
                </p>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
                  <div className="flex flex-col gap-4">
                    {([
                      { label: "Risk Score (0-100 — higher = riskier)",   val: simRisk, set: setSimRisk, color: "#EF4444" },
                      { label: "Compliance % (0-100)",                    val: simComp, set: setSimComp, color: "#10B981" },
                      { label: "Quality Score (0-100)",                   val: simQual, set: setSimQual, color: "#6C72FF" },
                    ] as const).map(({ label, val, set, color }) => (
                      <div key={label}>
                        <div className="flex items-center justify-between mb-1">
                          <label className="text-xs" style={{ color: "var(--text-muted)" }}>{label}</label>
                          <span className="text-sm font-bold tabular-nums" style={{ color }}>{val}</span>
                        </div>
                        <input type="range" min={0} max={100}
                          value={val} onChange={e => set(Number(e.target.value))}
                          className="w-full accent-purple-500" />
                      </div>
                    ))}
                    <div className="grid grid-cols-2 gap-3">
                      {[
                        { label: "Critical Findings", val: simCrit, set: setSimCrit },
                        { label: "High Findings",     val: simHigh, set: setSimHigh },
                      ].map(({ label, val, set }) => (
                        <div key={label}>
                          <label className="text-xs mb-1 block" style={{ color: "var(--text-muted)" }}>{label}</label>
                          <input type="number" min={0} value={val}
                            onChange={e => set(Number(e.target.value))}
                            className="w-full rounded px-3 py-1.5 text-sm outline-none"
                            style={{ background: "var(--bg-surface)", color: "var(--text-primary)", border: "1px solid var(--border)" }}
                          />
                        </div>
                      ))}
                    </div>
                  </div>

                  <div className="flex flex-col items-center justify-center gap-4 rounded-xl border p-6"
                    style={{ background: "var(--bg-surface)", borderColor: `${simResult.color}40` }}>
                    <p className="text-4xl font-extrabold tabular-nums" style={{ color: simResult.color }}>
                      {simResult.score}
                    </p>
                    <div className="px-6 py-2 rounded-full text-sm font-bold"
                      style={{ background: `${simResult.color}20`, color: simResult.color, border: `1px solid ${simResult.color}60` }}>
                      {simResult.decision}
                    </div>
                    {/* Score breakdown */}
                    <div className="w-full text-xs space-y-1 mt-2">
                      {[
                        { label: "Risk contrib",        val: ((100 - simRisk) * config.weights.risk).toFixed(1) },
                        { label: "Compliance contrib",  val: (simComp * config.weights.compliance).toFixed(1) },
                        { label: "Quality contrib",     val: (simQual * config.weights.quality).toFixed(1) },
                      ].map(r => (
                        <div key={r.label} className="flex justify-between">
                          <span style={{ color: "var(--text-muted)" }}>{r.label}</span>
                          <span style={{ color: "var(--text-secondary)" }}>{r.val}</span>
                        </div>
                      ))}
                    </div>
                    <p className="text-xs text-center" style={{ color: "var(--text-muted)" }}>
                      Simulated from current weights · not yet saved
                    </p>
                  </div>
                </div>
              </Card>

              {/* ── Save + rescore ── */}
              {canEdit && (
                <div className="flex flex-wrap items-center gap-3">
                  <button onClick={save} disabled={saving}
                    className="px-5 py-2.5 rounded-lg text-sm font-semibold transition-opacity disabled:opacity-50"
                    style={{ background: "var(--accent)", color: "#fff" }}>
                    {saving ? "Saving…" : "Save Policy"}
                  </button>
                  <button onClick={rescoreAll} disabled={rescoring}
                    className="px-5 py-2.5 rounded-lg text-sm font-semibold border transition-opacity disabled:opacity-50"
                    style={{ background: "var(--bg-card)", color: "var(--text-secondary)", borderColor: "var(--border)" }}>
                    {rescoring ? "Rescoring…" : "🔄 Rescore All Contracts"}
                  </button>
                  {saveMsg && (
                    <span className="text-sm" style={{ color: saveMsg.ok ? "#22C55E" : "#f87171" }}>
                      {saveMsg.text}
                    </span>
                  )}
                </div>
              )}

              {rescoreResult && (
                <pre className="text-xs rounded-lg p-4 overflow-x-auto"
                  style={{ background: "var(--bg-surface)", color: "var(--text-secondary)", border: "1px solid var(--border)", fontFamily: "monospace" }}>
                  {rescoreResult}
                </pre>
              )}

              {/* ── Feedback summary ── */}
              {feedback && feedback.total > 0 && (
                <Card>
                  <SectionTitle>Feedback Summary</SectionTitle>
                  <div className="flex flex-wrap gap-3 mb-3">
                    <span className="text-xs" style={{ color: "var(--text-muted)" }}>
                      Total: <strong style={{ color: "var(--text-secondary)" }}>{feedback.total}</strong>
                    </span>
                    {Object.entries(feedback.breakdown).map(([k, v]) => (
                      <span key={k} className="text-xs px-3 py-1 rounded-full"
                        style={{ background: "var(--bg-surface)", color: "var(--text-secondary)", border: "1px solid var(--border)" }}>
                        {k}: {v}
                      </span>
                    ))}
                    {feedback.avg_composite != null && (
                      <span className="text-xs px-3 py-1 rounded-full"
                        style={{ background: "var(--accent)15", color: "var(--accent)", border: "1px solid var(--accent)40" }}>
                        Avg composite: {feedback.avg_composite}
                      </span>
                    )}
                  </div>
                  {feedback.suggestion && (
                    <div className="rounded-lg p-3 text-xs"
                      style={{ background: "#6C72FF15", color: "var(--accent)", border: "1px solid #6C72FF40" }}>
                      💡 {feedback.suggestion}
                    </div>
                  )}
                </Card>
              )}

              {/* ── Change history ── */}
              {history.length > 0 && (
                <Card>
                  <SectionTitle>Change History ({history.length})</SectionTitle>
                  <div className="flex flex-col gap-3">
                    {history.map((h, i) => (
                      <div key={h.id} className="rounded-lg border p-3 text-xs"
                        style={{ background: "var(--bg-surface)", borderColor: "var(--border)" }}>
                        <div className="flex items-center justify-between mb-2">
                          <span className="font-medium" style={{ color: "var(--text-secondary)" }}>
                            {h.updated_at ? fmtDate(h.updated_at) : "—"}
                            {i === 0 && <span className="ml-2 px-2 py-0.5 rounded-full text-xs"
                              style={{ background: "#22C55E20", color: "#22C55E" }}>active</span>}
                          </span>
                          <span style={{ color: "var(--text-muted)" }}>by {h.updated_by ?? "system"} · #{h.id}</span>
                        </div>
                        <div className="flex flex-wrap gap-3">
                          {h.config?.weights && Object.entries(h.config.weights).map(([k, v]) => (
                            <span key={k} style={{ color: "var(--text-muted)" }}>
                              {k}: <strong style={{ color: "var(--text-secondary)" }}>
                                {typeof v === "number" ? v.toFixed(2) : String(v)}
                              </strong>
                            </span>
                          ))}
                          {h.config?.thresholds?.auto_approve && (
                            <span style={{ color: "var(--text-muted)" }}>
                              auto≥ <strong style={{ color: "#22C55E" }}>{h.config.thresholds.auto_approve.composite_min}</strong>
                            </span>
                          )}
                          {h.config?.thresholds?.manager_review && (
                            <span style={{ color: "var(--text-muted)" }}>
                              manager≥ <strong style={{ color: "#FBBF24" }}>{h.config.thresholds.manager_review.composite_min}</strong>
                            </span>
                          )}
                          {h.config?.thresholds?.legal_review && (
                            <span style={{ color: "var(--text-muted)" }}>
                              legal≥ <strong style={{ color: "#38BDF8" }}>{h.config.thresholds.legal_review.composite_min}</strong>
                            </span>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                </Card>
              )}

            </>
          )}
        </div>
      </main>
    </>
  );
}
