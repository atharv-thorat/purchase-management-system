"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";

import { StatusBadge } from "@/components/StatusBadge";
import { Button } from "@/components/ui/Button";
import { Field, Input, Textarea } from "@/components/ui/Form";
import { Card, PageHeader } from "@/components/ui/Layout";
import { EmptyState, ErrorState, Loading } from "@/components/ui/States";
import { api } from "@/lib/api";
import { isPositive, subtractQty } from "@/lib/decimal";
import { formatQty, humanize, todayISO, trimZeros } from "@/lib/format";
import { useAction, useApi } from "@/lib/hooks";

interface Row { received: string; rejected: string; reason: string }

export default function ReceiveGoodsPage() {
  const id = Number(useParams<{ id: string }>().id);
  const router = useRouter();
  const { run, busy } = useAction();
  const { data, error, loading } = useApi(() => api.pos.receivable(id), [id]);
  const [rows, setRows] = useState<Record<number, Row>>({});
  const [date, setDate] = useState(todayISO());
  const [remarks, setRemarks] = useState("");

  // Pre-fill: everything still pending arrives and is accepted.
  useEffect(() => {
    if (!data) return;
    setRows(Object.fromEntries(data.lines.map((l) => [l.po_line_id, { received: trimZeros(l.qty_pending), rejected: "0", reason: "" }])));
  }, [data]);

  if (loading && !data) return <Loading />;
  if (error || !data) return error ? <ErrorState error={error} /> : null;
  const pendingLines = data.lines.filter((l) => isPositive(l.qty_pending));
  const update = (lineId: number, patch: Partial<Row>) => setRows((r) => ({ ...r, [lineId]: { ...r[lineId], ...patch } }));

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    const lines = data.lines
      .filter((l) => isPositive(rows[l.po_line_id]?.received ?? ""))
      .map((l) => {
        const r = rows[l.po_line_id];
        // The storekeeper counts what arrived and what was rejected; accepted is the difference.
        // The server re-validates received = accepted + rejected and every other GRN rule.
        const accepted = subtractQty(r.received, r.rejected) ?? "";
        return { po_line_id: l.po_line_id, qty_received: r.received, qty_accepted: accepted,
                 qty_rejected: r.rejected || "0", rejection_reason: r.reason || null };
      });
    const grn = await run("save", () => api.pos.recordGrn(id, { received_date: date, remarks: remarks || null, lines }),
                          (g) => `${g.grn_number} recorded — ${g.po.po_number} is now ${humanize(g.po.status).toLowerCase()}`);
    if (grn) router.push(`/pos/${id}`);
  };

  return (
    <>
      <PageHeader title={`Receive goods · ${data.po.po_number}`} badge={<StatusBadge status={data.po.status} size="lg" />}
                  back={{ href: `/pos/${id}`, label: data.po.po_number }} subtitle={data.po.supplier.name} />
      {pendingLines.length === 0 ? <Card><EmptyState icon="truck" title="Nothing left to receive on this PO" /></Card> : (
        <form onSubmit={submit} className="space-y-6">
          <Card title="What arrived" subtitle="Pre-filled with the quantities still pending. Enter any rejected quantity with a reason." padded={false}>
            <table className="min-w-full text-sm">
              <thead className="border-b border-slate-200 bg-slate-50/80 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
                <tr><th className="px-4 py-2.5">Item</th><th className="px-4 py-2.5">Pending</th><th className="w-36 px-4 py-2.5">Received</th>
                  <th className="w-36 px-4 py-2.5">Rejected</th><th className="px-4 py-2.5">Rejection reason</th><th className="w-32 px-4 py-2.5 text-right">Accepted</th></tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {data.lines.map((l) => {
                  const r = rows[l.po_line_id];
                  if (!r) return null;
                  const done = !isPositive(l.qty_pending);
                  const accepted = subtractQty(r.received, r.rejected);
                  return (
                    <tr key={l.po_line_id} className={done ? "bg-slate-50 text-slate-400" : ""}>
                      <td className="px-4 py-3"><div className="font-medium text-slate-900">{l.item.name}</div>
                        <div className="text-xs text-slate-500">Ordered {formatQty(l.qty_ordered, l.item.unit)} · accepted so far {formatQty(l.qty_accepted)}</div></td>
                      <td className="px-4 py-3 tabular-nums">{formatQty(l.qty_pending, l.item.unit)}</td>
                      <td className="px-4 py-3"><Input inputMode="decimal" value={r.received} disabled={done}
                                                        onChange={(e) => update(l.po_line_id, { received: e.target.value })} aria-label={`Received ${l.item.name}`} /></td>
                      <td className="px-4 py-3"><Input inputMode="decimal" value={r.rejected} disabled={done}
                                                        onChange={(e) => update(l.po_line_id, { rejected: e.target.value })} aria-label={`Rejected ${l.item.name}`} /></td>
                      <td className="px-4 py-3">
                        {isPositive(r.rejected) && (
                          <Input value={r.reason} placeholder="e.g. damaged in transit" onChange={(e) => update(l.po_line_id, { reason: e.target.value })}
                                 aria-label={`Rejection reason ${l.item.name}`} />
                        )}
                      </td>
                      <td className="px-4 py-3 text-right font-medium tabular-nums text-slate-900">{done ? "—" : formatQty(accepted, l.item.unit)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </Card>
          <Card>
            <div className="grid gap-5 md:grid-cols-[14rem_1fr]">
              <Field label="Received on" required><Input type="date" value={date} max={todayISO()} onChange={(e) => setDate(e.target.value)} /></Field>
              <Field label="Remarks"><Textarea rows={2} value={remarks} onChange={(e) => setRemarks(e.target.value)} placeholder="Delivery note number, condition, anything notable" /></Field>
            </div>
          </Card>
          <div className="flex justify-end"><Button type="submit" icon="truck" loading={busy === "save"}>Record goods receipt</Button></div>
        </form>
      )}
    </>
  );
}
