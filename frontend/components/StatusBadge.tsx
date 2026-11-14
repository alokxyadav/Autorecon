const STATUS_STYLES: Record<string, { bg: string; text: string; dot: string; label: string }> = {
  matched: { bg: "bg-success-500/10", text: "text-success-500", dot: "bg-success-500", label: "Matched" },
  auto_resolved: { bg: "bg-success-500/10", text: "text-success-500", dot: "bg-success-500", label: "Auto-resolved" },
  approved: { bg: "bg-success-500/10", text: "text-success-500", dot: "bg-success-500", label: "Approved" },
  partial: { bg: "bg-warning-500/10", text: "text-warning-500", dot: "bg-warning-500", label: "Partial" },
  pending_settlement: { bg: "bg-warning-500/10", text: "text-warning-500", dot: "bg-warning-500", label: "Pending settlement" },
  pending_human_review: { bg: "bg-warning-500/10", text: "text-warning-500", dot: "bg-warning-500", label: "Needs review" },
  unmatched: { bg: "bg-danger-500/10", text: "text-danger-500", dot: "bg-danger-500", label: "Unmatched" },
  rejected: { bg: "bg-danger-500/10", text: "text-danger-500", dot: "bg-danger-500", label: "Rejected" },
};

export default function StatusBadge({ status }: { status: string }) {
  const style = STATUS_STYLES[status] || {
    bg: "bg-ink-400/10",
    text: "text-ink-400",
    dot: "bg-ink-400",
    label: status,
  };

  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-xs font-medium ${style.bg} ${style.text}`}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${style.dot}`} />
      {style.label}
    </span>
  );
}
