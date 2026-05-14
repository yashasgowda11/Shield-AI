import { statusMeta } from "@/lib/utils";
import { cn } from "@/lib/utils";

export default function StatusPill({ status }: { status: string }) {
  const { label, color, bg } = statusMeta(status);
  return (
    <span className={cn("inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium", color, bg)}>
      {label}
    </span>
  );
}
