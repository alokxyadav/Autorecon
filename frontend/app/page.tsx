"use client";

import { useEffect, useState } from "react";
import { api, ReconciliationResult, ForecastResponse, ApiError } from "@/lib/api";
import StatusBadge from "@/components/StatusBadge";
import SummaryCard from "@/components/SummaryCard";

const STATUS_FILTERS = [
  "all",
  "matched",
  "partial",
  "unmatched",
  "pending_settlement",
  "pending_human_review",
  "auto_resolved",
];

export default function DashboardPage() {
  const [results, setResults] = useState<ReconciliationResult[]>([]);
  const [selected, setSelected] = useState<ReconciliationResult | null>(null);
  const [statusFilter, setStatusFilter] = useState("all");
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [forecast, setForecast] = useState<ForecastResponse | null>(null);
  const [forecastError, setForecastError] = useState<string | null>(null);

  async function loadForecast() {
    setForecastError(null);
    try {
      const data = await api.getForecast(7);
      setForecast(data);
    } catch (e) {
      // Forecast is a secondary feature — a failure here shouldn't block the
      // rest of the dashboard from working, just show a small inline note.
      setForecastError(e instanceof ApiError ? e.message : "Forecast unavailable.");
    }
  }

  async function loadResults() {
    setLoading(true);
    setError(null);
    try {
      const data = await api.listResults(
        statusFilter === "all" ? {} : { status: statusFilter }
      );
      setResults(data);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to load reconciliation results.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadResults();
    loadForecast();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [statusFilter]);

  async function handleSeedAndRun() {
    setActionLoading("seed");
    setError(null);
    try {
      await api.seedDemoData(200);
      await api.runReconciliation();
      await loadResults();
      await loadForecast();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to seed/run reconciliation.");
    } finally {
      setActionLoading(null);
    }
  }

  async function handleAnalyze() {
    setActionLoading("analyze");
    setError(null);
    try {
      await api.analyzeItems();
      await loadResults();
      await loadForecast();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to run AI analysis.");
    } finally {
      setActionLoading(null);
    }
  }

  async function handleExport() {
    setActionLoading("export");
    setError(null);
    try {
      await api.downloadResultsCsv(statusFilter);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to export CSV.");
    } finally {
      setActionLoading(null);
    }
  }

  const matchedCount = results.filter((r) => r.status === "matched" || r.status === "auto_resolved" || r.status === "approved").length;
  const matchRate = results.length > 0 ? ((matchedCount / results.length) * 100).toFixed(1) : "0.0";
  const unmatchedValue = results
    .filter((r) => r.status === "unmatched")
    .reduce((sum, r) => sum + parseFloat(r.delta_amount), 0);
  const pendingReviewCount = results.filter((r) => r.status === "pending_human_review").length;

  return (
    <div className="mx-auto max-w-6xl">
      <div className="mb-6 rounded-lg border border-accent-500/30 bg-accent-100 p-4">
        <p className="text-sm text-ink-900">
          <span className="font-semibold">The problem:</span> finance teams reconcile
          payments, settlements, and bank statements by hand in spreadsheets — discrepancies
          go unnoticed for weeks. AutoRecon matches them automatically, explains every
          mismatch in plain language, and never lets an AI touch the ledger without a human
          sign-off.
        </p>
        <p className="mt-1.5 text-xs text-ink-400">
          See the <span className="font-medium">Audit Trail</span> tab for the full
          decision history, or the project README for the complete before/after breakdown.
        </p>
      </div>

      <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-xl font-semibold text-ink-900">Reconciliation Dashboard</h1>
          <p className="mt-1 text-sm text-ink-400">
            Deterministic matching results across transactions, settlements, and bank statements.
          </p>
        </div>
        <div className="flex flex-col gap-2 sm:flex-row">
          <button
            onClick={handleSeedAndRun}
            disabled={actionLoading !== null}
            className="rounded-md bg-primary-700 px-4 py-2 text-sm font-medium text-white hover:bg-primary-900 disabled:opacity-50"
          >
            {actionLoading === "seed" ? "Running…" : "Seed data & reconcile"}
          </button>
          <button
            onClick={handleAnalyze}
            disabled={actionLoading !== null}
            className="rounded-md border border-accent-500 px-4 py-2 text-sm font-medium text-accent-500 hover:bg-accent-100 disabled:opacity-50"
          >
            {actionLoading === "analyze" ? "Analyzing…" : "Run AI analysis"}
          </button>
          <button
            onClick={handleExport}
            disabled={actionLoading !== null}
            className="rounded-md border border-border px-4 py-2 text-sm font-medium text-ink-700 hover:bg-surface-50 disabled:opacity-50"
          >
            {actionLoading === "export" ? "Exporting…" : "Export CSV"}
          </button>
        </div>
      </div>

      {error && (
        <div className="mb-4 rounded-md border border-danger-500/30 bg-danger-500/10 px-4 py-3 text-sm text-danger-500">
          {error}
        </div>
      )}

      <div className="mb-6 grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-4">
        <SummaryCard label="Match rate" value={`${matchRate}%`} tone="success" />
        <SummaryCard label="Unmatched value" value={`₹${unmatchedValue.toFixed(2)}`} tone="danger" />
        <SummaryCard label="Pending review" value={String(pendingReviewCount)} tone="warning" />
        <SummaryCard label="Total results" value={String(results.length)} />
      </div>

      <div className="mb-6 rounded-lg border border-border bg-surface-0 p-4 shadow-card sm:p-5">
        <h2 className="text-sm font-semibold text-ink-900">7-Day Cash-Flow Forecast</h2>
        <p className="mt-1 text-xs text-ink-400">
          Built only from reconciled data — never raw, unverified transactions.
        </p>
        {forecastError ? (
          <p className="mt-3 text-sm text-ink-400">{forecastError}</p>
        ) : !forecast ? (
          <p className="mt-3 text-sm text-ink-400">Loading forecast…</p>
        ) : forecast.daily_forecast.length === 0 ? (
          <p className="mt-3 text-sm text-ink-400">
            No pending settlements land within the next 7 days.
          </p>
        ) : (
          <>
            <div className="mt-3 overflow-x-auto">
              <table className="w-full min-w-[420px] text-sm">
                <thead className="text-left text-xs uppercase text-ink-400">
                  <tr>
                    <th className="py-1">Date</th>
                    <th className="py-1 text-right">Low</th>
                    <th className="py-1 text-right">Expected</th>
                    <th className="py-1 text-right">High</th>
                  </tr>
                </thead>
                <tbody>
                  {forecast.daily_forecast.map((d) => (
                    <tr key={d.date} className="border-t border-border">
                      <td className="py-1.5 text-ink-700">{d.date}</td>
                      <td className="py-1.5 text-right tabular-nums text-ink-400">
                        ₹{parseFloat(d.low_estimate).toFixed(2)}
                      </td>
                      <td className="py-1.5 text-right tabular-nums font-medium text-ink-900">
                        ₹{parseFloat(d.expected_amount).toFixed(2)}
                      </td>
                      <td className="py-1.5 text-right tabular-nums text-ink-400">
                        ₹{parseFloat(d.high_estimate).toFixed(2)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="mt-3 text-xs text-ink-400">
              Based on {forecast.lag_stats.sample_size} historical settlements, averaging{" "}
              {forecast.lag_stats.average_days.toFixed(1)} days to settle.
            </p>
            {forecast.anomalies.length > 0 && (
              <div className="mt-3 rounded-md bg-warning-500/10 p-3">
                {forecast.anomalies.map((a, i) => (
                  <p key={i} className="text-xs text-warning-500">
                    ⚠ {a}
                  </p>
                ))}
              </div>
            )}
          </>
        )}
      </div>

      <div className="mb-4 flex flex-wrap gap-2">
        {STATUS_FILTERS.map((s) => (
          <button
            key={s}
            onClick={() => setStatusFilter(s)}
            className={`rounded-md px-3 py-1.5 text-xs font-medium ${
              statusFilter === s
                ? "bg-primary-700 text-white"
                : "bg-surface-100 text-ink-700 hover:bg-surface-0 border border-border"
            }`}
          >
            {s.replace(/_/g, " ")}
          </button>
        ))}
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <div className="overflow-hidden rounded-lg border border-border bg-surface-0 shadow-card lg:col-span-2">
          {loading ? (
            <div className="p-8 text-center text-sm text-ink-400">Loading reconciliation results…</div>
          ) : results.length === 0 ? (
            <div className="p-8 text-center text-sm text-ink-400">
              This is normally where a finance team spends hours cross-checking spreadsheets by
              hand. Click &ldquo;Seed data &amp; reconcile&rdquo; above to see AutoRecon do it in
              seconds.
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[560px] text-sm">
                <thead className="border-b border-border bg-surface-50 text-left text-xs uppercase text-ink-400">
                  <tr>
                    <th className="px-4 py-3">ID</th>
                    <th className="px-4 py-3">Match type</th>
                    <th className="px-4 py-3">Status</th>
                    <th className="px-4 py-3 text-right">Delta (₹)</th>
                    <th className="px-4 py-3 text-right">Confidence</th>
                  </tr>
                </thead>
                <tbody>
                  {results.map((r) => (
                    <tr
                      key={r.id}
                      onClick={() => setSelected(r)}
                      className={`cursor-pointer border-b border-border last:border-0 hover:bg-surface-50 ${
                        selected?.id === r.id ? "bg-accent-100" : ""
                      }`}
                    >
                      <td className="px-4 py-3 text-ink-700">#{r.id}</td>
                      <td className="px-4 py-3 capitalize text-ink-700">{r.match_type}</td>
                      <td className="px-4 py-3">
                        <StatusBadge status={r.status} />
                      </td>
                      <td className="px-4 py-3 text-right tabular-nums text-ink-900">
                        {parseFloat(r.delta_amount).toFixed(2)}
                      </td>
                      <td className="px-4 py-3 text-right tabular-nums text-ink-700">{r.confidence}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        <div className="rounded-lg border border-border bg-surface-0 p-5 shadow-card">
          <h2 className="text-sm font-semibold text-ink-900">Details</h2>
          {selected ? (
            <div className="mt-3 space-y-3 text-sm">
              <div>
                <p className="text-xs text-ink-400">Status</p>
                <StatusBadge status={selected.status} />
              </div>
              <div>
                <p className="text-xs text-ink-400">System notes</p>
                <p className="mt-1 text-ink-700">{selected.notes || "—"}</p>
              </div>
              {selected.ai_proposed_resolution && (
                <div className="rounded-md bg-accent-100 p-3">
                  <p className="text-xs font-medium text-accent-500">AI proposed</p>
                  <p className="mt-1 text-ink-900">{selected.ai_proposed_resolution}</p>
                  <p className="mt-1 text-xs text-ink-400">
                    Confidence: {selected.ai_confidence ?? "—"}
                  </p>
                </div>
              )}
              {selected.reviewer_name && (
                <div>
                  <p className="text-xs text-ink-400">Reviewed by</p>
                  <p className="mt-1 text-ink-700">{selected.reviewer_name}</p>
                </div>
              )}
            </div>
          ) : (
            <p className="mt-3 text-sm text-ink-400">Select a row to see details.</p>
          )}
        </div>
      </div>
    </div>
  );
}
