"use client";

import { useEffect, useState } from "react";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const APP_VERSION = "v0.5.0";

type BackendStatus = "checking" | "online" | "offline";

export default function Footer() {
  const [status, setStatus] = useState<BackendStatus>("checking");

  useEffect(() => {
    let cancelled = false;

    async function checkHealth() {
      try {
        // Deliberately a plain fetch, not the shared api.ts request() helper
        // — that helper retries 3x with backoff, which is the right
        // behavior for actual data calls but would make a background status
        // indicator take up to several seconds to report "offline" instead
        // of failing fast, since this check runs silently and repeatedly.
        const res = await fetch(`${API_BASE_URL}/health`, { cache: "no-store" });
        if (!cancelled) setStatus(res.ok ? "online" : "offline");
      } catch {
        if (!cancelled) setStatus("offline");
      }
    }

    checkHealth();
    const interval = setInterval(checkHealth, 30_000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, []);

  const statusConfig: Record<BackendStatus, { color: string; label: string }> = {
    checking: { color: "bg-ink-400", label: "Checking backend…" },
    online: { color: "bg-success-500", label: "Backend connected" },
    offline: { color: "bg-danger-500", label: "Backend unavailable" },
  };
  const { color, label } = statusConfig[status];

  return (
    <footer className="mt-8 border-t border-border px-4 py-4 sm:px-8">
      <div className="flex flex-col gap-3 text-xs text-ink-400 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-4">
          <span>
            © 2026 AutoRecon — built for the{" "}
            <span className="font-medium text-ink-700">Razorpay AI Buildathon</span>
          </span>
          <span className="hidden text-ink-400 sm:inline">·</span>
          <span className="hidden sm:inline">{APP_VERSION}</span>
        </div>
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-1.5">
            <span className={`h-1.5 w-1.5 rounded-full ${color}`} />
            <span>{label}</span>
          </div>
          <a
            href={`${API_BASE_URL}/docs`}
            target="_blank"
            rel="noopener noreferrer"
            className="hover:text-accent-500"
          >
            API docs
          </a>
        </div>
      </div>
    </footer>
  );
}
