"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import {
  Upload, FileText, CheckSquare, BarChart2,
  Shield, MessageSquare, ClipboardList,
  Settings, Database, Home,
} from "lucide-react";

const NAV = [
  { href: "/home",           label: "Home",            icon: Home },
  { href: "/upload",         label: "Upload",          icon: Upload },
  { href: "/contracts",      label: "Recent Uploads",  icon: FileText },
  { href: "/queue",          label: "Review Queue",    icon: CheckSquare },
  { href: "/dashboard/risk", label: "Risk Dashboard",  icon: BarChart2 },
  { href: "/dashboard/security", label: "Security",    icon: Shield },
  { href: "/ask",            label: "Ask Shield AI",   icon: MessageSquare },
  { href: "/audit",          label: "Audit Log",       icon: ClipboardList },
  { href: "/scoring",        label: "Scoring Policy",  icon: Settings },
  { href: "/recovery",       label: "Data Recovery",   icon: Database },
];

export default function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="w-56 flex-shrink-0 flex flex-col h-screen border-r sticky top-0"
      style={{ background: "var(--bg-surface)", borderColor: "var(--border)" }}>

      {/* Logo */}
      <div className="h-14 px-5 border-b flex items-center" style={{ borderColor: "var(--border)" }}>
        <Link href="/home" className="flex items-center gap-2">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src="/shield-ai-icon.svg"
            alt="Shield AI"
            width={28}
            height={28}
            className="flex-shrink-0"
          />
          <span className="font-semibold text-sm tracking-wide" style={{ color: "var(--text-primary)" }}>
            Shield AI
          </span>
        </Link>
      </div>

      {/* Nav */}
      <nav className="flex-1 py-3 overflow-y-auto">
        {NAV.map(({ href, label, icon: Icon }) => {
          const active = pathname === href || pathname.startsWith(href + "/");
          return (
            <Link
              key={href}
              href={href}
              className={cn(
                "flex items-center gap-3 mx-2 px-3 py-2 rounded-lg text-sm transition-colors mb-0.5",
                active
                  ? "text-white font-medium"
                  : "hover:text-white"
              )}
              style={active
                ? { background: "var(--accent)", color: "#fff" }
                : { color: "var(--text-muted)" }
              }
            >
              <Icon size={15} />
              {label}
            </Link>
          );
        })}
      </nav>

      {/* Footer */}
      <div className="px-4 py-3 border-t text-xs" style={{ borderColor: "var(--border)", color: "var(--text-muted)" }}>
        v2.0 · Next.js
      </div>
    </aside>
  );
}
