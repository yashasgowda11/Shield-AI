/** Role definitions — mirrors backend permission model. */

export const ROLES = [
  "Procurement Analyst",
  "Legal Reviewer",
  "Compliance Officer",
  "Executive",
  "Auditor",
] as const;

export type Role = (typeof ROLES)[number];

export const ROLE_META: Record<Role, { icon: string; description: string; color: string }> = {
  "Procurement Analyst": {
    icon: "📋",
    description: "Uploads contracts. Cannot approve.",
    color: "text-slate-300",
  },
  "Legal Reviewer": {
    icon: "⚖️",
    description: "Approves / rejects contracts in the legal-review queue.",
    color: "text-sky-400",
  },
  "Compliance Officer": {
    icon: "📊",
    description: "Approves / rejects contracts in the manager-review queue.",
    color: "text-amber-400",
  },
  Executive: {
    icon: "👔",
    description: "Read access + comments. Approve if escalated.",
    color: "text-purple-400",
  },
  Auditor: {
    icon: "🔍",
    description: "Read-only across all queues + audit logs.",
    color: "text-teal-400",
  },
};

export const PERMISSIONS: Record<Role, Set<string>> = {
  "Procurement Analyst": new Set(["upload", "view", "delete"]),
  "Legal Reviewer":      new Set(["view", "approve_legal", "reject", "comment", "escalate"]),
  "Compliance Officer":  new Set(["view", "approve_manager", "reject", "comment", "escalate"]),
  Executive:             new Set(["view", "comment"]),
  Auditor:               new Set(["view", "comment", "view_audit"]),
};

export function can(role: Role, action: string): boolean {
  return PERMISSIONS[role]?.has(action) ?? false;
}

/** Which status buckets each role sees in the Review Queue by default. */
export const ROLE_QUEUES: Record<Role, string[]> = {
  "Procurement Analyst": [],
  "Legal Reviewer":      ["legal_review"],
  "Compliance Officer":  ["manager_review"],
  Executive:             ["manager_review", "legal_review"],  // read-only + comment
  Auditor:               ["manager_review", "legal_review"],  // read-only + comment
};

/** Roles that can create assignments (escalate to another role). */
export const CAN_ASSIGN_ROLES: ReadonlySet<Role> = new Set([
  "Legal Reviewer",
  "Compliance Officer",
]);
