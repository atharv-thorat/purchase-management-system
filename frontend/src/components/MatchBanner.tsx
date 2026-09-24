import { Icon } from "@/components/Icon";
import type { InvoiceDetail } from "@/types/api";

/** The three-way-match result, impossible to miss: green when it passed, red with every reason
 *  when it didn't. Colour is always paired with an icon and words. */
export function MatchBanner({ invoice }: { invoice: InvoiceDetail }) {
  const { status, mismatch_reasons: reasons } = invoice;

  if (status === "MISMATCH" || (status === "REJECTED" && reasons.length)) {
    return (
      <section className="overflow-hidden rounded-xl border-2 border-red-600 bg-red-50 shadow-sm" role="alert">
        <div className="flex items-center gap-4 bg-red-600 px-6 py-4 text-white">
          <Icon name="xCircle" className="h-9 w-9 shrink-0" />
          <div>
            <p className="text-2xl font-bold tracking-wide">MISMATCH</p>
            <p className="text-red-50">
              {status === "REJECTED" ? "Rejected after failing the three-way match" : "Three-way match failed — this invoice can't be paid"}
            </p>
          </div>
          <span className="ml-auto rounded-full bg-white/20 px-3 py-1 text-sm font-semibold">
            {reasons.length} problem{reasons.length === 1 ? "" : "s"}
          </span>
        </div>
        <ol className="divide-y divide-red-200">
          {reasons.map((reason, i) => (
            <li key={i} className="flex items-start gap-3 px-6 py-3 text-[17px] text-red-950">
              <span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-red-600 text-sm font-bold text-white">{i + 1}</span>
              <span>{reason}</span>
            </li>
          ))}
        </ol>
      </section>
    );
  }

  if (status === "MATCHED" || status === "PARTIALLY_PAID" || status === "PAID") {
    const sub = { MATCHED: "Price, quantity and total all agree with the PO and goods received. Ready for payment.",
                  PARTIALLY_PAID: "Price, quantity and total agree. Part-paid.",
                  PAID: "Price, quantity and total agree. Fully paid." }[status];
    return (
      <section className="flex items-center gap-4 rounded-xl border-2 border-emerald-600 bg-emerald-600 px-6 py-4 text-white shadow-sm" role="status">
        <Icon name="checkCircle" className="h-9 w-9 shrink-0" />
        <div>
          <p className="text-2xl font-bold tracking-wide">MATCHED</p>
          <p className="text-emerald-50">{sub}</p>
        </div>
      </section>
    );
  }

  return null;
}
