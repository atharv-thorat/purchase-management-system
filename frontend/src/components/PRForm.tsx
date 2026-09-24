"use client";

import { useState } from "react";

import { Icon } from "@/components/Icon";
import { Button } from "@/components/ui/Button";
import { Field, Input, Select, Textarea } from "@/components/ui/Form";
import { Card } from "@/components/ui/Layout";
import { Loading } from "@/components/ui/States";
import { api } from "@/lib/api";
import { addDaysISO, formatINR, todayISO } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { PRIn } from "@/types/api";

interface Line { item_id: string; quantity: string; estimated_unit_price: string }
const blank: Line = { item_id: "", quantity: "", estimated_unit_price: "" };

/** Preview only: the server computes the real totals (and rounds each line to the paisa). */
function previewTotal(line: Line): string | null {
  const q = Number(line.quantity), p = Number(line.estimated_unit_price);
  return q > 0 && p > 0 ? (Math.round(q * p * 100) / 100).toFixed(2) : null;
}

export function PRForm({ initial, submitLabel, onSubmit }: {
  initial?: PRIn;
  submitLabel: string;
  onSubmit: (body: PRIn) => Promise<void>;
}) {
  const items = useApi(() => api.masters.items(), []);
  const [justification, setJustification] = useState(initial?.justification ?? "");
  const [requiredBy, setRequiredBy] = useState(initial?.required_by ?? addDaysISO(todayISO(), 14));
  const [lines, setLines] = useState<Line[]>(
    initial?.lines.map((l) => ({ item_id: String(l.item_id), quantity: l.quantity, estimated_unit_price: l.estimated_unit_price })) ?? [{ ...blank }],
  );
  const [busy, setBusy] = useState(false);

  const update = (i: number, patch: Partial<Line>) => setLines((all) => all.map((l, j) => (j === i ? { ...l, ...patch } : l)));
  const total = lines.reduce((sum, l) => sum + Number(previewTotal(l) ?? 0), 0);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    await onSubmit({
      justification,
      required_by: requiredBy,
      lines: lines.map((l) => ({ item_id: Number(l.item_id), quantity: l.quantity, estimated_unit_price: l.estimated_unit_price })),
    });
    setBusy(false);
  };

  if (items.loading && !items.data) return <Loading />;
  const byId = new Map(items.data?.map((i) => [String(i.id), i]));

  return (
    <form onSubmit={submit} className="space-y-6">
      <Card title="Details">
        <div className="grid gap-5 md:grid-cols-[1fr_14rem]">
          <Field label="Justification" required hint="Why is this needed? Approvers read this first.">
            <Textarea value={justification} onChange={(e) => setJustification(e.target.value)} rows={3} />
          </Field>
          <Field label="Needed by" required>
            <Input type="date" value={requiredBy} min={todayISO()} onChange={(e) => setRequiredBy(e.target.value)} />
          </Field>
        </div>
      </Card>

      <Card title="Items" subtitle="Quantities are what will be quoted, ordered and received" padded={false}>
        <table className="min-w-full text-sm">
          <thead className="border-b border-slate-200 bg-slate-50/80 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
            <tr><th className="px-4 py-2.5">Item</th><th className="w-36 px-4 py-2.5">Quantity</th><th className="w-44 px-4 py-2.5">Est. unit price (₹)</th><th className="w-40 px-4 py-2.5 text-right">Line total</th><th className="w-12" /></tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {lines.map((line, i) => {
              const unit = byId.get(line.item_id)?.unit;
              return (
                <tr key={i}>
                  <td className="px-4 py-2.5">
                    <Select value={line.item_id} onChange={(e) => update(i, { item_id: e.target.value })} aria-label={`Item ${i + 1}`}>
                      <option value="">Choose an item…</option>
                      {items.data?.map((item) => <option key={item.id} value={item.id}>{item.name} ({item.unit})</option>)}
                    </Select>
                  </td>
                  <td className="px-4 py-2.5">
                    <div className="flex items-center gap-2">
                      <Input inputMode="decimal" value={line.quantity} onChange={(e) => update(i, { quantity: e.target.value })} aria-label={`Quantity ${i + 1}`} />
                      <span className="w-8 text-slate-500">{unit}</span>
                    </div>
                  </td>
                  <td className="px-4 py-2.5">
                    <Input inputMode="decimal" value={line.estimated_unit_price} onChange={(e) => update(i, { estimated_unit_price: e.target.value })} aria-label={`Unit price ${i + 1}`} />
                  </td>
                  <td className="px-4 py-2.5 text-right tabular-nums text-slate-700">{formatINR(previewTotal(line))}</td>
                  <td className="px-2 py-2.5">
                    {lines.length > 1 && (
                      <button type="button" onClick={() => setLines((all) => all.filter((_, j) => j !== i))}
                              className="rounded p-1.5 text-slate-400 hover:bg-red-50 hover:text-red-600" aria-label="Remove line">
                        <Icon name="trash" className="h-4 w-4" />
                      </button>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        <div className="flex items-center justify-between border-t border-slate-100 px-4 py-3">
          <Button type="button" variant="ghost" size="sm" icon="plus" onClick={() => setLines((all) => [...all, { ...blank }])}>Add line</Button>
          <p className="text-slate-600">Estimated total <span className="ml-2 text-lg font-semibold tabular-nums text-slate-900">{formatINR(total.toFixed(2))}</span></p>
        </div>
      </Card>

      <div className="flex justify-end gap-2">
        <Button type="submit" loading={busy}>{submitLabel}</Button>
      </div>
    </form>
  );
}
