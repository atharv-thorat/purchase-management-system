import { Icon } from "@/components/Icon";
import { StatusBadge } from "@/components/StatusBadge";
import { formatDateTime, formatINR, humanize, ROLE_LABELS } from "@/lib/format";
import { DOT_CLASSES, toneOf } from "@/lib/status";
import type { TimelineEntry } from "@/types/api";

// Display only: each audit row is described from what it records (action, level in details,
// from/to status). The audit data itself is unchanged.

const ENTITY_LABEL = { PURCHASE_REQUEST: "PR", PURCHASE_ORDER: "PO", INVOICE: "Invoice" } as const;

/** Steps the system performs as a consequence of someone else's action (DESIGN.md §3). */
const SYSTEM_STEPS: Record<string, string[]> = {
  PURCHASE_REQUEST: ["PO_CANCELLED"],
  PURCHASE_ORDER: ["CLOSED"],
  INVOICE: ["MATCHED", "MISMATCHED"],
};

function approvalLevel(entry: TimelineEntry): string {
  const level = entry.details?.level ?? (entry.from_status === "PENDING_FINANCE" ? "FINANCE" : "DEPT_HEAD");
  return level === "FINANCE" ? "finance" : "department head";
}

function title(entry: TimelineEntry): string {
  const { entity_type: type, action } = entry;
  if (type === "PURCHASE_REQUEST") {
    switch (action) {
      case "CREATED": return "Request created";
      case "EDITED": return "Request edited";
      case "DELETED": return "Draft deleted";
      case "SUBMITTED": return "Submitted for approval";
      case "RESUBMITTED": return "Resubmitted after changes";
      case "APPROVED": return `Approved by ${approvalLevel(entry)}`;
      case "REJECTED": return `Rejected by ${approvalLevel(entry)}`;
      case "PO_CREATED": return "Purchase order created";
      case "PO_CANCELLED": return "Reopened — purchase order cancelled";
    }
  }
  if (type === "PURCHASE_ORDER") {
    switch (action) {
      case "ISSUED": return "Purchase order issued";
      case "GRN_RECORDED": return "Goods received";
      case "CANCELLED": return "Purchase order cancelled";
      case "SHORT_CLOSED": return "Short-closed";
      case "CLOSED": return "Closed automatically";
    }
  }
  if (type === "INVOICE") {
    switch (action) {
      case "ENTERED": return "Invoice entered";
      case "MATCHED": return "Three-way match passed";
      case "MISMATCHED": return "Three-way match failed";
      case "REMATCH_REQUESTED": return "Rematch requested";
      case "REJECTED": return "Invoice rejected";
      case "PAYMENT_RECORDED": return entry.to_status === "PAID" ? "Payment recorded — paid in full" : "Payment recorded";
    }
  }
  return humanize(action);
}

/** Human-readable extras from the row's details: comment, reason, GRN number, payment… */
function detailText(entry: TimelineEntry): string | null {
  const d = entry.details ?? {};
  const parts: string[] = [];
  if (typeof d.comment === "string") parts.push(`“${d.comment}”`);
  if (typeof d.reason === "string") parts.push(`“${d.reason}”`);
  if (typeof d.grn_number === "string") parts.push(d.grn_number);
  if (typeof d.po_number === "string" && entry.action !== "ENTERED") parts.push(d.po_number);
  if (typeof d.supplier === "string") parts.push(`Supplier: ${d.supplier}`);
  if (typeof d.amount === "string") parts.push(`${formatINR(d.amount)} via ${d.mode}${d.reference_no ? ` (${d.reference_no})` : ""}`);
  if (typeof d.balance === "string" && d.balance !== "0.00") parts.push(`balance ${formatINR(d.balance)}`);
  if (d.auto === true && typeof d.trigger === "string") parts.push(`after the ${d.trigger}`);
  if (d.over_budget === true) parts.push("over budget — approved with the warning shown");
  if (Array.isArray(d.mismatches)) parts.push(...(d.mismatches as string[]));
  return parts.length ? parts.join(" · ") : null;
}

/** [from] → [to], with the old status muted. Creation shows only the new status. */
function Transition({ from, to }: { from: string | null; to: string | null }) {
  if (!from && !to) return null;
  if (from && from === to) {
    return (
      <span className="inline-flex items-center gap-2">
        <StatusBadge status={to!} size="sm" muted /><span className="text-xs text-slate-400">no status change</span>
      </span>
    );
  }
  return (
    <span className="inline-flex flex-wrap items-center gap-1.5">
      {from && (
        <>
          <StatusBadge status={from} size="sm" muted />
          <span className="text-slate-400" aria-hidden="true">→</span>
          <span className="sr-only">changed to</span>
        </>
      )}
      {to ? <StatusBadge status={to} size="sm" /> : <span className="text-xs text-slate-500">removed</span>}
    </span>
  );
}

export function StatusTimeline({ entries, showEntity = false }: { entries: TimelineEntry[]; showEntity?: boolean }) {
  if (!entries.length) return <p className="text-sm text-slate-500">No history yet.</p>;
  return (
    <ol className="relative space-y-5 before:absolute before:bottom-2 before:left-[7px] before:top-2 before:w-px before:bg-slate-200">
      {entries.map((entry, i) => {
        const system = SYSTEM_STEPS[entry.entity_type]?.includes(entry.action) ?? false;
        const extra = detailText(entry);
        return (
          <li key={i} className="relative flex gap-4" data-testid="timeline-entry">
            <span className={`relative z-10 mt-1.5 h-[15px] w-[15px] shrink-0 rounded-full ring-4 ring-white ${DOT_CLASSES[toneOf(entry.to_status ?? entry.from_status)]}`} />
            <div className="min-w-0 flex-1">
              <p className="flex flex-wrap items-baseline gap-x-2">
                <span className="font-medium text-slate-900">{title(entry)}</span>
                {showEntity && entry.reference && (
                  <span className="text-sm text-slate-500">{ENTITY_LABEL[entry.entity_type]} {entry.reference}</span>
                )}
              </p>
              <div className="mt-1"><Transition from={entry.from_status} to={entry.to_status} /></div>
              <p className="mt-1 flex flex-wrap items-center gap-x-1 text-sm text-slate-500">
                {formatDateTime(entry.at)} ·
                {system ? (
                  <span className="inline-flex items-center gap-1 font-medium text-slate-600"><Icon name="cog" className="h-3.5 w-3.5" />System</span>
                ) : entry.user ? (
                  <span>{entry.user.name} <span className="text-slate-400">({ROLE_LABELS[entry.user.role]})</span></span>
                ) : <span>System</span>}
              </p>
              {extra && <p className="mt-1 text-sm text-slate-700">{extra}</p>}
            </div>
          </li>
        );
      })}
    </ol>
  );
}
