export default function SummaryCard({
  label,
  value,
  tone = "default",
}: {
  label: string;
  value: string;
  tone?: "default" | "success" | "warning" | "danger";
}) {
  const toneClass = {
    default: "text-ink-900",
    success: "text-success-500",
    warning: "text-warning-500",
    danger: "text-danger-500",
  }[tone];

  return (
    <div className="rounded-lg border border-border bg-surface-0 p-4 shadow-card">
      <p className="text-xs font-medium uppercase tracking-wide text-ink-400">{label}</p>
      <p className={`mt-2 text-2xl font-semibold tabular-nums ${toneClass}`}>{value}</p>
    </div>
  );
}
