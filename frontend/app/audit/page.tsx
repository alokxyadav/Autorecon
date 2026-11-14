"use client";

import { useEffect, useState } from "react";
import { api, AuditLogEntry, ApiError } from "@/lib/api";

const EVENT_STYLES: Record<string, string> = {
  match_attempt: "bg-ink-400/10 text-ink-700",
  ai_proposal: "bg-accent-100 text-accent-500",
  human_decision: "bg-success-500/10 text-success-500",
  system_error: "bg-danger-500/10 text-danger-500",
};

export default function AuditPage() {
  const [entries, setEntries] = useState<AuditLogEntry[]>([]);
  const [filter, setFilter] = useState<string>("all");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const data = await api.listAuditLog(filter === "all" ? {} : { event_type: filter });
      setEntries(data);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to load audit log.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filter]);

  return (
    <div className="mx-auto max-w-4xl">
      <h1 className="text-xl font-semibold text-ink-900">Audit Trail</h1>
      <p className="mt-1 text-sm text-ink-400">
        Every match attempt, AI proposal, and human decision — in order, nothing hidden.
      </p>

      <div className="mt-4 flex gap-2">
        {["all", "match_attempt", "ai_proposal", "human_decision", "system_error"].map((f) => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className={`rounded-md px-3 py-1.5 text-xs font-medium ${
              filter === f
                ? "bg-primary-700 text-white"
                : "border border-border bg-surface-100 text-ink-700 hover:bg-surface-0"
            }`}
          >
            {f.replace(/_/g, " ")}
          </button>
        ))}
      </div>

      {error && (
        <div className="mt-4 rounded-md border border-danger-500/30 bg-danger-500/10 px-4 py-3 text-sm text-danger-500">
          {error}
        </div>
      )}

      <div className="mt-6 space-y-3">
        {loading ? (
          <p className="text-sm text-ink-400">Loading audit trail…</p>
        ) : entries.length === 0 ? (
          <div className="rounded-lg border border-border bg-surface-0 p-8 text-center text-sm text-ink-400 shadow-card">
            No audit log entries yet — run a reconciliation to generate some.
          </div>
        ) : (
          entries.map((e) => (
            <div key={e.id} className="flex flex-col gap-2 rounded-lg border border-border bg-surface-0 p-4 shadow-card sm:flex-row sm:gap-4">
              <div className="text-xs text-ink-400 sm:w-36 sm:flex-shrink-0">
                {new Date(e.created_at).toLocaleString()}
              </div>
              <div className="flex-1">
                <div className="flex items-center gap-2">
                  <span
                    className={`rounded-md px-2 py-0.5 text-xs font-medium ${
                      EVENT_STYLES[e.event_type] || "bg-ink-400/10 text-ink-700"
                    }`}
                  >
                    {e.event_type.replace(/_/g, " ")}
                  </span>
                  <span className="text-xs text-ink-400">by {e.decided_by}</span>
                </div>
                <p className="mt-1.5 text-sm text-ink-900">{e.reasoning_text || "—"}</p>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
