"use client";

import { useEffect, useState } from "react";
import Topbar from "@/components/layout/Topbar";
import { AlertTriangle, BarChart2 } from "lucide-react";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  Cell, PieChart, Pie, Legend,
} from "recharts";

const BACKEND = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";
const STATUS_PALETTE = ["#6C72FF","#22C55E","#F59E0B","#EF4444","#8B5CF6","#10B981","#F97316","#3B82F6"];

function Card({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return (
    <div className={`rounded-xl p-5 ${className}`}
      style={{ background: "var(--bg-card)", border: "1px solid var(--border)" }}>
      {children}
    </div>
  );
}

function MetricCard({ label, value, sub, accent = false }: {
  label: string; value: string | number; sub?: string; accent?: boolean;
}) {
  return (
    <Card>
      <p className="text-xs font-semibold uppercase tracking-widest mb-1" style={{ color: "var(--text-muted)" }}>{label}</p>
      <p className="text-2xl font-bold" style={{ color: accent ? "#EF4444" : "var(--accent)" }}>{value}</p>
      {sub && <p className="text-xs mt-1" style={{ color: "var(--text-muted)" }}>{sub}</p>}
    </Card>
  );
}

const ttStyle = { contentStyle: { background: "#0D1628", border: "1px solid #212C4D", borderRadius: 8 }, labelStyle: { color: "#D1D5E8" } };

export default function RiskDashboard() {
  const [data, setData]       = useState<Record<string, any> | null>(null);
  const [error, setError]     = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch(`${BACKEND}/dashboard/risk-summary`)
      .then(r => r.json()).then(setData).catch(e => setError(String(e)))
      .finally(() => setLoading(false));
  }, []);

  return (
    <>
      <Topbar title="Risk Dashboard" />
      <main className="p-4 sm:p-6 flex flex-col gap-6 flex-1 overflow-y-auto min-h-0">
        {loading && <p className="text-sm" style={{ color: "var(--text-muted)" }}>Loading…</p>}
        {error && (
          <div className="rounded-lg p-4 text-sm text-red-400 bg-red-400/10 border border-red-400/20">
            Backend unreachable: {error}
          </div>
        )}

        {data && data.total_contracts === 0 && (
          <div className="rounded-lg p-10 text-center" style={{ background: "var(--bg-card)", border: "1px solid var(--border)" }}>
            <BarChart2 size={36} className="mx-auto mb-3 opacity-30" style={{ color: "var(--text-muted)" }} />
            <p className="text-sm" style={{ color: "var(--text-muted)" }}>No contracts uploaded yet. Upload one to populate this dashboard.</p>
          </div>
        )}

        {data && data.total_contracts > 0 && (<>

          {/* ── Headline metrics ── */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <MetricCard label="Total Contracts"   value={data.total_contracts} />
            <MetricCard label="Processed"         value={data.processed_contracts} />
            <MetricCard label="Avg Risk Score"    value={`${data.avg_risk_score}/100`} sub={`Median ${data.median_risk_score}`} />
            <MetricCard label="Anomalies Flagged" value={data.anomalies?.length ?? 0}
              sub={data.anomalies?.length ? "needs attention" : "all clear"} accent={!!data.anomalies?.length} />
          </div>

          {/* ── Anomaly callout ── */}
          {data.anomalies?.length > 0 && (
            <div className="rounded-xl p-5" style={{ background: "#EF444411", border: "1px solid #EF444433" }}>
              <div className="flex items-center gap-2 mb-2">
                <AlertTriangle size={15} style={{ color: "#EF4444" }} />
                <span className="font-semibold text-sm" style={{ color: "#EF4444" }}>Anomaly Callouts</span>
              </div>
              <p className="text-xs mb-3" style={{ color: "var(--text-muted)" }}>
                Contracts flagged because their risk score is materially above the corpus mean, or above the 70-point legal-review threshold.
              </p>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                {data.anomalies.map((a: any) => (
                  <div key={a.contract_id} className="flex items-center justify-between rounded-lg px-4 py-3"
                    style={{ background: "var(--bg-card)", border: "1px solid var(--border)" }}>
                    <div>
                      <p className="font-medium text-sm truncate max-w-xs" style={{ color: "var(--text-primary)" }}>{a.filename}</p>
                      <p className="text-xs" style={{ color: "var(--text-muted)" }}>{a.vendor ?? "unknown"} · #{a.contract_id}</p>
                    </div>
                    <div className="text-right ml-4 flex-shrink-0">
                      <p className="font-bold text-sm" style={{ color: "#EF4444" }}>{a.score}/100</p>
                      <p className="text-xs" style={{ color: "var(--text-muted)" }}>{a.reason}</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* ── Charts row ── */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <Card className="md:col-span-2">
              <h2 className="text-sm font-semibold mb-4" style={{ color: "var(--text-primary)" }}>Risk Score Distribution</h2>
              <ResponsiveContainer width="100%" height={240}>
                <BarChart
                  data={[
                    { label: "Low (0–30)",      count: data.score_buckets?.["0-30 (low)"] ?? 0 },
                    { label: "Moderate (31–60)", count: data.score_buckets?.["31-60 (moderate)"] ?? 0 },
                    { label: "High (61–100)",    count: data.score_buckets?.["61-100 (high)"] ?? 0 },
                  ]}
                  margin={{ top: 5, right: 10, left: -20, bottom: 5 }}
                >
                  <XAxis dataKey="label" tick={{ fill: "#7E89AC", fontSize: 11 }} />
                  <YAxis tick={{ fill: "#7E89AC", fontSize: 11 }} allowDecimals={false} />
                  <Tooltip {...ttStyle} />
                  <Bar dataKey="count" radius={[6, 6, 0, 0]}>
                    <Cell fill="#22C55E" />
                    <Cell fill="#F59E0B" />
                    <Cell fill="#EF4444" />
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
              <p className="text-xs text-center mt-1" style={{ color: "var(--text-muted)" }}>
                Avg {data.avg_risk_score} · Median {data.median_risk_score}
              </p>
            </Card>

            <Card>
              <h2 className="text-sm font-semibold mb-4" style={{ color: "var(--text-primary)" }}>By Status</h2>
              {Object.keys(data.by_status ?? {}).length > 0 ? (
                <ResponsiveContainer width="100%" height={240}>
                  <PieChart>
                    <Pie
                      data={Object.entries(data.by_status).map(([name, value], i) => ({
                        name, value, fill: STATUS_PALETTE[i % STATUS_PALETTE.length],
                      }))}
                      cx="50%" cy="45%" innerRadius={55} outerRadius={80}
                      dataKey="value" label={({ value }) => value} labelLine={false}
                    >
                      {Object.entries(data.by_status).map((_, i) => (
                        <Cell key={i} fill={STATUS_PALETTE[i % STATUS_PALETTE.length]} />
                      ))}
                    </Pie>
                    <Tooltip {...ttStyle} />
                    <Legend wrapperStyle={{ fontSize: 10, color: "#7E89AC" }} />
                  </PieChart>
                </ResponsiveContainer>
              ) : <p className="text-xs" style={{ color: "var(--text-muted)" }}>No status data yet.</p>}
            </Card>
          </div>

          {/* ── Vendor ranking + recurring risks ── */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <Card className="md:col-span-2">
              <h2 className="text-sm font-semibold mb-4" style={{ color: "var(--text-primary)" }}>Vendor Risk Ranking</h2>
              {data.vendor_ranking?.length > 0 ? (
                <div className="overflow-x-auto">
                  <table className="w-full text-xs">
                    <thead>
                      <tr style={{ color: "var(--text-muted)" }}>
                        {["Vendor", "Contracts", "Avg Score", "Max Score"].map(h => (
                          <th key={h} className="text-left py-2 pr-4 font-semibold uppercase tracking-wider"
                            style={{ borderBottom: "1px solid var(--border)" }}>{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {data.vendor_ranking.map((v: any, i: number) => (
                        <tr key={i} className="border-t" style={{ borderColor: "var(--border)" }}>
                          <td className="py-2 pr-4 font-medium" style={{ color: "var(--text-primary)" }}>{v.vendor}</td>
                          <td className="py-2 pr-4" style={{ color: "var(--text-muted)" }}>{v.n_contracts}</td>
                          <td className="py-2 pr-4 font-semibold" style={{
                            color: v.avg_score >= 70 ? "#EF4444" : v.avg_score >= 40 ? "#F59E0B" : "#22C55E"
                          }}>{v.avg_score}</td>
                          <td className="py-2" style={{ color: "var(--text-muted)" }}>{v.max_score}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : <p className="text-xs" style={{ color: "var(--text-muted)" }}>No vendor data yet.</p>}
            </Card>

            <Card>
              <h2 className="text-sm font-semibold mb-4" style={{ color: "var(--text-primary)" }}>Recurring Risky Clauses</h2>
              {data.top_recurring_risks?.length > 0 ? (
                <div className="flex flex-col gap-2.5">
                  {data.top_recurring_risks.slice(0, 8).map((r: any, i: number) => (
                    <div key={i} className="flex items-start gap-2.5">
                      <span className="text-sm flex-shrink-0 mt-0.5">
                        {r.max_severity === "Critical" ? "🔴" : r.max_severity === "High" ? "🟠" : r.max_severity === "Medium" ? "🟡" : "🟢"}
                      </span>
                      <div>
                        <p className="text-xs font-medium" style={{ color: "var(--text-primary)" }}>{r.risk}</p>
                        <p className="text-xs" style={{ color: "var(--text-muted)" }}>
                          {r.count} contract{r.count !== 1 ? "s" : ""}
                        </p>
                      </div>
                    </div>
                  ))}
                </div>
              ) : <p className="text-xs" style={{ color: "var(--text-muted)" }}>No risk findings yet.</p>}
            </Card>
          </div>

        </>)}
      </main>
    </>
  );
}
