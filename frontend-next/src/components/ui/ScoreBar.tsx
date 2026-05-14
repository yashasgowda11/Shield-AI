import { scoreColor, scoreBand } from "@/lib/utils";

export default function ScoreBar({ score }: { score: number }) {
  const color = scoreColor(score);
  const band  = scoreBand(score);
  const pct   = Math.min(Math.max(score, 0), 100);

  const hexMap: Record<string, string> = {
    "text-green-400": "#4ade80",
    "text-amber-400": "#fbbf24",
    "text-sky-400":   "#38bdf8",
    "text-red-400":   "#f87171",
  };
  const hex = hexMap[color] ?? "#7E89AC";

  return (
    <div className="rounded-xl p-4" style={{ background: "var(--bg-card)", border: "1px solid var(--border)" }}>
      <div className="flex justify-between items-baseline mb-2">
        <span className="text-xs font-bold uppercase tracking-wider" style={{ color: "var(--text-muted)" }}>
          Composite Approval Score
        </span>
        <span className="text-xs font-semibold px-2 py-0.5 rounded-full border"
          style={{ color: hex, borderColor: hex + "55", background: hex + "11" }}>
          {band}
        </span>
      </div>
      <div className="flex items-center gap-3">
        <div className="flex-1 rounded-full h-2.5" style={{ background: "var(--border)" }}>
          <div
            className="h-2.5 rounded-full transition-all duration-500"
            style={{ width: `${pct}%`, background: hex }}
          />
        </div>
        <span className="text-2xl font-bold tabular-nums" style={{ color: hex }}>
          {score.toFixed(0)}
          <span className="text-sm font-normal" style={{ color: "var(--text-muted)" }}>/100</span>
        </span>
      </div>
    </div>
  );
}
