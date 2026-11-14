"use client";

import { useState } from "react";
import { api, ApiError } from "@/lib/api";

export default function AskPage() {
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<string | null>(null);
  const [groundedIn, setGroundedIn] = useState<number[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleAsk() {
    if (!question.trim()) return;
    setLoading(true);
    setError(null);
    setAnswer(null);
    try {
      const result = await api.askQuestion(question.trim());
      setAnswer(result.answer);
      setGroundedIn(result.grounded_in);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to get an answer.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="mx-auto max-w-3xl">
      <h1 className="text-xl font-semibold text-ink-900">Ask AutoRecon</h1>
      <p className="mt-1 text-sm text-ink-400">
        Ask about a specific order or the reconciliation state. Answers are grounded only in the
        audit trail — if there&apos;s no relevant entry, it will say so instead of guessing.
      </p>

      <div className="mt-6 flex flex-col gap-2 sm:flex-row">
        <input
          type="text"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleAsk()}
          placeholder="Why didn't order_00042 reconcile?"
          maxLength={500}
          className="flex-1 rounded-md border border-border px-4 py-2.5 text-sm focus:border-accent-500 focus:outline-none"
        />
        <button
          onClick={handleAsk}
          disabled={loading}
          className="rounded-md bg-primary-700 px-5 py-2.5 text-sm font-medium text-white hover:bg-primary-900 disabled:opacity-50"
        >
          {loading ? "Asking…" : "Ask"}
        </button>
      </div>

      {error && (
        <div className="mt-4 rounded-md border border-danger-500/30 bg-danger-500/10 px-4 py-3 text-sm text-danger-500">
          {error}
        </div>
      )}

      {answer && (
        <div className="mt-6 rounded-lg border border-border bg-surface-0 p-5 shadow-card">
          <p className="text-xs font-medium text-accent-500">Answer</p>
          <p className="mt-2 text-sm text-ink-900">{answer}</p>
          {groundedIn.length > 0 && (
            <p className="mt-3 text-xs text-ink-400">
              Grounded in audit log entries: {groundedIn.map((id) => `#${id}`).join(", ")}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
