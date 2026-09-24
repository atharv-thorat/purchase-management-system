import { StatusBadge } from "@/components/StatusBadge";
import { formatDateTime, formatINR, humanize, ROLE_LABELS } from "@/lib/format";
import { DOT_CLASSES, toneOf } from "@/lib/status";
import type { TimelineEntry } from "@/types/api";

const ENTITY_LABEL = { PURCHASE_REQUEST: "PR", PURCHASE_ORDER: "PO", INVOICE: "Invoice" } as const;

/** Human-readable extras from an audit row's details (reason, comment, GRN number, payment…). */
function detailText(entry: TimelineEntry): string | null {
  const d = entry.details ?? {};
  const parts: string[] = [];
  if (typeof d.comment === "string") parts.push(`“${d.comment}”`);
  if (typeof d.reason === "string") parts.push(`“${d.reason}”`);
  if (typeof d.grn_number === "string") parts.push(d.grn_number);
  if (typeof d.po_number === "string" && entry.action !== "ENTERED") parts.push(d.po_number);
  if (typeof d.supplier === "string") parts.push(`Supplier: ${d.supplier}`);
  if (typeof d.amount === "string") parts.push(`${formatINR(d.amount)} via ${d.mode}${d.reference_no ? ` (${d.reference_no})` : ""}`);
  if (typeof d.balance === "string") parts.push(`balance ${formatINR(d.balance)}`);
  if (d.auto === true) parts.push(`automatic, after ${d.trigger}`);
  if (d.over_budget === true) parts.push("over budget — approved with warning");
  if (Array.isArray(d.mismatches)) parts.push(...(d.mismatches as string[]));
  return parts.length ? parts.join(" · ") : null;
}

export function StatusTimeline({ entries, showEntity = false }: { entries: TimelineEntry[]; showEntity?: boolean }) {
  if (!entries.length) return <p className="text-sm text-slate-500">No history yet.</p>;
  return (
    <ol className="relative space-y-5 before:absolute before:bottom-2 before:left-[7px] before:top-2 before:w-px before:bg-slate-200">
      {entries.map((entry, i) => {
        const extra = detailText(entry);
        return (
          <li key={i} className="relative flex gap-4 pl-0">
            <span className={`relative z-10 mt-1.5 h-[15px] w-[15px] shrink-0 rounded-full ring-4 ring-white ${DOT_CLASSES[toneOf(entry.to_status)]}`} />
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                <span className="font-medium text-slate-900">{humanize(entry.action)}</span>
                {showEntity && entry.reference && (
                  <span className="text-sm text-slate-500">{ENTITY_LABEL[entry.entity_type]} {entry.reference}</span>
                )}
                {entry.to_status && entry.from_status !== entry.to_status && <StatusBadge status={entry.to_status} size="sm" />}
              </div>
              <p className="mt-0.5 text-sm text-slate-500">
                {formatDateTime(entry.at)}
                {entry.user && <> · {entry.user.name} <span className="text-slate-400">({ROLE_LABELS[entry.user.role]})</span></>}
              </p>
              {extra && <p className="mt-1 text-sm text-slate-700">{extra}</p>}
            </div>
          </li>
        );
      })}
    </ol>
  );
}
