"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import { useSidebar } from "@/lib/SidebarContext";
import {
  Upload, FileText, CheckSquare, BarChart2,
  Shield, MessageSquare, ClipboardList,
  Settings, Database, Home, FlaskConical, X, Users2,
} from "lucide-react";

const NAV = [
  { href: "/home",               label: "Home",            icon: Home },
  { href: "/upload",             label: "Upload",          icon: Upload },
  { href: "/contracts",          label: "Recent Uploads",  icon: FileText },
  { href: "/queue",              label: "Review Queue",    icon: CheckSquare },
  { href: "/dashboard/risk",     label: "Risk Dashboard",  icon: BarChart2 },
  { href: "/dashboard/security", label: "Security",        icon: Shield },
  { href: "/ask",                label: "Ask Shield AI",   icon: MessageSquare },
  { href: "/audit",              label: "Audit Log",       icon: ClipboardList },
  { href: "/scoring",            label: "Scoring Policy",  icon: Settings },
  { href: "/recovery",           label: "Data Recovery",   icon: Database },
  { href: "/samples",            label: "Sample Data",     icon: FlaskConical },
  { href: "/team",               label: "Meet the Team",   icon: Users2 },
];

export default function Sidebar() {
  const pathname = usePathname();
  const { open, setOpen } = useSidebar();

  return (
    <aside
      className={cn(
        // Shared
        "flex flex-col border-r shrink-0 transition-transform duration-300 ease-in-out",
        // Mobile: fixed full-height drawer slides in from left
        "fixed inset-y-0 left-0 z-40 w-64 h-full",
        // Desktop: relative sticky sidebar, always visible
        "md:relative md:w-56 md:sticky md:top-0 md:h-screen md:z-auto md:translate-x-0",
        // Mobile toggle
        open ? "translate-x-0 shadow-2xl" : "-translate-x-full",
      )}
      style={{ background: "var(--bg-surface)", borderColor: "var(--border)" }}
    >
      {/* ── Logo row + mobile close button ─────────────────────────── */}
      <div
        className="h-14 px-4 border-b flex items-center justify-between flex-shrink-0"
        style={{ borderColor: "var(--border)" }}
      >
        <Link
          href="/home"
          className="flex items-center gap-2 min-w-0"
          onClick={() => setOpen(false)}
        >
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src="/shield-ai-icon.svg"
            alt="Shield AI"
            width={26}
            height={26}
            className="flex-shrink-0"
          />
          <span
            className="font-semibold text-sm tracking-wide truncate"
            style={{ color: "var(--text-primary)" }}
          >
            Shield AI
          </span>
        </Link>

        {/* Close button — only visible on mobile */}
        <button
          onClick={() => setOpen(false)}
          className="md:hidden p-1.5 rounded-lg transition-colors hover:bg-white/10"
          aria-label="Close navigation"
          style={{ color: "var(--text-muted)" }}
        >
          <X size={18} />
        </button>
      </div>

      {/* ── Nav links ─────────────────────────────────────────────── */}
      <nav className="flex-1 py-3 overflow-y-auto">
        {NAV.map(({ href, label, icon: Icon }) => {
          const active = pathname === href || pathname.startsWith(href + "/");
          return (
            <Link
              key={href}
              href={href}
              onClick={() => setOpen(false)}
              className={cn(
                "flex items-center gap-3 mx-2 px-3 py-2.5 rounded-lg text-sm transition-colors mb-0.5",
                active ? "text-white font-medium" : "hover:text-white"
              )}
              style={
                active
                  ? { background: "var(--accent)", color: "#fff" }
                  : { color: "var(--text-muted)" }
              }
            >
              <Icon size={15} className="flex-shrink-0" />
              <span className="truncate">{label}</span>
            </Link>
          );
        })}
      </nav>

      {/* ── Footer ────────────────────────────────────────────────── */}
      <div
        className="px-4 py-3 border-t text-xs flex-shrink-0"
        style={{ borderColor: "var(--border)", color: "var(--text-muted)" }}
      >
        v2.0 · Next.js
      </div>
    </aside>
  );
}
