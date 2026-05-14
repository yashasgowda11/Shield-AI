"use client";

import { useState } from "react";
import { SidebarContext } from "@/lib/SidebarContext";
import Sidebar from "./Sidebar";

export default function LayoutShell({ children }: { children: React.ReactNode }) {
  const [open, setOpen] = useState(false);

  return (
    <SidebarContext.Provider value={{ open, setOpen }}>
      {/* ── Mobile backdrop ────────────────────────────────────────── */}
      {open && (
        <div
          className="fixed inset-0 z-30 bg-black/60 md:hidden"
          onClick={() => setOpen(false)}
        />
      )}

      {/* ── Sidebar (desktop sticky | mobile drawer) ──────────────── */}
      <Sidebar />

      {/* ── Main content area ──────────────────────────────────────── */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        {children}
      </div>
    </SidebarContext.Provider>
  );
}
