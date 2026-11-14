import Link from "next/link";

export default function NotFound() {
  return (
    <div className="mx-auto flex max-w-lg flex-col items-center px-4 py-16 text-center">
      <span className="flex h-12 w-12 items-center justify-center rounded-lg bg-accent-500 text-lg font-bold text-white">
        AR
      </span>
      <p className="mt-6 text-6xl font-semibold text-primary-700">404</p>
      <h1 className="mt-4 text-xl font-semibold text-ink-900">Page not found</h1>
      <p className="mt-2 text-sm text-ink-400">
        This page doesn&apos;t exist, or the link may be out of date. Here are the
        pages that do:
      </p>
      <div className="mt-6 grid w-full grid-cols-2 gap-3">
        <Link
          href="/"
          className="rounded-md border border-border bg-surface-0 px-4 py-3 text-sm font-medium text-ink-700 shadow-card hover:bg-surface-50"
        >
          Dashboard
        </Link>
        <Link
          href="/review"
          className="rounded-md border border-border bg-surface-0 px-4 py-3 text-sm font-medium text-ink-700 shadow-card hover:bg-surface-50"
        >
          Review Queue
        </Link>
        <Link
          href="/audit"
          className="rounded-md border border-border bg-surface-0 px-4 py-3 text-sm font-medium text-ink-700 shadow-card hover:bg-surface-50"
        >
          Audit Trail
        </Link>
        <Link
          href="/ask"
          className="rounded-md border border-border bg-surface-0 px-4 py-3 text-sm font-medium text-ink-700 shadow-card hover:bg-surface-50"
        >
          Ask AutoRecon
        </Link>
      </div>
    </div>
  );
}
