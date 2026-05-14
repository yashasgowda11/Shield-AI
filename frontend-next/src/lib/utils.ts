import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

/** Merge Tailwind classes safely. */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/** Map contract status → display label + color token. */
export function statusMeta(status: string): { label: string; color: string; bg: string } {
  const map: Record<string, { label: string; color: string; bg: string }> = {
    uploaded:          { label: "Uploaded",        color: "text-slate-400",  bg: "bg-slate-400/10" },
    extracting:        { label: "Extracting…",      color: "text-yellow-400", bg: "bg-yellow-400/10" },
    extracted:         { label: "Processing…",      color: "text-yellow-400", bg: "bg-yellow-400/10" },
    processed:         { label: "Processed",        color: "text-blue-400",   bg: "bg-blue-400/10" },
    quarantined:       { label: "Quarantined 🚨",   color: "text-red-400",    bg: "bg-red-400/10" },
    pipeline_failed:   { label: "Pipeline failed",  color: "text-red-500",    bg: "bg-red-500/10" },
    extraction_failed: { label: "Extraction failed",color: "text-red-500",    bg: "bg-red-500/10" },
    manager_review:    { label: "Manager Review",   color: "text-amber-400",  bg: "bg-amber-400/10" },
    legal_review:      { label: "Legal Review",     color: "text-sky-400",    bg: "bg-sky-400/10" },
    approved:          { label: "Approved ✅",       color: "text-green-400",  bg: "bg-green-400/10" },
    rejected:          { label: "Rejected ❌",       color: "text-red-400",    bg: "bg-red-400/10" },
  };
  return map[status] ?? { label: status, color: "text-slate-400", bg: "bg-slate-400/10" };
}

/** Map composite score → colour. */
export function scoreColor(score: number): string {
  if (score >= 82) return "text-green-400";
  if (score >= 63) return "text-amber-400";
  if (score >= 38) return "text-sky-400";
  return "text-red-400";
}

export function scoreBand(score: number): string {
  if (score >= 82) return "AUTO APPROVE";
  if (score >= 63) return "MANAGER REVIEW";
  if (score >= 38) return "LEGAL REVIEW";
  return "REJECT";
}

/** Format ISO timestamp to "May 13, 2026 14:32" */
export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("en-US", {
    month: "short", day: "numeric", year: "numeric",
    hour: "2-digit", minute: "2-digit",
  });
}
