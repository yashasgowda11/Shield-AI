"use client";

import { useRole } from "@/hooks/useRole";
import { ROLES, ROLE_META } from "@/lib/roles";

export default function Topbar({ title }: { title: string }) {
  const { role, setRole } = useRole();
  const meta = ROLE_META[role];

  return (
    <header
      className="h-14 flex items-center justify-between px-6 border-b shrink-0 z-10"
      style={{ background: "var(--bg-surface)", borderColor: "var(--border)" }}
    >
      <h1 className="text-sm font-semibold tracking-wide text-white">{title}</h1>

      <div className="flex items-center gap-3">
        <span className="text-xs" style={{ color: "var(--text-muted)" }}>Role:</span>
        <select
          value={role}
          onChange={(e) => setRole(e.target.value as typeof role)}
          className="text-xs font-medium rounded-lg px-3 py-1.5 border outline-none cursor-pointer"
          style={{
            background: "var(--bg-card)",
            borderColor: "var(--border)",
            color: meta.color.replace("text-", ""),
          }}
        >
          {ROLES.map((r) => (
            <option key={r} value={r}>
              {ROLE_META[r].icon} {r}
            </option>
          ))}
        </select>
      </div>
    </header>
  );
}
