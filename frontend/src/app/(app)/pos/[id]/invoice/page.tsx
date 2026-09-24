"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";

import { StatusBadge } from "@/components/StatusBadge";
import { Button } from "@/components/ui/Button";
import { Field, Input } from "@/components/ui/Form";
import { Card, Notice, PageHeader } from "@/components/ui/Layout";
import { ErrorState, Loading } from "@/components/ui/States";
import { api } from "@/lib/api";
import { formatINR, formatQty, todayISO, trimZeros } from "@/lib/format";
import { useAction, useApi } from "@/lib/hooks";

interface Row { include: boolean; qty: string; price: string }

export default function EnterInvoicePage() {
  const id = Number(useParams<{ id: string }>().id);
  const router = useRouter();
  const { run, busy } = useAction();
  const { data: po, error, loading } = useApi(() => api.pos.get(id), [id]);
  const [rows, setRows] = useState<Record<number, Row>>({});
  const [number, setNumber] = useState("");
  const [date, setDate] = useState(todayISO());
  const [total, setTotal] = useState("");
  const [totalTouched, setTotalTouched] = useState(false);

  // Pre-fill from the PO: accepted-but-not-yet-invoiced quantity at the PO price. Type what the
  // supplier actually printed; the three-way match runs on the server when you save.
  useEffect(() => {
    if (!po) return;
    setRows(Object.fromEntries(po.lines.map((l) => [l.id, {
      include: Number(l.qty_uninvoiced) > 0, qty: trimZeros(l.qty_uninvoiced), price: l.unit_price }])));
  }, [po]);

  const suggested = po ? po.lines.reduce((sum, l) => {
    const r = rows[l.id];
    return r?.include ? sum + Math.round(Number(r.qty) * Number(r.price) * 100) / 100 : sum;
  }, 0).toFixed(2) : "0.00";
  useEffect(() => { if (!totalTouched) setTotal(suggested); }, [suggested, totalTouched]);

  if (loading && !po) return <Loading />;
  if (error || !po) return error ? <ErrorState error={error} /> : null;
  const update = (lineId: number, patch: Partial<Row>) => setRows((r) => ({ ...r, [lineId]: { ...r[lineId], ...patch } }));

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    const lines = po.lines.filter((l) => rows[l.id]?.include).map((l) => ({ po_line_id: l.id, qty: rows[l.id].qty, unit_price: rows[l.id].price }));
    const invoice = await run("save", () => api.pos.enterInvoice(id, { supplier_invoice_number: number, invoice_date: date, total, lines }),
                              (inv) => inv.status === "MATCHED" ? `${inv.supplier_invoice_number} matched` : `${inv.supplier_invoice_number} saved with a mismatch`);
    if (invoice) router.push(`/invoices/${invoice.id}`);
  };

  return (
    <>
      <PageHeader title={`Enter invoice · ${po.po_number}`} badge={<StatusBadge status={po.status} size="lg" />}
                  back={{ href: `/pos/${id}`, label: po.po_number }} subtitle={`From ${po.supplier.name}`} />
      <form onSubmit={submit} className="space-y-6">
        <Notice tone="info" title="Copy the figures from the supplier's invoice">
          Lines are pre-filled with what has been received but not yet invoiced, at the PO price. If the supplier billed
          something different, type their figures — the three-way match will show every difference.
        </Notice>
        <Card>
          <div className="grid gap-5 md:grid-cols-3">
            <Field label="Supplier invoice number" required><Input value={number} onChange={(e) => setNumber(e.target.value)} placeholder="e.g. SSST/26-27/1102" autoFocus /></Field>
            <Field label="Invoice date" required><Input type="date" value={date} max={todayISO()} onChange={(e) => setDate(e.target.value)} /></Field>
            <Field label="Invoice total (₹)" required hint={totalTouched ? `Sum of lines: ${formatINR(suggested)}` : "As printed on the invoice"}>
              <Input inputMode="decimal" value={total} onChange={(e) => { setTotal(e.target.value); setTotalTouched(true); }} />
            </Field>
          </div>
        </Card>
        <Card title="Invoice lines" padded={false}>
          <table className="min-w-full text-sm">
            <thead className="border-b border-slate-200 bg-slate-50/80 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
              <tr><th className="w-12 px-4 py-2.5" /><th className="px-4 py-2.5">Item</th><th className="px-4 py-2.5">Accepted / invoiced</th>
                <th className="w-36 px-4 py-2.5">Qty billed</th><th className="w-40 px-4 py-2.5">Unit price (₹)</th><th className="px-4 py-2.5 text-right">PO price</th></tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {po.lines.map((l) => {
                const r = rows[l.id];
                if (!r) return null;
                return (
                  <tr key={l.id} className={r.include ? "" : "text-slate-400"}>
                    <td className="px-4 py-3"><input type="checkbox" checked={r.include} onChange={(e) => update(l.id, { include: e.target.checked })}
                                                     className="h-4 w-4 rounded border-slate-300" aria-label={`Include ${l.item.name}`} /></td>
                    <td className="px-4 py-3 font-medium text-slate-900">{l.item.name}</td>
                    <td className="px-4 py-3 tabular-nums">{formatQty(l.qty_accepted)} / {formatQty(l.qty_invoiced, l.item.unit)}</td>
                    <td className="px-4 py-3"><Input inputMode="decimal" value={r.qty} disabled={!r.include} onChange={(e) => update(l.id, { qty: e.target.value })} aria-label={`Qty ${l.item.name}`} /></td>
                    <td className="px-4 py-3"><Input inputMode="decimal" value={r.price} disabled={!r.include} onChange={(e) => update(l.id, { price: e.target.value })} aria-label={`Price ${l.item.name}`} /></td>
                    <td className="px-4 py-3 text-right tabular-nums text-slate-600">{formatINR(l.unit_price)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </Card>
        <div className="flex justify-end"><Button type="submit" icon="receipt" loading={busy === "save"}>Save and run three-way match</Button></div>
      </form>
    </>
  );
}
