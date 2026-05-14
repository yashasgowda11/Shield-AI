"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import Topbar from "@/components/layout/Topbar";
import { useRole } from "@/hooks/useRole";
import { api } from "@/lib/api";
import { Upload, FileText, X, CheckCircle, AlertTriangle, ArrowUpRight } from "lucide-react";

const BACKEND = "/api/backend";

type FileResult = {
  filename: string;
  status: string;
  id?: number;
  message?: string;
  n_clauses?: number;
};

/* ─── Pipeline progress ─────────────────────────────────────────────────────── */
const STEPS = [
  { id: "security",    label: "Security Gate",       icon: "🛡️", desc: "Scanning for threats & injections",              agent: "Agent 4" },
  { id: "extraction",  label: "Document Extraction",  icon: "📄", desc: "Gemini 1.5 Flash · Parsing clauses & obligations", agent: "Agent 1" },
  { id: "risk",        label: "Risk Assessment",      icon: "🔍", desc: "Gemini 1.5 Pro + Pinecone RAG",                   agent: "Agent 2" },
  { id: "compliance",  label: "Compliance Check",     icon: "✅", desc: "HIPAA · SOC 2 · GDPR verification",               agent: "Agent 3" },
  { id: "scoring",     label: "Approval Scoring",     icon: "🎯", desc: "Policy engine · No LLM in the loop",              agent: "Agent 5" },
];

type StepState = "done" | "active" | "pending" | "failed";

function getStepsDone(status: string): number {
  switch (status) {
    case "uploaded":      return 0;
    case "processing":    return 1;   // security done, extraction running
    case "extracted":     return 4;   // extraction+risk+compliance done, scoring next
    case "auto_approved":
    case "manager_review":
    case "legal_review":
    case "rejected":      return 5;   // all done
    case "quarantined":   return -1;  // failed at security
    default:              return 0;
  }
}

function stepState(stepIndex: number, stepsDone: number): StepState {
  if (stepsDone === -1) return stepIndex === 0 ? "failed" : "pending";
  if (stepIndex < stepsDone) return "done";
  if (stepIndex === stepsDone && stepsDone < STEPS.length) return "active";
  return "pending";
}

const FINAL_STATUSES = ["auto_approved", "manager_review", "legal_review", "rejected", "quarantined"];

function finalLabel(status: string): { text: string; color: string; emoji: string } {
  switch (status) {
    case "auto_approved":   return { text: "Auto-Approved",    color: "#22C55E", emoji: "✅" };
    case "manager_review":  return { text: "Manager Review",   color: "#F59E0B", emoji: "👔" };
    case "legal_review":    return { text: "Legal Review",     color: "#38BDF8", emoji: "⚖️" };
    case "rejected":        return { text: "Rejected",         color: "#EF4444", emoji: "❌" };
    case "quarantined":     return { text: "Quarantined",      color: "#F97316", emoji: "🚫" };
    default:                return { text: status,             color: "#7E89AC", emoji: "⏳" };
  }
}

function PipelineProgress({ contractId, filename }: { contractId: number; filename: string }) {
  const [status, setStatus] = useState("processing");
  const [done, setDone] = useState(false);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const poll = useCallback(async () => {
    try {
      const res = await fetch(`${BACKEND}/contracts/${contractId}`);
      if (!res.ok) return;
      const data = await res.json();
      const s = data.status ?? "processing";
      setStatus(s);
      if (FINAL_STATUSES.includes(s)) {
        setDone(true);
        if (intervalRef.current) clearInterval(intervalRef.current);
      }
    } catch { /* ignore */ }
  }, [contractId]);

  useEffect(() => {
    poll();
    intervalRef.current = setInterval(poll, 2000);
    return () => { if (intervalRef.current) clearInterval(intervalRef.current); };
  }, [poll]);

  const stepsDone = getStepsDone(status);
  const label = done ? finalLabel(status) : null;

  return (
    <div className="rounded-2xl border p-6 fade-in-up"
      style={{ background: "var(--bg-card)", borderColor: "var(--border)" }}>
      {/* Header */}
      <div className="flex items-start justify-between mb-5 gap-3">
        <div>
          <p className="font-semibold text-sm" style={{ color: "var(--text-primary)" }}>{filename}</p>
          <p className="text-xs mt-0.5" style={{ color: "var(--text-muted)" }}>Contract #{contractId}</p>
        </div>
        {!done && (
          <div className="flex items-center gap-1.5 text-xs px-3 py-1 rounded-full"
            style={{ background: "#6C72FF15", border: "1px solid #6C72FF40", color: "var(--accent)" }}>
            <div className="w-1.5 h-1.5 rounded-full progress-pulse" style={{ background: "var(--accent)" }} />
            Processing…
          </div>
        )}
        {done && label && (
          <div className="flex items-center gap-1.5 text-xs px-3 py-1 rounded-full font-semibold"
            style={{ background: `${label.color}18`, border: `1px solid ${label.color}40`, color: label.color }}>
            {label.emoji} {label.text}
          </div>
        )}
      </div>

      {/* Steps */}
      <div className="flex flex-col gap-0">
        {STEPS.map((step, i) => {
          const state: StepState = stepState(i, stepsDone);
          return (
            <div key={step.id} className="flex items-start gap-4">
              {/* Connector line */}
              <div className="flex flex-col items-center">
                <div className="w-8 h-8 rounded-full flex items-center justify-center text-sm flex-shrink-0 transition-all duration-500"
                  style={{
                    background: state === "done" ? "#22C55E20"
                      : state === "active" ? "#6C72FF20"
                      : state === "failed" ? "#EF444420"
                      : "var(--bg-surface)",
                    border: `2px solid ${
                      state === "done" ? "#22C55E"
                      : state === "active" ? "#6C72FF"
                      : state === "failed" ? "#EF4444"
                      : "var(--border)"
                    }`,
                  }}>
                  {state === "done" ? "✓"
                    : state === "failed" ? "✗"
                    : state === "active" ? (
                      <div className="w-3 h-3 rounded-full spin"
                        style={{ border: "2px solid #6C72FF", borderTopColor: "transparent" }} />
                    ) : <span className="text-xs" style={{ color: "var(--text-muted)" }}>{i + 1}</span>}
                </div>
                {i < STEPS.length - 1 && (
                  <div className="w-px flex-1 mt-1 mb-1 min-h-[20px] transition-all duration-500"
                    style={{ background: state === "done" ? "#22C55E40" : "var(--border)" }} />
                )}
              </div>

              {/* Content */}
              <div className="pb-4 flex-1">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-sm">{step.icon}</span>
                  <p className="font-medium text-sm transition-colors"
                    style={{
                      color: state === "done" ? "#22C55E"
                        : state === "active" ? "var(--text-primary)"
                        : state === "failed" ? "#EF4444"
                        : "var(--text-muted)",
                    }}>
                    {step.label}
                  </p>
                  <span className="text-xs px-2 py-0.5 rounded"
                    style={{ background: "var(--bg-surface)", color: "var(--text-muted)", border: "1px solid var(--border)" }}>
                    {step.agent}
                  </span>
                  {state === "active" && (
                    <span className="text-xs progress-pulse" style={{ color: "var(--accent)" }}>Running…</span>
                  )}
                </div>
                <p className="text-xs mt-0.5" style={{ color: "var(--text-muted)" }}>{step.desc}</p>
              </div>
            </div>
          );
        })}
      </div>

      {/* Done CTA */}
      {done && (
        <div className="mt-2 pt-4 border-t flex items-center justify-between"
          style={{ borderColor: "var(--border)" }}>
          <p className="text-xs" style={{ color: "var(--text-muted)" }}>Pipeline complete</p>
          <a href={`/contracts/${contractId}`}
            className="inline-flex items-center gap-1.5 text-xs font-semibold px-4 py-2 rounded-lg transition-opacity hover:opacity-80"
            style={{ background: "var(--accent)", color: "#fff" }}>
            View contract <ArrowUpRight size={12} />
          </a>
        </div>
      )}
    </div>
  );
}

/* ─── Page ───────────────────────────────────────────────────────────────────── */
export default function UploadPage() {
  const { role } = useRole();
  const [tab, setTab] = useState<"single" | "bulk">("single");
  const [dragging, setDragging] = useState(false);
  const [files, setFiles] = useState<File[]>([]);
  const [uploading, setUploading] = useState(false);
  const [results, setResults] = useState<FileResult[]>([]);
  const [pipelines, setPipelines] = useState<{ id: number; filename: string }[]>([]);
  const [error, setError] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  const canUpload = role === "Procurement Analyst";
  const isBulk = tab === "bulk";
  const maxFiles = isBulk ? 20 : 1;

  function addFiles(incoming: FileList | null) {
    if (!incoming) return;
    const valid = Array.from(incoming).filter(f => f.name.match(/\.(pdf|docx)$/i)).slice(0, maxFiles);
    setFiles(isBulk ? [...files, ...valid].slice(0, maxFiles) : [valid[0]].filter(Boolean));
    setResults([]);
    setError("");
  }

  function removeFile(i: number) {
    setFiles(files.filter((_, idx) => idx !== i));
  }

  async function handleUpload() {
    if (!files.length) return;
    setUploading(true);
    setError("");
    setResults([]);
    setPipelines([]);
    try {
      const actor = `user:${role}`;
      if (isBulk) {
        const r = await api.contracts.bulkUpload(files, actor);
        const newResults = r.results.map(x => ({
          filename: x.filename, status: x.status, id: x.id,
          message: x.message, n_clauses: x.n_clauses,
        }));
        setResults(newResults);
        // Start pipeline tracking for successfully queued contracts
        const newPipes = newResults.filter(x => x.id && x.status !== "quarantined" && x.status !== "error")
          .map(x => ({ id: x.id!, filename: x.filename }));
        setPipelines(newPipes);
      } else {
        const r = await api.contracts.upload(files[0], actor);
        setResults([{ filename: files[0].name, status: r.status, id: r.id, n_clauses: r.n_clauses }]);
        if (r.id && r.status !== "quarantined") {
          setPipelines([{ id: r.id, filename: files[0].name }]);
        }
      }
      setFiles([]);
    } catch (e) {
      setError(String(e));
    } finally {
      setUploading(false);
    }
  }

  return (
    <>
      <Topbar title="Upload Contract" />
      <main className="flex flex-col items-center px-4 py-8 flex-1 overflow-y-auto min-h-0">
        <div className="w-full max-w-3xl flex flex-col gap-6">

          {/* Role warning */}
          {!canUpload && (
            <div className="rounded-xl p-4 text-sm text-amber-400 bg-amber-400/10 border border-amber-400/20">
              Only <strong>Procurement Analysts</strong> can upload contracts. Switch role in the top bar.
            </div>
          )}

          {/* Tabs */}
          <div className="flex justify-center">
            <div className="flex gap-1 p-1 rounded-xl" style={{ background: "var(--bg-card)", border: "1px solid var(--border)" }}>
              {(["single", "bulk"] as const).map(t => (
                <button key={t} onClick={() => { setTab(t); setFiles([]); setResults([]); setPipelines([]); }}
                  className="px-6 py-2 rounded-lg text-sm font-medium transition-all"
                  style={tab === t
                    ? { background: "var(--accent)", color: "#fff" }
                    : { color: "var(--text-muted)" }}>
                  {t === "single" ? "📄 Single File" : "📦 Bulk Upload (up to 20)"}
                </button>
              ))}
            </div>
          </div>

          {/* Drop zone — half viewport height */}
          <div
            onDragOver={e => { e.preventDefault(); setDragging(true); }}
            onDragLeave={() => setDragging(false)}
            onDrop={e => { e.preventDefault(); setDragging(false); addFiles(e.dataTransfer.files); }}
            onClick={() => canUpload && inputRef.current?.click()}
            className="w-full rounded-2xl border-2 border-dashed flex flex-col items-center justify-center text-center cursor-pointer transition-all duration-200"
            style={{
              minHeight: "45vh",
              borderColor: dragging ? "var(--accent)" : files.length > 0 ? "var(--accent)66" : "var(--border)",
              background: dragging ? "var(--accent)0D" : files.length > 0 ? "var(--accent)08" : "var(--bg-card)",
              opacity: canUpload ? 1 : 0.4,
              pointerEvents: canUpload ? "auto" : "none",
            }}
          >
            {files.length === 0 ? (
              <>
                <div className="w-20 h-20 rounded-2xl flex items-center justify-center mb-4 transition-all"
                  style={{ background: dragging ? "var(--accent)22" : "var(--bg-surface)", border: "1px solid var(--border)" }}>
                  <Upload size={36} style={{ color: dragging ? "var(--accent)" : "var(--text-muted)" }} />
                </div>
                <p className="text-lg font-semibold text-white mb-2">
                  {dragging ? "Drop to upload" : `Drop ${isBulk ? "up to 20 files" : "a file"} here`}
                </p>
                <p className="text-sm mb-4" style={{ color: "var(--text-muted)" }}>
                  or click to browse your computer
                </p>
                <p className="text-xs px-4 py-2 rounded-full"
                  style={{ background: "var(--bg-surface)", color: "var(--text-muted)", border: "1px solid var(--border)" }}>
                  PDF or DOCX · Max 50 MB per file
                </p>
              </>
            ) : (
              <div className="w-full px-6 flex flex-col items-center gap-3">
                <div className="flex items-center gap-2 mb-2">
                  <CheckCircle size={20} style={{ color: "#22C55E" }} />
                  <p className="text-sm font-semibold text-white">
                    {files.length} file{files.length > 1 ? "s" : ""} selected
                  </p>
                </div>
                <div className="w-full max-h-48 overflow-y-auto flex flex-col gap-2">
                  {files.map((f, i) => (
                    <div key={i}
                      className="flex items-center justify-between rounded-xl px-4 py-3 w-full"
                      style={{ background: "var(--bg-surface)", border: "1px solid var(--border)" }}
                      onClick={e => e.stopPropagation()}>
                      <div className="flex items-center gap-2 text-sm min-w-0">
                        <FileText size={14} style={{ color: "var(--accent)", flexShrink: 0 }} />
                        <span className="text-white truncate">{f.name}</span>
                        <span className="text-xs flex-shrink-0" style={{ color: "var(--text-muted)" }}>
                          {(f.size / 1024).toFixed(0)} KB
                        </span>
                      </div>
                      <button onClick={() => removeFile(i)} className="ml-3 hover:text-red-400 transition-colors flex-shrink-0"
                        style={{ color: "var(--text-muted)" }}>
                        <X size={14} />
                      </button>
                    </div>
                  ))}
                </div>
                <p className="text-xs mt-1" style={{ color: "var(--text-muted)" }}>Click elsewhere to add more files</p>
              </div>
            )}
            <input ref={inputRef} type="file" accept=".pdf,.docx" multiple={isBulk} className="hidden"
              onChange={e => addFiles(e.target.files)} />
          </div>

          {/* Upload button */}
          {files.length > 0 && (
            <button onClick={handleUpload} disabled={uploading || !canUpload}
              className="w-full py-4 rounded-xl text-base font-bold transition-all disabled:opacity-50 flex items-center justify-center gap-3"
              style={{ background: "var(--accent)", color: "#fff" }}>
              {uploading ? (
                <>
                  <div className="w-5 h-5 rounded-full border-2 border-t-transparent spin"
                    style={{ borderColor: "#ffffff", borderTopColor: "transparent" }} />
                  Uploading & running security gate…
                </>
              ) : (
                <>
                  <Upload size={18} />
                  Upload {files.length} file{files.length > 1 ? "s" : ""} · Start Pipeline
                </>
              )}
            </button>
          )}

          {/* Error */}
          {error && (
            <div className="rounded-xl p-4 text-sm text-red-400 bg-red-400/10 border border-red-400/20 flex gap-2">
              <AlertTriangle size={16} className="shrink-0 mt-0.5" />
              {error}
            </div>
          )}

          {/* Upload summary (for bulk) */}
          {results.length > 0 && results.some(r => ["quarantined", "error", "duplicate"].includes(r.status)) && (
            <div className="flex flex-col gap-2">
              <p className="text-xs font-bold uppercase tracking-wider" style={{ color: "var(--text-muted)" }}>
                Upload Summary
              </p>
              {results.filter(r => ["quarantined", "error", "duplicate"].includes(r.status)).map((r, i) => (
                <div key={i} className="rounded-xl p-3 flex items-center gap-3"
                  style={{ background: "var(--bg-card)", border: "1px solid var(--border)" }}>
                  {r.status === "quarantined" || r.status === "error"
                    ? <AlertTriangle size={16} className="text-amber-400 shrink-0" />
                    : <CheckCircle size={16} className="text-blue-400 shrink-0" />}
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-white truncate">{r.filename}</p>
                    {r.message && <p className="text-xs mt-0.5" style={{ color: "var(--text-muted)" }}>{r.message}</p>}
                  </div>
                  <span className="text-xs px-2 py-1 rounded-full font-medium capitalize flex-shrink-0"
                    style={{
                      background: r.status === "quarantined" ? "#F9731620" : r.status === "error" ? "#EF444420" : "#3B82F620",
                      color: r.status === "quarantined" ? "#F97316" : r.status === "error" ? "#EF4444" : "#38BDF8",
                    }}>
                    {r.status}
                  </span>
                </div>
              ))}
            </div>
          )}

          {/* Pipeline progress trackers */}
          {pipelines.length > 0 && (
            <div className="flex flex-col gap-4">
              <p className="text-xs font-bold uppercase tracking-wider" style={{ color: "var(--text-muted)" }}>
                🚀 Agent Pipeline Progress
              </p>
              {pipelines.map(p => (
                <PipelineProgress key={p.id} contractId={p.id} filename={p.filename} />
              ))}
            </div>
          )}
        </div>
      </main>
    </>
  );
}
