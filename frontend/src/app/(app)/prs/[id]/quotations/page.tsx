"use client";

import { useState } from "react";
import { useParams, useRouter } from "next/navigation";

import { Icon } from "@/components/Icon";
import { StatusBadge } from "@/components/StatusBadge";
import { Button } from "@/components/ui/Button";
import { Field, Input, Select, Textarea } from "@/components/ui/Form";
import { Card, Notice, PageHeader } from "@/components/ui/Layout";
import { Modal } from "@/components/ui/Modal";
import { EmptyState, ErrorState, Loading } from "@/components/ui/States";
import { api } from "@/lib/api";
import { addDaysISO, formatDate, formatINR, formatQty, todayISO } from "@/lib/format";
import { useAction, useApi } from "@/lib/hooks";
import type { Comparison, ComparisonQuotation, PRDetail } from "@/types/api";

// ---- comparison table ---------------------------------------------------------------------------

function ComparisonTable({ cmp, canSelect, onSelect }: {
  cmp: Comparison; canSelect: boolean; onSelect: (q: ComparisonQuotation) => void;
}) {
  const quotes = cmp.quotations;
  const cell = (q: ComparisonQuotation) => (q.is_expired ? "bg-slate-50 text-slate-400" : "");
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full border-separate border-spacing-0 text-sm">
        <thead>
          <tr>
            <th className="sticky left-0 w-64 border-b border-slate-200 bg-white px-4 py-3 text-left align-bottom text-xs font-semibold uppercase tracking-wide text-slate-500">Item</th>
            {quotes.map((q) => (
              <th key={q.quotation_id} className={`min-w-[13rem] border-b border-l border-slate-200 px-4 py-3 text-left align-top font-normal ${cell(q)}`}>
                <div className="flex items-start justify-between gap-2">
                  <span className={`font-semibold ${q.is_expired ? "text-slate-400 line-through decoration-slate-300" : "text-slate-900"}`}>{q.supplier.name}</span>
                  {q.is_selected && <StatusBadge status="PO_CREATED" size="sm" />}
                </div>
                <div className="mt-1 space-y-0.5 text-xs text-slate-500">
                  <div>{q.delivery_days} days delivery · {q.payment_terms}</div>
                  <div className={q.is_expired ? "font-medium text-slate-500" : ""}>
                    {q.is_expired ? <span className="inline-flex items-center gap-1"><Icon name="clock" className="h-3.5 w-3.5" />Expired {formatDate(q.valid_until)}</span>
                      : `Valid until ${formatDate(q.valid_until)}`}
                  </div>
                </div>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {cmp.lines.map((row) => (
            <tr key={row.pr_line_id}>
              <td className="sticky left-0 border-b border-slate-100 bg-white px-4 py-3">
                <div className="font-medium text-slate-900">{row.item.name}</div>
                <div className="text-xs text-slate-500">{formatQty(row.quantity, row.item.unit)}</div>
              </td>
              {quotes.map((q) => {
                const c = row.cells.find((x) => x.quotation_id === q.quotation_id);
                return (
                  <td key={q.quotation_id} className={`border-b border-l border-slate-100 px-4 py-3 tabular-nums ${cell(q)} ${c?.is_lowest ? "bg-emerald-50" : ""}`}>
                    {c ? (
                      <div className="flex items-center justify-between gap-2">
                        <div>
                          <div className={c.is_lowest ? "font-semibold text-emerald-800" : ""}>{formatINR(c.unit_price)}</div>
                          <div className="text-xs opacity-70">{formatINR(c.line_total)}</div>
                        </div>
                        {c.is_lowest && <span className="rounded bg-emerald-600 px-1.5 py-0.5 text-[11px] font-semibold uppercase tracking-wide text-white">Lowest</span>}
                      </div>
                    ) : "—"}
                  </td>
                );
              })}
            </tr>
          ))}
          <tr>
            <td className="sticky left-0 bg-white px-4 py-3 font-semibold text-slate-900">Total</td>
            {quotes.map((q) => (
              <td key={q.quotation_id} className={`border-l border-slate-100 px-4 py-3 ${cell(q)} ${q.is_lowest_valid_total ? "bg-emerald-50" : ""}`}>
                <div className={`text-lg font-semibold tabular-nums ${q.is_lowest_valid_total ? "text-emerald-800" : q.is_expired ? "" : "text-slate-900"}`}>
                  {formatINR(q.total)}
                </div>
                {q.is_lowest_valid_total && (
                  <div className="mt-0.5 inline-flex items-center gap-1 text-xs font-semibold text-emerald-700"><Icon name="check" className="h-4 w-4" />Lowest valid total</div>
                )}
                {q.is_expired && <div className="mt-0.5 text-xs">Can&apos;t be selected</div>}
              </td>
            ))}
          </tr>
          {canSelect && (
            <tr>
              <td className="sticky left-0 bg-white" />
              {quotes.map((q) => (
                <td key={q.quotation_id} className="border-l border-slate-100 px-4 pb-4">
                  <Button size="sm" className="w-full" disabled={q.is_expired} onClick={() => onSelect(q)}
                          variant={q.is_lowest_valid_total ? "primary" : "secondary"}>
                    Select &amp; create PO
                  </Button>
                </td>
              ))}
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

// ---- select dialog: reason fields only when rule 6 needs them (hints come from the API) ------------

function SelectDialog({ pr, cmp, quote, onClose }: { pr: PRDetail; cmp: Comparison; quote: ComparisonQuotation | null; onClose: () => void }) {
  const router = useRouter();
  const { run, busy } = useAction();
  const [reason, setReason] = useState("");
  const [justification, setJustification] = useState("");
  if (!quote) return null;

  const needsJustification = cmp.selection.single_quote_justification_required;
  const needsReason = !cmp.selection.lowest_valid_quotation_ids.includes(quote.quotation_id);
  const lowest = cmp.quotations.find((q) => cmp.selection.lowest_valid_quotation_ids.includes(q.quotation_id));

  const confirm = async () => {
    const po = await run("select", () => api.quotations.select(pr.id, quote.quotation_id, {
      selection_reason: needsReason ? reason : null,
      single_quote_justification: needsJustification ? justification : null,
    }), (p) => `${p.po_number} issued to ${p.supplier.name}`);
    if (po) router.push(`/pos/${po.id}`);
  };

  return (
    <Modal open title={`Select ${quote.supplier.name}`} onClose={onClose} width="max-w-xl" footer={
      <>
        <Button variant="secondary" onClick={onClose}>Cancel</Button>
        <Button loading={busy === "select"} onClick={confirm} icon="cart">Create purchase order</Button>
      </>
    }>
      <div className="space-y-4">
        <p className="text-slate-600">
          A PO for <strong className="text-slate-900">{formatINR(quote.total)}</strong> will be issued to {quote.supplier.name} at
          these prices. Prices are copied onto the PO and can&apos;t change afterwards.
        </p>
        {needsJustification && (
          <>
            <Notice tone="warning" icon="alert" title="Only one valid quotation">
              {cmp.quotations.length > cmp.selection.valid_quotations ? "Expired quotations don't count. " : ""}Explain why a single quote is acceptable.
            </Notice>
            <Field label="Single-quote justification" required>
              <Textarea value={justification} onChange={(e) => setJustification(e.target.value)} autoFocus />
            </Field>
          </>
        )}
        {needsReason && lowest && (
          <>
            <Notice tone="warning" icon="alert" title="Not the lowest valid quotation">
              {lowest.supplier.name} offers {formatINR(lowest.total)} against {formatINR(quote.total)} here.
            </Notice>
            <Field label="Reason for choosing this supplier" required>
              <Textarea value={reason} onChange={(e) => setReason(e.target.value)} autoFocus={!needsJustification} />
            </Field>
          </>
        )}
      </div>
    </Modal>
  );
}

// ---- add quotation --------------------------------------------------------------------------------

function AddQuotation({ pr, onAdded }: { pr: PRDetail; onAdded: () => void }) {
  const suppliers = useApi(() => api.masters.suppliers({ active: true }), []);
  const { run, busy } = useAction();
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ supplier_id: "", quote_date: todayISO(), valid_until: addDaysISO(todayISO(), 30), delivery_days: "7", payment_terms: "30 days from invoice" });
  const [prices, setPrices] = useState<Record<number, string>>({});

  const submit = async () => {
    const q = await run("add", () => api.quotations.add(pr.id, {
      supplier_id: Number(form.supplier_id), quote_date: form.quote_date, valid_until: form.valid_until,
      delivery_days: Number(form.delivery_days), payment_terms: form.payment_terms,
      lines: pr.lines.map((l) => ({ pr_line_id: l.id, unit_price: prices[l.id] ?? "" })),
    }), (q) => `Quotation from ${q.supplier.name} added (${formatINR(q.total)})`);
    if (q) { setOpen(false); setPrices({}); setForm((f) => ({ ...f, supplier_id: "" })); onAdded(); }
  };

  return (
    <>
      <Button icon="plus" onClick={() => setOpen(true)}>Add quotation</Button>
      <Modal open={open} title="Add supplier quotation" onClose={() => setOpen(false)} width="max-w-2xl" footer={
        <>
          <Button variant="secondary" onClick={() => setOpen(false)}>Cancel</Button>
          <Button loading={busy === "add"} onClick={submit}>Save quotation</Button>
        </>
      }>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Supplier" required className="sm:col-span-2">
            <Select value={form.supplier_id} onChange={(e) => setForm({ ...form, supplier_id: e.target.value })}>
              <option value="">Choose a supplier…</option>
              {suppliers.data?.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
            </Select>
          </Field>
          <Field label="Quote date" required><Input type="date" value={form.quote_date} onChange={(e) => setForm({ ...form, quote_date: e.target.value })} /></Field>
          <Field label="Valid until" required><Input type="date" value={form.valid_until} onChange={(e) => setForm({ ...form, valid_until: e.target.value })} /></Field>
          <Field label="Delivery (days)" required><Input inputMode="numeric" value={form.delivery_days} onChange={(e) => setForm({ ...form, delivery_days: e.target.value })} /></Field>
          <Field label="Payment terms" required><Input value={form.payment_terms} onChange={(e) => setForm({ ...form, payment_terms: e.target.value })} /></Field>
        </div>
        <p className="mb-2 mt-5 text-sm font-medium text-slate-700">Unit prices <span className="font-normal text-slate-500">— every line must be priced; quantities are the PR&apos;s</span></p>
        <div className="divide-y divide-slate-100 rounded-lg border border-slate-200">
          {pr.lines.map((l) => (
            <div key={l.id} className="flex items-center gap-4 px-3 py-2">
              <div className="flex-1">
                <div className="font-medium text-slate-900">{l.item.name}</div>
                <div className="text-xs text-slate-500">{formatQty(l.quantity, l.item.unit)} · estimate {formatINR(l.estimated_unit_price)}</div>
              </div>
              <div className="w-40"><Input inputMode="decimal" placeholder="₹ per unit" value={prices[l.id] ?? ""}
                                           onChange={(e) => setPrices({ ...prices, [l.id]: e.target.value })} aria-label={`Price for ${l.item.name}`} /></div>
            </div>
          ))}
        </div>
      </Modal>
    </>
  );
}

// ---- page -----------------------------------------------------------------------------------------

export default function QuotationsPage() {
  const id = Number(useParams<{ id: string }>().id);
  const pr = useApi(() => api.prs.get(id), [id]);
  const cmp = useApi(() => api.quotations.compare(id), [id]);
  const [selecting, setSelecting] = useState<ComparisonQuotation | null>(null);

  if ((pr.loading && !pr.data) || (cmp.loading && !cmp.data)) return <Loading />;
  if (pr.error || cmp.error) return <ErrorState error={(pr.error ?? cmp.error)!} />;
  if (!pr.data || !cmp.data) return null;

  const canAdd = pr.data.actions.includes("add_quotation");
  const canSelect = pr.data.actions.includes("select_quotation");
  const s = cmp.data.selection;

  return (
    <>
      <PageHeader title={`Quotations for ${pr.data.pr_number}`} badge={<StatusBadge status={pr.data.status} size="lg" />}
                  back={{ href: `/prs/${id}`, label: pr.data.pr_number }} subtitle={pr.data.justification}
                  actions={canAdd && <AddQuotation pr={pr.data} onAdded={() => { void cmp.reload(); void pr.reload(); }} />} />
      <div className="space-y-6">
        {cmp.data.quotations.length > 0 && canSelect && (
          <div className="grid gap-3 md:grid-cols-3">
            <Notice tone="info" icon="scale" title={`${s.valid_quotations} valid quotation${s.valid_quotations === 1 ? "" : "s"}`}>
              {cmp.data.quotations.length - s.valid_quotations > 0 ? `${cmp.data.quotations.length - s.valid_quotations} expired — shown greyed out, not counted.` : "None expired."}
            </Notice>
            <Notice tone={s.single_quote_justification_required ? "warning" : "success"} icon={s.single_quote_justification_required ? "alert" : "checkCircle"}
                    title={s.single_quote_justification_required ? "Single quote: justification needed" : "Competitive quotes received"}>
              {s.single_quote_justification_required ? "Fewer than two valid quotations." : "At least two valid quotations."}
            </Notice>
            <Notice tone="success" icon="rupee" title={s.lowest_valid_total ? `Lowest valid total ${formatINR(s.lowest_valid_total)}` : "No valid quotation"}>
              Choosing any other supplier needs a reason.
            </Notice>
          </div>
        )}
        <Card title="Side-by-side comparison" subtitle="Lowest price per line highlighted in green; expired quotes greyed out" padded={false}>
          {cmp.data.quotations.length === 0 ? (
            <EmptyState icon="scale" title="No quotations yet">{canAdd ? "Add the quotations you've received from suppliers." : "Purchase hasn't recorded any quotations."}</EmptyState>
          ) : (
            <ComparisonTable cmp={cmp.data} canSelect={canSelect} onSelect={setSelecting} />
          )}
        </Card>
      </div>
      <SelectDialog key={selecting?.quotation_id ?? 0} pr={pr.data} cmp={cmp.data} quote={selecting} onClose={() => setSelecting(null)} />
    </>
  );
}
