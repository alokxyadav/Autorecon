"use client";

import { useEffect } from "react";

export default function ErrorPage({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    // Log to the browser console at minimum so this doesn't fail silently —
    // in a real production deployment, wire this to an error-tracking
    // service (Sentry, etc.) instead of just console.error.
    console.error("AutoRecon frontend error:", error);
  }, [error]);

  return (
    <div className="mx-auto flex max-w-lg flex-col items-center px-4 py-16 text-center">
      <p className="text-4xl">⚠️</p>
      <h1 className="mt-4 text-xl font-semibold text-ink-900">Something went wrong</h1>
      <p className="mt-2 text-sm text-ink-400">
        This page hit an unexpected error. It&apos;s been logged. You can try again,
        or head back to the dashboard.
      </p>
      {error.digest && (
        <p className="mt-2 text-xs text-ink-400">Error reference: {error.digest}</p>
      )}
      <div className="mt-6 flex gap-3">
        <button
          onClick={reset}
          className="rounded-md bg-primary-700 px-4 py-2 text-sm font-medium text-white hover:bg-primary-900"
        >
          Try again
        </button>
        <a
          href="/"
          className="rounded-md border border-border px-4 py-2 text-sm font-medium text-ink-700 hover:bg-surface-50"
        >
          Back to dashboard
        </a>
      </div>
    </div>
  );
}
