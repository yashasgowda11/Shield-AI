/**
 * Typed API client — wraps every Shield AI backend endpoint.
 * All functions throw on non-2xx responses so callers can use try/catch.
 */

// const BACKEND = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";
const BACKEND = "/api/backend";
// ── Generic fetch wrapper ─────────────────────────────────────────────────────

async function request<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const res = await fetch(`${BACKEND}${path}`, {
    headers: { "Content-Type": "application/json", ...options.headers },
    ...options,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API ${options.method ?? "GET"} ${path} → ${res.status}: ${text}`);
  }
  return res.json() as Promise<T>;
}

async function postForm<T>(path: string, data: Record<string, string>): Promise<T> {
  const body = new URLSearchParams(data);
  const res = await fetch(`${BACKEND}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`POST ${path} → ${res.status}: ${text}`);
  }
  return res.json() as Promise<T>;
}

// ── Types (mirrors backend Pydantic schemas) ──────────────────────────────────

export interface ContractSummary {
  id: number;
  filename: string;
  status: string;
  uploaded_at: string | null;
  n_clauses: number;
}

export interface ContractListResponse {
  total: number;
  limit: number;
  offset: number;
  items: ContractSummary[];
}

export interface Comment {
  id: number;
  actor: string;
  role: string;
  comment: string;
  comment_type: "comment" | "recommendation" | "escalation";
  created_at: string;
}

export interface Assignment {
  id: number;
  assigned_role: string;
  assigned_by: string;
  can_approve: boolean;
  note: string | null;
  active: boolean;
  assigned_at: string;
}

export interface Decision {
  id: number;
  recommendation: string;
  reasoning: string;
  reviewer_role: string;
  decided_at: string;
  scoring_details: ScoringDetails | null;
}

export interface ScoringDetails {
  composite_score: number;
  risk_score: number;
  compliance_average: number;
  quality_score: number;
  critical_findings: number;
  high_findings: number;
  decision: string;
  rationale: string[];
  required_actions: string[];
  triggered_rules: string[];
  sector: string;
  jurisdiction: string;
  financial_penalties: string[];
  jurisdiction_penalties: string[];
}

export interface ContractDetail extends ContractSummary {
  raw_text: string | null;
  clauses: Array<{ number: string; title: string; text: string }> | null;
  agent_outputs: Record<string, { output: Record<string, unknown>; confidence: number | null; prompt_hash: string | null; created_at: string }>;
  decisions: Decision[];
  security_events: Array<{ event_type: string; severity: string; details: Record<string, unknown> }>;
  comments: Comment[];
  assignments: Assignment[];
}

export interface BulkUploadResult {
  total: number;
  queued: number;
  duplicates: number;
  quarantined: number;
  errors: number;
  results: Array<{
    id?: number;
    status: string;
    filename: string;
    message?: string;
    n_clauses?: number;
    security_events?: Array<{ event_type: string; severity: string }>;
  }>;
}

export interface DashboardStats {
  total_contracts: number;
  by_status: Record<string, number>;
  avg_risk_score: number;
  compliance_pass_rate: number;
}

// ── Contracts ─────────────────────────────────────────────────────────────────

export const api = {
  contracts: {
    list: (params?: { status?: string; assigned_role?: string; limit?: number; offset?: number }) => {
      const q = new URLSearchParams();
      if (params?.status) q.set("status", params.status);
      if (params?.assigned_role) q.set("assigned_role", params.assigned_role);
      if (params?.limit !== undefined) q.set("limit", String(params.limit));
      if (params?.offset !== undefined) q.set("offset", String(params.offset));
      return request<ContractListResponse>(`/contracts/?${q}`);
    },

    get: (id: number) => request<ContractDetail>(`/contracts/${id}`),

    upload: async (file: File, actor: string) => {
      const form = new FormData();
      form.append("file", file);
      form.append("actor", actor);
      const res = await fetch(`${BACKEND}/contracts/upload`, { method: "POST", body: form });
      if (!res.ok) throw new Error(await res.text());
      return res.json();
    },

    bulkUpload: async (files: File[], actor: string): Promise<BulkUploadResult> => {
      const form = new FormData();
      files.forEach((f) => form.append("files", f));
      form.append("actor", actor);
      const res = await fetch(`${BACKEND}/contracts/bulk-upload`, { method: "POST", body: form });
      if (!res.ok) throw new Error(await res.text());
      return res.json();
    },

    decide: (id: number, decision: string, reasoning: string, actor: string, role: string) =>
      postForm(`/contracts/${id}/decide`, { decision, reasoning, actor, role }),

    addComment: (id: number, comment: string, role: string, actor: string, comment_type = "comment") =>
      postForm(`/contracts/${id}/comment`, { comment, role, actor, comment_type }),

    assign: (id: number, assigned_role: string, assigned_by: string, assigning_role: string, can_approve: boolean, note: string) =>
      postForm(`/contracts/${id}/assign`, {
        assigned_role,
        assigned_by,
        assigning_role,
        can_approve: String(can_approve),
        note,
      }),

    auditReport: (id: number) => request<Record<string, unknown>>(`/contracts/${id}/audit-report`),

    delete: (id: number, actor: string) =>
      request(`/contracts/${id}?actor=${encodeURIComponent(actor)}`, { method: "DELETE" }),
  },

  dashboard: {
    stats: () => request<DashboardStats>("/dashboard/stats"),
  },

  health: {
    check: () => request<{ status: string; lt?: { available: boolean } }>("/health"),
  },
};
