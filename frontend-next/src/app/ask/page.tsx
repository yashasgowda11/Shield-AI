"use client";

import { useEffect, useRef, useState } from "react";
import Topbar from "@/components/layout/Topbar";
import { Send } from "lucide-react";
import { fmtDate } from "@/lib/utils";

const BACKEND = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";

type Mode = "analytics" | "contract_qa";

interface ContractOption {
  id: number;
  filename: string;
  n_clauses: number;
}

interface AnalyticsResult {
  mode: "analytics";
  explanation?: string;
  rows?: Record<string, unknown>[];
  columns?: string[];
  sql?: string;
}

interface ContractQAResult {
  mode: "contract_qa";
  answer?: string;
  confidence?: number;
  cited_clauses?: Array<{ clause_number?: string; title?: string; text?: string; relevance?: string }>;
}

interface BlockedResult {
  mode: "blocked";
  reason?: string;
}

type AssistantResult = AnalyticsResult | ContractQAResult | BlockedResult;

interface Message {
  role: "user" | "assistant";
  content: string;
  result?: AssistantResult;
}

const ANALYTICS_SUGGESTIONS = [
  "Which contracts expire this quarter?",
  "Show all vendors with GDPR failures",
  "List contracts with risk score above 70",
  "How many contracts are in legal review?",
];

const QA_SUGGESTIONS = [
  "What are the payment terms?",
  "Who are the parties involved?",
  "What are the termination clauses?",
  "What governing law applies?",
];

export default function AskPage() {
  const [mode, setMode] = useState<Mode>("analytics");
  const [contracts, setContracts] = useState<ContractOption[]>([]);
  const [selectedContract, setSelectedContract] = useState<number | "">("");
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [expandedSql, setExpandedSql] = useState<Set<number>>(new Set());
  const [expandedClauses, setExpandedClauses] = useState<Set<number>>(new Set());
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    async function loadContracts() {
      try {
        const res = await fetch(`${BACKEND}/contracts/?limit=200`);
        if (!res.ok) return;
        const data = await res.json();
        const items: ContractOption[] = (data.items ?? []).filter(
          (c: ContractOption) => c.n_clauses > 0
        );
        setContracts(items);
      } catch {}
    }
    loadContracts();
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function send(question?: string) {
    const q = (question ?? input).trim();
    if (!q) return;
    setInput("");

    const userMsg: Message = { role: "user", content: q };
    setMessages((prev) => [...prev, userMsg]);
    setLoading(true);

    try {
      const body: Record<string, unknown> = { question: q };
      if (mode === "contract_qa" && selectedContract !== "") {
        body.contract_id = selectedContract;
      }
      const res = await fetch(`${BACKEND}/query/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await res.json();

      let result: AssistantResult;
      if (!res.ok || data.blocked || data.mode === "blocked") {
        result = { mode: "blocked", reason: data.reason ?? data.detail ?? "Request was blocked by security gate." };
      } else {
        result = data as AssistantResult;
      }

      const assistantMsg: Message = {
        role: "assistant",
        content: data.explanation ?? data.answer ?? data.reason ?? "",
        result,
      };
      setMessages((prev) => [...prev, assistantMsg]);
    } catch (e) {
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: String(e),
          result: { mode: "blocked", reason: String(e) },
        },
      ]);
    } finally {
      setLoading(false);
    }
  }

  function toggleSql(idx: number) {
    setExpandedSql((prev) => {
      const next = new Set(prev);
      next.has(idx) ? next.delete(idx) : next.add(idx);
      return next;
    });
  }

  function toggleClauses(idx: number) {
    setExpandedClauses((prev) => {
      const next = new Set(prev);
      next.has(idx) ? next.delete(idx) : next.add(idx);
      return next;
    });
  }

  return (
    <>
      <Topbar title="Ask Shield AI" />
      <main className="flex flex-col flex-1 p-4 sm:p-6 gap-4 max-w-4xl mx-auto w-full overflow-y-auto min-h-0">
        {/* Mode toggle + security badge */}
        <div className="flex flex-wrap items-center gap-3">
          {(["analytics", "contract_qa"] as Mode[]).map((m) => (
            <button
              key={m}
              onClick={() => setMode(m)}
              className="px-4 py-2 rounded-lg text-sm font-medium transition-colors"
              style={{
                background: mode === m ? "var(--accent)" : "var(--bg-card)",
                color: mode === m ? "#fff" : "var(--text-secondary)",
                border: `1px solid ${mode === m ? "var(--accent)" : "var(--border)"}`,
              }}
            >
              {m === "analytics" ? "📊 Analytics" : "❓ Ask about a contract"}
            </button>
          ))}
          <span
            className="text-xs px-3 py-1.5 rounded-full ml-auto"
            style={{ background: "var(--bg-card)", color: "var(--text-muted)", border: "1px solid var(--border)" }}
          >
            🪤 All questions scanned by Agent 4
          </span>
        </div>

        {/* Mode description + controls */}
        {mode === "analytics" ? (
          <div
            className="rounded-xl border p-4"
            style={{ background: "var(--bg-card)", borderColor: "var(--border)" }}
          >
            <p className="text-sm mb-3" style={{ color: "var(--text-secondary)" }}>
              Ask natural language questions across your entire contract corpus. Results are translated to SQL and executed against the database.
            </p>
            <div className="flex flex-wrap gap-2">
              {ANALYTICS_SUGGESTIONS.map((s) => (
                <button
                  key={s}
                  onClick={() => setInput(s)}
                  className="text-xs px-3 py-1.5 rounded-full transition-colors hover:brightness-110"
                  style={{ background: "var(--bg-surface)", color: "var(--text-secondary)", border: "1px solid var(--border)" }}
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div
            className="rounded-xl border p-4"
            style={{ background: "var(--bg-card)", borderColor: "var(--border)" }}
          >
            <p className="text-sm mb-3" style={{ color: "var(--text-secondary)" }}>
              Ask questions about a specific contract. The AI will cite relevant clauses.
            </p>
            <div className="mb-3">
              <label className="text-xs font-medium mb-1 block" style={{ color: "var(--text-muted)" }}>
                Select Contract
              </label>
              <select
                value={selectedContract}
                onChange={(e) => setSelectedContract(e.target.value === "" ? "" : Number(e.target.value))}
                className="w-full rounded-lg px-3 py-2 text-sm"
                style={{
                  background: "var(--bg-surface)",
                  color: "var(--text-primary)",
                  border: "1px solid var(--border)",
                  outline: "none",
                }}
              >
                <option value="">— pick a contract —</option>
                {contracts.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.filename} ({c.n_clauses} clauses)
                  </option>
                ))}
              </select>
            </div>
            <div className="flex flex-wrap gap-2">
              {QA_SUGGESTIONS.map((s) => (
                <button
                  key={s}
                  onClick={() => setInput(s)}
                  className="text-xs px-3 py-1.5 rounded-full transition-colors hover:brightness-110"
                  style={{ background: "var(--bg-surface)", color: "var(--text-secondary)", border: "1px solid var(--border)" }}
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Chat history */}
        <div className="flex flex-col gap-4 flex-1 min-h-0 overflow-y-auto">
          {messages.length === 0 && (
            <div className="flex items-center justify-center py-16">
              <p className="text-sm" style={{ color: "var(--text-muted)" }}>
                Ask a question to get started.
              </p>
            </div>
          )}
          {messages.map((msg, idx) => {
            if (msg.role === "user") {
              return (
                <div key={idx} className="flex justify-end">
                  <div
                    className="rounded-2xl rounded-tr-sm px-4 py-3 max-w-lg text-sm"
                    style={{ background: "var(--accent)", color: "#fff" }}
                  >
                    {msg.content}
                  </div>
                </div>
              );
            }

            const result = msg.result;
            return (
              <div key={idx} className="flex justify-start">
                <div
                  className="rounded-2xl rounded-tl-sm px-4 py-3 max-w-2xl w-full border"
                  style={{ background: "var(--bg-card)", borderColor: "var(--border)" }}
                >
                  {result?.mode === "blocked" && (
                    <div
                      className="rounded-lg p-3 text-sm"
                      style={{ background: "#DC262618", color: "#f87171", border: "1px solid #DC262640" }}
                    >
                      <strong>Blocked by Security Gate</strong>
                      <p className="mt-1">{(result as BlockedResult).reason}</p>
                    </div>
                  )}

                  {result?.mode === "analytics" && (
                    <div className="flex flex-col gap-3">
                      {(result as AnalyticsResult).explanation && (
                        <p className="text-sm" style={{ color: "var(--text-secondary)" }}>
                          {(result as AnalyticsResult).explanation}
                        </p>
                      )}
                      {(result as AnalyticsResult).rows && (result as AnalyticsResult).rows!.length > 0 && (
                        <div className="overflow-x-auto rounded-lg border" style={{ borderColor: "var(--border)" }}>
                          <table className="w-full text-xs">
                            <thead>
                              <tr style={{ background: "var(--bg-surface)", color: "var(--text-muted)" }}>
                                {((result as AnalyticsResult).columns ?? Object.keys((result as AnalyticsResult).rows![0])).map((col) => (
                                  <th key={col} className="px-3 py-2 text-left font-medium">{col}</th>
                                ))}
                              </tr>
                            </thead>
                            <tbody>
                              {(result as AnalyticsResult).rows!.map((row, ri) => (
                                <tr key={ri} className="border-t" style={{ borderColor: "var(--border)" }}>
                                  {((result as AnalyticsResult).columns ?? Object.keys(row)).map((col) => (
                                    <td key={col} className="px-3 py-2" style={{ color: "var(--text-secondary)" }}>
                                      {String(row[col] ?? "")}
                                    </td>
                                  ))}
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      )}
                      {(result as AnalyticsResult).sql && (
                        <div>
                          <button
                            onClick={() => toggleSql(idx)}
                            className="text-xs font-medium mb-1"
                            style={{ color: "var(--text-muted)" }}
                          >
                            {expandedSql.has(idx) ? "▾" : "▸"} View SQL
                          </button>
                          {expandedSql.has(idx) && (
                            <pre
                              className="text-xs rounded-lg p-3 overflow-x-auto"
                              style={{
                                background: "var(--bg-surface)",
                                color: "#a5b4fc",
                                border: "1px solid var(--border)",
                                fontFamily: "monospace",
                              }}
                            >
                              {(result as AnalyticsResult).sql}
                            </pre>
                          )}
                        </div>
                      )}
                    </div>
                  )}

                  {result?.mode === "contract_qa" && (
                    <div className="flex flex-col gap-3">
                      {(result as ContractQAResult).answer && (
                        <p className="text-sm" style={{ color: "var(--text-secondary)" }}>
                          {(result as ContractQAResult).answer}
                        </p>
                      )}
                      {(result as ContractQAResult).confidence !== undefined && (
                        <div>
                          <div className="flex items-center justify-between text-xs mb-1" style={{ color: "var(--text-muted)" }}>
                            <span>Confidence</span>
                            <span>{Math.round(((result as ContractQAResult).confidence ?? 0) * 100)}%</span>
                          </div>
                          <div className="rounded-full h-2 overflow-hidden" style={{ background: "var(--bg-surface)" }}>
                            <div
                              className="h-2 rounded-full"
                              style={{
                                width: `${Math.round(((result as ContractQAResult).confidence ?? 0) * 100)}%`,
                                background: "var(--accent)",
                              }}
                            />
                          </div>
                        </div>
                      )}
                      {(result as ContractQAResult).cited_clauses && (result as ContractQAResult).cited_clauses!.length > 0 && (
                        <div>
                          <button
                            onClick={() => toggleClauses(idx)}
                            className="text-xs font-medium mb-1"
                            style={{ color: "var(--text-muted)" }}
                          >
                            {expandedClauses.has(idx) ? "▾" : "▸"} Cited Clauses ({(result as ContractQAResult).cited_clauses!.length})
                          </button>
                          {expandedClauses.has(idx) && (
                            <div className="flex flex-col gap-2">
                              {(result as ContractQAResult).cited_clauses!.map((cl, ci) => (
                                <div
                                  key={ci}
                                  className="rounded-lg p-3 text-xs border"
                                  style={{ background: "var(--bg-surface)", borderColor: "var(--border)" }}
                                >
                                  <p className="font-medium mb-1" style={{ color: "var(--accent)" }}>
                                    {cl.clause_number ? `§${cl.clause_number}` : ""} {cl.title}
                                  </p>
                                  {cl.text && (
                                    <p style={{ color: "var(--text-secondary)" }}>{cl.text}</p>
                                  )}
                                  {cl.relevance && (
                                    <p className="mt-1 italic" style={{ color: "var(--text-muted)" }}>
                                      {cl.relevance}
                                    </p>
                                  )}
                                </div>
                              ))}
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </div>
            );
          })}
          {loading && (
            <div className="flex justify-start">
              <div
                className="rounded-2xl rounded-tl-sm px-4 py-3 text-sm border"
                style={{ background: "var(--bg-card)", borderColor: "var(--border)", color: "var(--text-muted)" }}
              >
                Thinking…
              </div>
            </div>
          )}
          <div ref={bottomRef} />
        </div>

        {/* Input bar */}
        <div
          className="flex items-center gap-2 rounded-xl border px-4 py-2"
          style={{ background: "var(--bg-card)", borderColor: "var(--border)" }}
        >
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && send()}
            placeholder={
              mode === "analytics"
                ? "Ask about your contracts…"
                : selectedContract
                ? "Ask about this contract…"
                : "Select a contract first…"
            }
            disabled={loading || (mode === "contract_qa" && selectedContract === "")}
            className="flex-1 bg-transparent text-sm outline-none"
            style={{ color: "var(--text-primary)" }}
          />
          <button
            onClick={() => send()}
            disabled={loading || !input.trim() || (mode === "contract_qa" && selectedContract === "")}
            className="rounded-lg p-2 transition-opacity disabled:opacity-40"
            style={{ background: "var(--accent)", color: "#fff" }}
          >
            <Send size={16} />
          </button>
        </div>
      </main>
    </>
  );
}
