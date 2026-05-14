"use client";

import { Menu } from "lucide-react";
import { useRole } from "@/hooks/useRole";
import { useSidebar } from "@/lib/SidebarContext";
import { ROLES, ROLE_META } from "@/lib/roles";

export default function Topbar({ title }: { title: string }) {
  const { role, setRole } = useRole();
  const { setOpen } = useSidebar();
  const meta = ROLE_META[role];

  return (
    <header
      className="h-14 flex items-center justify-between px-4 sm:px-6 border-b shrink-0 z-10 gap-3"
      style={{ background: "var(--bg-surface)", borderColor: "var(--border)" }}
    >
      {/* Left: hamburger (mobile) + page title */}
      <div className="flex items-center gap-3 min-w-0">
        {/* Hamburger — hidden on desktop */}
        <button
          onClick={() => setOpen(true)}
          className="md:hidden p-1.5 rounded-lg transition-colors hover:bg-white/10 flex-shrink-0"
          aria-label="Open navigation"
          style={{ color: "var(--text-muted)" }}
        >
          <Menu size={20} />
        </button>

        <h1 className="text-sm font-semibold tracking-wide text-white truncate">
          {title}
        </h1>
      </div>

      {/* Right: role selector */}
      <div className="flex items-center gap-2 flex-shrink-0">
        <span className="text-xs hidden sm:block" style={{ color: "var(--text-muted)" }}>
          Role:
        </span>
        <select
          value={role}
          onChange={(e) => setRole(e.target.value as typeof role)}
          className="text-xs font-medium rounded-lg px-2 sm:px-3 py-1.5 border outline-none cursor-pointer max-w-[140px] sm:max-w-none"
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
