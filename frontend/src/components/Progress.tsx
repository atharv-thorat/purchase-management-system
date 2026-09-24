import { formatQty, ratio } from "@/lib/format";
import type { ItemUnit } from "@/types/api";

/** One quantity against the ordered quantity, e.g. accepted 40 of 50. */
export function QtyProgress({ label, value, of, unit, tone }: {
  label: string; value: string; of: string; unit: ItemUnit; tone: "blue" | "green";
}) {
  const r = ratio(value, of);
  const fill = tone === "blue" ? "bg-brand-500" : "bg-emerald-600";
  const track = tone === "blue" ? "bg-brand-100" : "bg-emerald-100";
  return (
    <div className="min-w-[9rem]">
      <div className="mb-1 flex justify-between gap-2 text-xs">
        <span className="text-slate-500">{label}</span>
        <span className="tabular-nums text-slate-800">{formatQty(value)} / {formatQty(of, unit)}</span>
      </div>
      <div className={`h-2 overflow-hidden rounded-full ${track}`} role="progressbar" aria-label={label}
           aria-valuenow={Math.round(r * 100)} aria-valuemin={0} aria-valuemax={100}>
        <div className={`h-full rounded-full ${fill}`} style={{ width: `${r * 100}%` }} />
      </div>
    </div>
  );
}
