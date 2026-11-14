"use client";

import { useEffect, useState } from "react";
import { api, ReconciliationResult, ApiError } from "@/lib/api";
import StatusBadge from "@/components/StatusBadge";

export default function ReviewPage() {
  const [items, setItems] = useState<ReconciliationResult[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reviewerName, setReviewerName] = useState("");
  const [processingId, setProcessingId] = useState<number | null>(null);

  async function loadItems() {
    setLoading(true);
    setError(null);
    try {
      const data = await api.listResults({ status: "pending_human_review" });
      setItems(data);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to load review queue.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadItems();
  }, []);

  async function handleDecision(id: number, approve: boolean) {
    if (!reviewerName.trim()) {
      setError("Enter your name before approving or rejecting an item.");
      return;
    }
    setProcessingId(id);
    setError(null);
    try {
      if (approve) {
        await api.approveResult(id, reviewerName.trim());
      } else {
        await api.rejectResult(id, reviewerName.trim());
      }
      setItems((prev) => prev.filter((i) => i.id !== id));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to record decision.");
    } finally {
      setProcessingId(null);
    }
  }

  return (
    <div className="mx-auto max-w-4xl">
      <h1 className="text-xl font-semibold text-ink-900">Human Review Queue</h1>
      <p className="mt-1 text-sm text-ink-400">
        Items the policy gate did not auto-resolve — either the AI's confidence was too low, or the
        amount at stake exceeded the auto-approve ceiling.
      </p>

      <div className="mt-4 flex flex-col gap-2 sm:flex-row sm:items-center">
        <label className="text-sm text-ink-700">Reviewing as:</label>
        <input
          type="text"
          value={reviewerName}
          onChange={(e) => setReviewerName(e.target.value)}
          placeholder="Your name"
          maxLength={100}
          className="w-full rounded-md border border-border px-3 py-1.5 text-sm focus:border-accent-500 focus:outline-none sm:w-56"
        />
      </div>

      {error && (
        <div className="mt-4 rounded-md border border-danger-500/30 bg-danger-500/10 px-4 py-3 text-sm text-danger-500">
          {error}
        </div>
      )}

      <div className="mt-6 space-y-4">
        {loading ? (
          <p className="text-sm text-ink-400">Loading review queue…</p>
        ) : items.length === 0 ? (
          <div className="rounded-lg border border-border bg-surface-0 p-8 text-center text-sm text-ink-400 shadow-card">
            Nothing needs review right now.
          </div>
        ) : (
          items.map((item) => (
            <div key={item.id} className="rounded-lg border border-border bg-surface-0 p-4 shadow-card sm:p-5">
              <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                <div>
                  <p className="text-sm font-medium text-ink-900">Reconciliation result #{item.id}</p>
                  <div className="mt-1 flex items-center gap-2">
                    <StatusBadge status={item.status} />
                    <span className="text-xs text-ink-400 capitalize">{item.match_type}</span>
                  </div>
                </div>
                <p className="tabular-nums text-sm font-medium text-danger-500">
                  ₹{parseFloat(item.delta_amount).toFixed(2)}
                </p>
              </div>

              <div className="mt-3 rounded-md bg-surface-50 p-3 text-sm text-ink-700">
                <p className="text-xs font-medium text-ink-400">Deterministic engine notes</p>
                <p className="mt-1">{item.notes}</p>
              </div>

              {item.ai_proposed_resolution && (
                <div className="mt-3 rounded-md bg-accent-100 p-3 text-sm">
                  <p className="text-xs font-medium text-accent-500">AI proposed resolution</p>
                  <p className="mt-1 text-ink-900">{item.ai_proposed_resolution}</p>
                  <p className="mt-1 text-xs text-ink-400">
                    AI confidence: {item.ai_confidence ?? "—"} / 100
                  </p>
                </div>
              )}

              <div className="mt-4 flex flex-col gap-2 sm:flex-row sm:justify-end">
                <button
                  onClick={() => handleDecision(item.id, false)}
                  disabled={processingId === item.id}
                  className="rounded-md border border-danger-500 px-4 py-1.5 text-sm font-medium text-danger-500 hover:bg-danger-500/10 disabled:opacity-50"
                >
                  Reject
                </button>
                <button
                  onClick={() => handleDecision(item.id, true)}
                  disabled={processingId === item.id}
                  className="rounded-md bg-success-500 px-4 py-1.5 text-sm font-medium text-white hover:opacity-90 disabled:opacity-50"
                >
                  {processingId === item.id ? "Saving…" : "Approve"}
                </button>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
