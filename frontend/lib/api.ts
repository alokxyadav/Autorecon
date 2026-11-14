const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
// Only set this if you've set AUTORECON_API_KEY on the backend (see
// .env.example). Note: NEXT_PUBLIC_* variables are bundled into the client
// JS and visible to anyone who opens dev tools — fine for a demo where you
// control both ends, but not a substitute for real per-user auth in a
// multi-tenant deployment (see PHASE_6_ROADMAP.md).
const API_KEY = process.env.NEXT_PUBLIC_API_KEY;

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

async function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const maxAttempts = 3;
  let lastError: unknown;

  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    try {
      const res = await fetch(`${API_BASE_URL}${path}`, {
        ...options,
        headers: {
          "Content-Type": "application/json",
          ...(API_KEY ? { "X-API-Key": API_KEY } : {}),
          ...(options.headers || {}),
        },
        cache: "no-store",
      });

      if (!res.ok) {
        let detail = res.statusText;
        try {
          const body = await res.json();
          detail = body.detail || detail;
        } catch {
          // response wasn't JSON — fall back to statusText
        }

        // Retry only on 502/503/504 — the specific signature of "the
        // backend is still starting up" right after a fresh deploy, or a
        // transient upstream hiccup. Never retry 4xx (client errors like
        // bad input or auth failures won't fix themselves on retry, and
        // retrying a mutating POST on a 4xx could be actively wrong).
        if ([502, 503, 504].includes(res.status) && attempt < maxAttempts) {
          lastError = new ApiError(detail, res.status);
          await sleep(500 * attempt);
          continue;
        }
        throw new ApiError(detail, res.status);
      }

      return res.json() as Promise<T>;
    } catch (err) {
      // Network-level failure (backend not listening yet at all, DNS not
      // resolved, connection refused) — the exact symptom of hitting the
      // frontend a few seconds before the backend has finished booting.
      if (err instanceof ApiError) throw err;
      lastError = err;
      if (attempt < maxAttempts) {
        await sleep(500 * attempt);
        continue;
      }
    }
  }

  throw lastError instanceof Error
    ? lastError
    : new ApiError("Request failed after retries.", 0);
}

export interface ReconciliationResult {
  id: number;
  transaction_id: number | null;
  settlement_id: number | null;
  bank_line_id: number | null;
  match_type: string;
  status: string;
  confidence: number;
  delta_amount: string;
  notes: string | null;
  ai_proposed_resolution: string | null;
  ai_confidence: number | null;
  reviewer_name: string | null;
  created_at: string;
  updated_at: string;
}

export interface AuditLogEntry {
  id: number;
  event_type: string;
  payload_json: string;
  reasoning_text: string | null;
  decided_by: string;
  created_at: string;
}

export interface ForecastResponse {
  lag_stats: { average_days: number; stdev_days: number; sample_size: number };
  daily_forecast: Array<{
    date: string;
    expected_amount: string;
    low_estimate: string;
    high_estimate: string;
  }>;
  anomalies: string[];
}

export const api = {
  seedDemoData: (numTransactions = 200) =>
    request<{ seeded: boolean; details: Record<string, number> }>(
      `/demo/seed?num_transactions=${numTransactions}`,
      { method: "POST" }
    ),

  runReconciliation: () =>
    request<{ summary: Record<string, unknown>; results_created: number }>(
      "/reconcile/run",
      { method: "POST" }
    ),

  analyzeItems: (reanalyze = false) =>
    request<{ items_analyzed: number; auto_resolved: number; pending_human_review: number }>(
      `/reconciliation/analyze?reanalyze=${reanalyze}`,
      { method: "POST" }
    ),

  listResults: (params: { status?: string; match_type?: string; limit?: number } = {}) => {
    const query = new URLSearchParams();
    if (params.status) query.set("status", params.status);
    if (params.match_type) query.set("match_type", params.match_type);
    if (params.limit) query.set("limit", String(params.limit));
    return request<ReconciliationResult[]>(`/reconciliation/results?${query.toString()}`);
  },

  approveResult: (id: number, reviewerName: string) =>
    request<ReconciliationResult>(`/reconciliation/${id}/approve`, {
      method: "POST",
      body: JSON.stringify({ reviewer_name: reviewerName }),
    }),

  rejectResult: (id: number, reviewerName: string) =>
    request<ReconciliationResult>(`/reconciliation/${id}/reject`, {
      method: "POST",
      body: JSON.stringify({ reviewer_name: reviewerName }),
    }),

  listAuditLog: (params: { event_type?: string; limit?: number } = {}) => {
    const query = new URLSearchParams();
    if (params.event_type) query.set("event_type", params.event_type);
    if (params.limit) query.set("limit", String(params.limit));
    return request<AuditLogEntry[]>(`/audit-log?${query.toString()}`);
  },

  getForecast: (horizonDays = 7) =>
    request<ForecastResponse>(`/forecast?horizon_days=${horizonDays}`),

  askQuestion: (question: string) =>
    request<{ answer: string; grounded_in: number[] }>("/query", {
      method: "POST",
      body: JSON.stringify({ question }),
    }),

  // Deliberately NOT a plain URL for a plain <a href> link — that would
  // skip the X-API-Key header entirely and silently 401 whenever
  // AUTORECON_API_KEY is set on the backend. Instead this fetches the CSV
  // with the same authenticated request() path as everything else, then
  // triggers a client-side download via a Blob and a synthetic link click.
  downloadResultsCsv: async (status?: string): Promise<void> => {
    const query = new URLSearchParams();
    if (status && status !== "all") query.set("status", status);
    const suffix = query.toString() ? `?${query.toString()}` : "";

    const res = await fetch(`${API_BASE_URL}/reconciliation/results/export${suffix}`, {
      headers: API_KEY ? { "X-API-Key": API_KEY } : {},
    });
    if (!res.ok) {
      throw new ApiError(`Export failed (${res.status})`, res.status);
    }
    const blob = await res.blob();
    const url = window.URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "reconciliation_results.csv";
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    window.URL.revokeObjectURL(url);
  },
};
