"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import Topbar from "@/components/layout/Topbar";
import {
  Upload, FileText, CheckSquare, BarChart2, Shield,
  MessageSquare, ClipboardList, Settings,
  Database, Cpu, Brain, Lock, Zap, GitMerge,
  CheckCircle, Activity,
} from "lucide-react";

const BACKEND = "/api/backend";

interface RiskSummary {
  total_contracts: number;
  processed_contracts: number;
  avg_risk_score: number;
  anomalies: unknown[];
  by_status: Record<string, number>;
}

/* ─── Animated Shield Logo Card ─────────────────────────────────────────────── */
function ShieldLogoCard() {
  return (
    <div
      className="shield-glow rounded-2xl flex flex-col items-center justify-center gap-4 text-center select-none w-full py-10 px-6"
      style={{
        background: "linear-gradient(135deg, #0D1628 0%, #101935 60%, #13204A 100%)",
        border: "1px solid rgba(108,114,255,0.35)",
      }}
    >
      {/* Animated icon */}
      <div className="logo-badge-pulse rounded-2xl p-5"
        style={{ background: "linear-gradient(135deg, #6C72FF22, #A78BFA22)" }}>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src="/shield-ai-icon.svg" alt="Shield AI" width={64} height={64} />
      </div>

      {/* Animated gradient title */}
      <h2
        className="text-2xl font-extrabold tracking-tight"
        style={{
          background: "linear-gradient(90deg, #6C72FF, #A78BFA, #6C72FF)",
          backgroundSize: "200% 100%",
          WebkitBackgroundClip: "text",
          WebkitTextFillColor: "transparent",
          animation: "gradientShift 4s ease-in-out infinite",
        }}
      >
        Shield AI
      </h2>

      <p className="text-sm tracking-widest uppercase font-semibold max-w-xs"
        style={{ color: "var(--text-muted)" }}>
        Enterprise Contract Intelligence
      </p>

      {/* Live indicator */}
      <div className="flex items-center gap-1.5 px-4 py-1.5 rounded-full"
        style={{ background: "#10B98115", border: "1px solid #10B98140" }}>
        <div className="w-1.5 h-1.5 rounded-full bg-emerald-400 progress-pulse" />
        <span className="text-xs font-medium" style={{ color: "#10B981" }}>Live · All agents ready</span>
      </div>

      {/* Description */}
      <p className="text-xs max-w-sm leading-relaxed" style={{ color: "var(--text-muted)" }}>
        Multi-agent AI platform for enterprise contract review — HIPAA · SOC 2 · GDPR
      </p>

      {/* Action buttons inside card */}
      <div className="flex gap-3 flex-wrap justify-center mt-2">
        <Link href="/upload"
          className="inline-flex items-center gap-2 px-5 py-2.5 rounded-lg text-sm font-semibold hover:opacity-90 transition-opacity"
          style={{ background: "var(--accent)", color: "#fff" }}>
          <Upload size={14} />
          Upload Contract
        </Link>
        <Link href="/queue"
          className="inline-flex items-center gap-2 px-5 py-2.5 rounded-lg text-sm font-semibold transition-colors hover:brightness-110"
          style={{ background: "rgba(255,255,255,0.08)", color: "var(--text-primary)", border: "1px solid rgba(255,255,255,0.15)" }}>
          <CheckSquare size={14} />
          Review Queue
        </Link>
      </div>
    </div>
  );
}

/* ─── Stat card (equal height) ───────────────────────────────────────────────── */
function StatCard({ value, label, loading = false, accent = "var(--accent)" }: {
  value: string | number; label: string; loading?: boolean; accent?: string;
}) {
  return (
    <div
      className="flex flex-col items-center justify-center rounded-xl px-4 py-5 text-center"
      style={{ background: "var(--bg-card)", border: "1px solid var(--border)" }}
    >
      {loading ? (
        <div className="w-7 h-7 rounded-full border-2 border-t-transparent spin"
          style={{ borderColor: accent, borderTopColor: "transparent" }} />
      ) : (
        <span className="text-2xl font-bold tracking-tight" style={{ color: accent }}>{value}</span>
      )}
      <span className="mt-2 text-xs" style={{ color: "var(--text-muted)" }}>{label}</span>
    </div>
  );
}

/* ─── Agent card (uniform height via flex) ───────────────────────────────────── */
interface AgentCardProps {
  number: number; name: string; subtitle: string;
  icon: React.ReactNode; model: string; modelTag?: string;
  items: string[]; accent?: string;
}

function AgentCard({ number, name, subtitle, icon, model, modelTag, items, accent = "var(--accent)" }: AgentCardProps) {
  return (
    <div className="rounded-xl p-5 flex flex-col gap-3 h-full"
      style={{ background: "var(--bg-card)", border: "1px solid var(--border)", minHeight: 280 }}>
      <div className="flex items-start gap-3">
        <div className="w-10 h-10 rounded-lg flex items-center justify-center flex-shrink-0"
          style={{ background: accent + "22" }}>
          <span style={{ color: accent }}>{icon}</span>
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-xs font-semibold px-2 py-0.5 rounded"
              style={{ background: accent + "22", color: accent }}>
              Agent {number}
            </span>
            {modelTag && (
              <span className="text-xs px-2 py-0.5 rounded"
                style={{ background: "var(--bg-surface)", color: "var(--text-muted)", border: "1px solid var(--border)" }}>
                {modelTag}
              </span>
            )}
          </div>
          <h3 className="mt-1 font-semibold text-sm" style={{ color: "var(--text-primary)" }}>{name}</h3>
          <p className="text-xs mt-0.5" style={{ color: "var(--text-muted)" }}>{subtitle}</p>
        </div>
      </div>
      <div className="text-xs px-3 py-1.5 rounded-lg"
        style={{ background: "var(--bg-surface)", color: "var(--text-secondary)", border: "1px solid var(--border)" }}>
        🤖 {model}
      </div>
      <ul className="flex flex-col gap-1 flex-1">
        {items.map(item => (
          <li key={item} className="flex items-center gap-2 text-xs" style={{ color: "var(--text-secondary)" }}>
            <CheckCircle size={11} style={{ color: accent, flexShrink: 0 }} />
            {item}
          </li>
        ))}
      </ul>
    </div>
  );
}

/* ─── Nav card ───────────────────────────────────────────────────────────────── */
function NavCard({ href, icon, label, description }: {
  href: string; icon: React.ReactNode; label: string; description: string;
}) {
  return (
    <Link href={href}
      className="group rounded-xl p-4 flex items-start gap-3 transition-all duration-150 h-full"
      style={{ background: "var(--bg-card)", border: "1px solid var(--border)" }}
      onMouseEnter={e => {
        (e.currentTarget as HTMLAnchorElement).style.borderColor = "var(--accent)";
        (e.currentTarget as HTMLAnchorElement).style.background = "var(--bg-surface)";
      }}
      onMouseLeave={e => {
        (e.currentTarget as HTMLAnchorElement).style.borderColor = "var(--border)";
        (e.currentTarget as HTMLAnchorElement).style.background = "var(--bg-card)";
      }}
    >
      <div className="w-9 h-9 rounded-lg flex items-center justify-center flex-shrink-0"
        style={{ background: "var(--accent)22", color: "var(--accent)" }}>
        {icon}
      </div>
      <div>
        <p className="font-medium text-sm" style={{ color: "var(--text-primary)" }}>{label}</p>
        <p className="text-xs mt-0.5" style={{ color: "var(--text-muted)" }}>{description}</p>
      </div>
    </Link>
  );
}

/* ─── Section heading ─────────────────────────────────────────────────────────── */
function SectionHeading({ label, title }: { label: string; title: string }) {
  return (
    <div className="mb-5">
      <span className="text-xs font-semibold uppercase tracking-widest px-2 py-1 rounded"
        style={{ background: "var(--accent)22", color: "var(--accent)" }}>
        {label}
      </span>
      <h2 className="mt-2 text-base font-bold" style={{ color: "var(--text-primary)" }}>{title}</h2>
    </div>
  );
}

/* ─── Page ───────────────────────────────────────────────────────────────────── */
export default function HomePage() {
  const [summary, setSummary] = useState<RiskSummary | null>(null);
  const [statsLoading, setStatsLoading] = useState(true);

  useEffect(() => {
    fetch(`${BACKEND}/dashboard/risk-summary`)
      .then(r => r.ok ? r.json() : null)
      .then(d => { if (d) setSummary(d); })
      .catch(() => null)
      .finally(() => setStatsLoading(false));
  }, []);

  const totalContracts = summary?.total_contracts ?? 0;
  const processed = summary?.processed_contracts ?? 0;
  const avgRisk = summary?.avg_risk_score ?? 0;
  const anomalies = summary?.anomalies?.length ?? 0;

  return (
    <>
      <Topbar title="Home" />
      <main className="flex-1 overflow-y-auto min-h-0">

        {/* ── Hero: centered logo card + stats ── */}
        <section className="relative overflow-hidden"
          style={{ background: "linear-gradient(160deg, #060D1F 0%, #0D1628 55%, #0f172a 100%)" }}>

          {/* Animated glow orbs */}
          <div className="orb-pulse absolute top-0 right-0 w-[450px] h-[450px] rounded-full pointer-events-none"
            style={{ background: "var(--accent)", transform: "translate(35%, -35%)", filter: "blur(90px)", opacity: 0.25 }} />
          <div className="orb-pulse absolute bottom-0 left-0 w-[300px] h-[300px] rounded-full pointer-events-none"
            style={{ background: "#A78BFA", transform: "translate(-40%, 40%)", filter: "blur(80px)", opacity: 0.15, animationDelay: "2s" }} />

          <div className="relative z-10 max-w-4xl mx-auto px-4 sm:px-6 py-8 sm:py-12 flex flex-col items-center gap-6 sm:gap-8">

            {/* Centered Shield Logo Card */}
            <div className="w-full max-w-lg">
              <ShieldLogoCard />
            </div>

            {/* Live stats row */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 w-full">
              <StatCard value={statsLoading ? "—" : totalContracts} label="Total Contracts" loading={statsLoading} />
              <StatCard value={statsLoading ? "—" : processed} label="Processed" loading={statsLoading} accent="#10B981" />
              <StatCard value={statsLoading ? "—" : `${avgRisk}`} label="Avg Risk Score" loading={statsLoading} accent="#F59E0B" />
              <StatCard value={statsLoading ? "—" : anomalies} label="Anomalies Flagged" loading={statsLoading} accent={anomalies > 0 ? "#EF4444" : "#22C55E"} />
            </div>

            {/* Quick action links */}
            <div className="flex gap-3 flex-wrap justify-center">
              <Link href="/dashboard/risk"
                className="inline-flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors hover:brightness-110"
                style={{ background: "var(--bg-card)", color: "var(--text-secondary)", border: "1px solid var(--border)" }}>
                <BarChart2 size={14} /> Risk Dashboard
              </Link>
              <Link href="/contracts"
                className="inline-flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors hover:brightness-110"
                style={{ background: "var(--bg-card)", color: "var(--text-secondary)", border: "1px solid var(--border)" }}>
                <FileText size={14} /> Recent Uploads
              </Link>
              <Link href="/ask"
                className="inline-flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors hover:brightness-110"
                style={{ background: "var(--bg-card)", color: "var(--text-secondary)", border: "1px solid var(--border)" }}>
                <MessageSquare size={14} /> Ask Shield AI
              </Link>
            </div>
          </div>
        </section>

        {/* ── Status breakdown (if live data available) ── */}
        {summary && Object.keys(summary.by_status ?? {}).length > 0 && (
          <section className="px-4 py-6 sm:px-6">
            <div className="max-w-6xl mx-auto">
              <SectionHeading label="Live" title="Contract Status Breakdown" />
              <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-6 gap-3">
                {Object.entries(summary.by_status).map(([status, count]) => {
                  const colors: Record<string, string> = {
                    auto_approved: "#22C55E", manager_review: "#F59E0B",
                    legal_review: "#38BDF8", rejected: "#EF4444",
                    processing: "#6C72FF", extracted: "#10B981",
                    quarantined: "#F97316", uploaded: "#7E89AC",
                  };
                  const color = colors[status] ?? "#7E89AC";
                  return (
                    <div key={status} className="rounded-xl p-4 text-center"
                      style={{ background: "var(--bg-card)", border: `1px solid ${color}30` }}>
                      <p className="text-2xl font-bold" style={{ color }}>{count}</p>
                      <p className="text-xs mt-1 capitalize" style={{ color: "var(--text-muted)" }}>
                        {status.replace(/_/g, " ")}
                      </p>
                    </div>
                  );
                })}
              </div>
            </div>
          </section>
        )}

        {/* ── Pipeline ── */}
        <section className="px-6 py-8">
          <div className="max-w-6xl mx-auto">
            <SectionHeading label="Pipeline" title="6-Agent Processing Pipeline" />

            {/* Model legend */}
            <div className="flex flex-wrap gap-2 mb-5">
              <span className="inline-flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-full"
                style={{ background: "var(--accent)15", color: "var(--accent)", border: "1px solid var(--accent)40" }}>
                🤖 Primary: Gemini 2.5 Flash-Lite
              </span>
              <span className="inline-flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-full"
                style={{ background: "var(--bg-card)", color: "var(--text-muted)", border: "1px solid var(--border)" }}>
                ↩ Fallback: Gemini 1.5 Flash
              </span>
            </div>

            {/* Uniform 3-column grid — all 6 cards same height per row */}
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 items-stretch">
              <AgentCard number={4} name="Security Gate" subtitle="Runs at upload — pre-LLM threat screening"
                icon={<Lock size={18} />} model="Lobster Trap + Offline Detector" modelTag="No LLM"
                items={["Prompt injection detection", "Malicious payload scanning", "Quarantine before any LLM call", "Offline-safe regex fallback"]}
                accent="#EF4444" />
              <AgentCard number={0} name="Contract Classifier" subtitle="Determines type, sector & applicable frameworks"
                icon={<Brain size={18} />} model="Gemini 2.5 Flash-Lite" modelTag="Fast"
                items={["Contract type (MSA / NDA / DPA / BAA…)", "Industry sector (Healthcare / Fintech…)", "Jurisdiction & governing law", "Applicable frameworks (HIPAA / GDPR / SOC 2…)"]}
                accent="#A78BFA" />
              <AgentCard number={1} name="Document Extraction" subtitle="Structured data from raw contract text"
                icon={<FileText size={18} />} model="Gemini 2.5 Flash-Lite" modelTag="Fast"
                items={["Parties & signatories", "Effective & expiry dates", "Key obligations & clauses", "Executive summary"]}
                accent="#6C72FF" />
              <AgentCard number={2} name="Risk Assessment" subtitle="Semantic risk scoring with RAG retrieval"
                icon={<Brain size={18} />} model="Gemini 2.5 Flash-Lite + Pinecone RAG" modelTag="RAG"
                items={["Composite risk score (0–100)", "Critical / High / Medium findings", "Severity classification", "Peer contract comparison"]}
                accent="#F59E0B" />
              <AgentCard number={3} name="Compliance Check" subtitle="Multi-framework regulatory verification"
                icon={<CheckCircle size={18} />} model="Gemini 2.5 Flash-Lite + Pinecone RAG" modelTag="RAG"
                items={["HIPAA pass / fail per clause", "SOC 2 pass / fail per clause", "GDPR pass / fail per clause", "Gap analysis & evidence citations"]}
                accent="#10B981" />
              <AgentCard number={5} name="Approval Scoring" subtitle="Policy engine — deterministic, no LLM"
                icon={<GitMerge size={18} />} model="Policy-based · No LLM" modelTag="No LLM"
                items={["AUTO_APPROVE", "MANAGER_REVIEW", "LEGAL_REVIEW", "REJECT"]}
                accent="#8B5CF6" />
            </div>
          </div>
        </section>

        {/* ── Data Layer ── */}
        <section className="px-4 py-5 sm:px-6">
          <div className="max-w-6xl mx-auto">
            <SectionHeading label="Storage" title="Data Layer" />
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 items-stretch">
              {/* PostgreSQL */}
              <div className="rounded-xl p-5 flex flex-col gap-3 h-full"
                style={{ background: "var(--bg-card)", border: "1px solid var(--border)" }}>
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-lg flex items-center justify-center flex-shrink-0"
                    style={{ background: "#3B82F622" }}>
                    <Database size={18} style={{ color: "#3B82F6" }} />
                  </div>
                  <div>
                    <div className="flex items-center gap-2">
                      <h3 className="font-semibold text-sm" style={{ color: "var(--text-primary)" }}>PostgreSQL</h3>
                      <div className="w-1.5 h-1.5 rounded-full"
                        style={{ background: summary ? "#22C55E" : "#7E89AC" }} />
                    </div>
                    <p className="text-xs" style={{ color: "var(--text-muted)" }}>Primary relational store · {totalContracts} contracts</p>
                  </div>
                </div>
                <ul className="flex flex-col gap-1.5 flex-1">
                  {["Contracts, extractions, risk findings", "Compliance results & audit events",
                    "Human decisions + scoring feedback", "Comments, assignments & escalations"].map(item => (
                    <li key={item} className="flex items-center gap-2 text-xs" style={{ color: "var(--text-secondary)" }}>
                      <span style={{ color: "#3B82F6" }}>▸</span>{item}
                    </li>
                  ))}
                </ul>
              </div>

              {/* Pinecone */}
              <div className="rounded-xl p-5 flex flex-col gap-3 h-full"
                style={{ background: "var(--bg-card)", border: "1px solid var(--border)" }}>
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-lg flex items-center justify-center flex-shrink-0"
                    style={{ background: "#10B98122" }}>
                    <Zap size={18} style={{ color: "#10B981" }} />
                  </div>
                  <div>
                    <h3 className="font-semibold text-sm" style={{ color: "var(--text-primary)" }}>Pinecone Vector DB</h3>
                    <p className="text-xs" style={{ color: "var(--text-muted)" }}>Semantic search & RAG retrieval</p>
                  </div>
                </div>
                <ul className="flex flex-col gap-1.5 flex-1">
                  {["contracts namespace — peer contract embeddings",
                    "policies namespace — HIPAA / SOC 2 / GDPR corpus",
                    "Cosine similarity retrieval for agents 2 & 3",
                    "Real-time upsert on every processed contract"].map(item => (
                    <li key={item} className="flex items-center gap-2 text-xs" style={{ color: "var(--text-secondary)" }}>
                      <span style={{ color: "#10B981" }}>▸</span>{item}
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          </div>
        </section>

        {/* ── Architecture badges ── */}
        <section className="px-4 py-5 sm:px-6">
          <div className="max-w-6xl mx-auto">
            <SectionHeading label="Architecture" title="How it works" />
            <div className="flex flex-wrap gap-2">
              {[
                { label: "FastAPI Backend", icon: <Cpu size={13} /> },
                { label: "Async agent orchestration", icon: <GitMerge size={13} /> },
                { label: "Sector-aware scoring", icon: <BarChart2 size={13} /> },
                { label: "Human feedback loop", icon: <Activity size={13} /> },
                { label: "Full audit trail", icon: <ClipboardList size={13} /> },
                { label: "Role-based access", icon: <Shield size={13} /> },
                { label: "Pinecone RAG", icon: <Brain size={13} /> },
                { label: "PostgreSQL persistence", icon: <Database size={13} /> },
              ].map(({ label, icon }) => (
                <span key={label}
                  className="inline-flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-full"
                  style={{ background: "var(--bg-card)", color: "var(--text-secondary)", border: "1px solid var(--border)" }}>
                  <span style={{ color: "var(--accent)" }}>{icon}</span>
                  {label}
                </span>
              ))}
            </div>
          </div>
        </section>

        {/* ── Role Descriptions ── */}
        <section className="px-4 py-5 sm:px-6">
          <div className="max-w-6xl mx-auto">
            <SectionHeading label="Access" title="User Roles & Permissions" />
            {/* 5 roles: 1 col → 2 col → 3 col → naturally fills last row centred via justify-items */}
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 items-stretch">
              {[
                {
                  icon: "📋",
                  role: "Procurement Analyst",
                  color: "#94A3B8",
                  bg: "#94A3B815",
                  border: "#94A3B830",
                  what: "Entry-level operator who initiates the review pipeline.",
                  can: ["Upload single & bulk contracts", "View all uploaded contracts", "Delete own uploads"],
                  cannot: ["Approve or reject contracts", "Access audit trail", "Assign reviewers"],
                },
                {
                  icon: "📊",
                  role: "Compliance Officer",
                  color: "#FBBF24",
                  bg: "#FBBF2415",
                  border: "#FBBF2430",
                  what: "Reviews contracts routed to the manager queue.",
                  can: ["Approve / reject manager-review contracts", "Comment & annotate clauses", "Escalate to Legal team"],
                  cannot: ["Approve legal-review contracts", "Modify scoring policy"],
                },
                {
                  icon: "⚖️",
                  role: "Legal Reviewer",
                  color: "#38BDF8",
                  bg: "#38BDF815",
                  border: "#38BDF830",
                  what: "Senior gatekeeper for high-risk or escalated contracts.",
                  can: ["Approve / reject legal-review contracts", "Comment & annotate clauses", "Escalate to Executive"],
                  cannot: ["Modify scoring rules", "Delete contracts"],
                },
                {
                  icon: "👔",
                  role: "Executive",
                  color: "#A78BFA",
                  bg: "#A78BFA15",
                  border: "#A78BFA30",
                  what: "Strategic oversight with read access across all queues.",
                  can: ["View all contracts & queues", "Add comments & annotations", "Approve if escalated"],
                  cannot: ["Initiate uploads", "Modify scoring policy"],
                },
                {
                  icon: "🔍",
                  role: "Auditor",
                  color: "#2DD4BF",
                  bg: "#2DD4BF15",
                  border: "#2DD4BF30",
                  what: "Read-only compliance monitor with full audit access.",
                  can: ["View all contracts & queues", "Access full audit log", "Add read-only comments"],
                  cannot: ["Approve or reject contracts", "Upload contracts", "Modify any data"],
                },
              ].map(({ icon, role, color, bg, border, what, can: canDo, cannot }) => (
                <div key={role}
                  className="rounded-xl p-5 flex flex-col gap-3"
                  style={{ background: bg, border: `1px solid ${border}` }}>
                  {/* Role header */}
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-lg flex items-center justify-center text-xl flex-shrink-0"
                      style={{ background: `${color}20`, border: `1px solid ${color}40` }}>
                      {icon}
                    </div>
                    <div>
                      <h3 className="font-semibold text-sm" style={{ color: "var(--text-primary)" }}>{role}</h3>
                      <p className="text-xs mt-0.5 leading-snug" style={{ color: "var(--text-muted)" }}>{what}</p>
                    </div>
                  </div>

                  {/* Divider */}
                  <div className="h-px" style={{ background: border }} />

                  {/* Can do */}
                  <div>
                    <p className="text-xs font-semibold uppercase tracking-wider mb-1.5" style={{ color }}>
                      Can do
                    </p>
                    <ul className="flex flex-col gap-1">
                      {canDo.map(item => (
                        <li key={item} className="flex items-start gap-1.5 text-xs" style={{ color: "var(--text-secondary)" }}>
                          <span className="mt-0.5 flex-shrink-0" style={{ color: "#22C55E" }}>✓</span>
                          {item}
                        </li>
                      ))}
                    </ul>
                  </div>

                  {/* Cannot */}
                  <div className="mt-auto">
                    <p className="text-xs font-semibold uppercase tracking-wider mb-1.5" style={{ color: "var(--text-muted)" }}>
                      Cannot
                    </p>
                    <ul className="flex flex-col gap-1">
                      {cannot.map(item => (
                        <li key={item} className="flex items-start gap-1.5 text-xs" style={{ color: "var(--text-muted)" }}>
                          <span className="mt-0.5 flex-shrink-0" style={{ color: "#EF4444" }}>✕</span>
                          {item}
                        </li>
                      ))}
                    </ul>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* ── Quick Navigation ── */}
        <section className="px-4 py-5 sm:px-6">
          <div className="max-w-6xl mx-auto">
            <SectionHeading label="Navigate" title="Quick Navigation" />
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 items-stretch">
              <NavCard href="/upload"             icon={<Upload size={16} />}        label="Upload"           description="Upload single or bulk contracts" />
              <NavCard href="/contracts"          icon={<FileText size={16} />}      label="Recent Uploads"   description="Browse & inspect all contracts" />
              <NavCard href="/dashboard/risk"     icon={<BarChart2 size={16} />}     label="Risk Dashboard"   description="Portfolio risk analytics" />
              <NavCard href="/queue"              icon={<CheckSquare size={16} />}   label="Review Queue"     description="Approve, reject or escalate" />
              <NavCard href="/dashboard/security" icon={<Shield size={16} />}        label="Security"         description="Quarantine & threat log" />
              <NavCard href="/ask"                icon={<MessageSquare size={16} />} label="Ask Shield AI"    description="Natural language contract Q&A" />
              <NavCard href="/audit"              icon={<ClipboardList size={16} />} label="Audit Log"        description="Immutable event history" />
              <NavCard href="/scoring"            icon={<Settings size={16} />}      label="Scoring Policy"   description="Adjust weights & thresholds" />
              <NavCard href="/recovery"           icon={<Database size={16} />}      label="Data Recovery"    description="Cache fallback & service health" />
            </div>
          </div>
        </section>

        {/* ── Footer ── */}
        <footer className="px-4 pb-6 sm:px-6">
          <div className="max-w-6xl mx-auto">
            <div className="px-6 py-4 rounded-xl flex flex-col sm:flex-row items-center justify-between gap-2 text-xs"
              style={{ background: "var(--bg-card)", border: "1px solid var(--border)", color: "var(--text-muted)" }}>
              <span>Shield AI v0.3.0 · Multi-agent contract intelligence</span>
              <span>Gemini · Pinecone · PostgreSQL · FastAPI · Next.js</span>
            </div>
          </div>
        </footer>

      </main>
    </>
  );
}
