"use client";

import { useState } from "react";
import { useParams } from "next/navigation";

import { MatchBanner } from "@/components/MatchBanner";
import { ReasonDialog } from "@/components/ReasonDialog";
import { StatusBadge } from "@/components/StatusBadge";
import { StatusTimeline } from "@/components/StatusTimeline";
import { Button } from "@/components/ui/Button";
import { Field, Input, Select } from "@/components/ui/Form";
import { Card, Facts, Notice, PageHeader } from "@/components/ui/Layout";
import { EmptyState, ErrorState, Loading } from "@/components/ui/States";
import { DocLink, Table, TBody, Td, Th, THead } from "@/components/ui/Table";
import { api } from "@/lib/api";
import { formatDate, formatDateTime, formatINR, formatQty, humanize, todayISO } from "@/lib/format";
import { useAction, useApi } from "@/lib/hooks";
import type { InvoiceDetail, PaymentMode } from "@/types/api";

function PaymentForm({ invoice, onPaid }: { invoice: InvoiceDetail; onPaid: (inv: InvoiceDetail) => void }) {
  const { run, busy } = useAction();
  const [amount, setAmount] = useState(invoice.balance_due);
  const [mode, setMode] = useState<PaymentMode>("NEFT");
  const [reference, setReference] = useState("");
  const [paidOn, setPaidOn] = useState(todayISO());

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    const result = await run("pay", () => api.invoices.pay(invoice.id, { amount, mode, reference_no: reference, paid_on: paidOn }),
      (inv) => inv.po.status === "CLOSED" ? `Payment recorded — ${inv.po.po_number} is now closed` : `Payment recorded — ${humanize(inv.status).toLowerCase()}`);
    if (result) { onPaid(result); setAmount(result.balance_due); setReference(""); }
  };

  return (
    <Card title="Record a payment">
      <div className="mb-5 flex items-end justify-between rounded-lg bg-slate-50 px-4 py-3">
        <div>
          <p className="text-sm text-slate-500">Balance due</p>
          <p className="text-3xl font-semibold tabular-nums text-slate-900">{formatINR(invoice.balance_due)}</p>
        </div>
        <p className="text-right text-sm text-slate-500">Invoice {formatINR(invoice.total)}<br />Paid so far {formatINR(invoice.amount_paid)}</p>
      </div>
      <form onSubmit={submit} className="grid gap-4 sm:grid-cols-2">
        <Field label="Amount (₹)" required hint="Partial payments are allowed"><Input inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} /></Field>
        <Field label="Mode" required>
          <Select value={mode} onChange={(e) => setMode(e.target.value as PaymentMode)}>
            <option value="NEFT">NEFT</option><option value="CHEQUE">Cheque</option><option value="UPI">UPI</option>
          </Select>
        </Field>
        <Field label="Reference number" required><Input value={reference} onChange={(e) => setReference(e.target.value)} placeholder="UTR / cheque no." /></Field>
        <Field label="Paid on" required><Input type="date" value={paidOn} max={todayISO()} onChange={(e) => setPaidOn(e.target.value)} /></Field>
        <div className="sm:col-span-2 flex justify-end"><Button type="submit" icon="rupee" loading={busy === "pay"}>Record payment</Button></div>
      </form>
    </Card>
  );
}

export default function InvoiceDetailPage() {
  const id = Number(useParams<{ id: string }>().id);
  const { data: inv, error, loading, reload, setData } = useApi(() => api.invoices.get(id), [id]);
  const { run, busy } = useAction();
  const [rejecting, setRejecting] = useState(false);

  if (loading && !inv) return <Loading />;
  if (error || !inv) return error ? <ErrorState error={error} onRetry={reload} /> : null;
  const has = (a: string) => inv.actions.includes(a as never);

  return (
    <>
      <PageHeader title={`Invoice ${inv.supplier_invoice_number}`} badge={<StatusBadge status={inv.status} size="lg" />}
                  back={{ href: "/invoices", label: "Invoices" }}
                  subtitle={<>{inv.supplier.name} · against <DocLink href={`/pos/${inv.po.id}`}>{inv.po.po_number}</DocLink> <StatusBadge status={inv.po.status} size="sm" /></>}
                  actions={<>
                    {has("rematch") && (
                      <Button variant="secondary" icon="refresh" loading={busy === "rematch"}
                              onClick={async () => {
                                const r = await run("rematch", () => api.invoices.rematch(inv.id),
                                  (x) => x.status === "MATCHED" ? "Rematched — the invoice now matches" : "Rematched — still a mismatch");
                                if (r) setData(r);
                              }}>Rematch</Button>
                    )}
                    {has("reject") && <Button variant="danger" icon="xCircle" onClick={() => setRejecting(true)}>Reject invoice</Button>}
                  </>} />

      <div className="space-y-6">
        <MatchBanner invoice={inv} />
        {inv.status === "MISMATCH" && has("rematch") && (
          <Notice tone="info" title="What next?">
            If goods have arrived since, <strong>Rematch</strong> re-checks against the latest goods receipts. If the invoice itself is wrong,
            <strong> Reject</strong> it — the supplier can then send a corrected invoice under the same number.
          </Notice>
        )}
        {inv.status === "REJECTED" && inv.rejection_reason && <Notice tone="danger" icon="xCircle" title="Invoice rejected">“{inv.rejection_reason}”</Notice>}

        <Card>
          <Facts items={[
            ["Supplier", inv.supplier.name],
            ["Invoice date", formatDate(inv.invoice_date)],
            ["Invoice total", <span key="t" className="font-semibold">{formatINR(inv.total)}</span>],
            ["Paid", formatINR(inv.amount_paid)],
            ["Balance due", inv.status === "REJECTED" ? "—" : <span key="b" className="font-semibold">{formatINR(inv.balance_due)}</span>],
            ["Entered by", `${inv.created_by.name} · ${formatDateTime(inv.created_at)}`],
          ]} />
        </Card>

        <Card title="Lines" subtitle="Compared with the PO price and the quantity accepted at receipt" padded={false}>
          <Table>
            <THead><Th>Item</Th><Th right>Qty billed</Th><Th right>Unit price</Th><Th right>PO price</Th><Th right>Line total</Th></THead>
            <TBody>
              {inv.lines.map((l) => (
                <tr key={l.id}>
                  <Td className="font-medium">{l.item.name}</Td>
                  <Td right>{formatQty(l.qty, l.item.unit)}</Td>
                  <Td right className={l.price_matches ? "" : "font-semibold text-red-700"}>{formatINR(l.unit_price)}</Td>
                  <Td right className="text-slate-500">{formatINR(l.po_unit_price)}</Td>
                  <Td right>{formatINR(l.line_total)}</Td>
                </tr>
              ))}
            </TBody>
          </Table>
        </Card>

        <div className="grid gap-6 lg:grid-cols-2">
          {has("record_payment") ? <PaymentForm invoice={inv} onPaid={setData} /> : inv.payments && (
            <Card title="Payments" padded={false}>
              {inv.payments.length === 0 ? <EmptyState icon="rupee" title="No payments yet" /> : (
                <Table>
                  <THead><Th>Date</Th><Th>Mode</Th><Th>Reference</Th><Th right>Amount</Th></THead>
                  <TBody>{inv.payments.map((p) => (
                    <tr key={p.id}><Td>{formatDate(p.paid_on)}</Td><Td>{p.mode}</Td><Td>{p.reference_no}</Td><Td right>{formatINR(p.amount)}</Td></tr>
                  ))}</TBody>
                </Table>
              )}
            </Card>
          )}
          <Card title="History"><StatusTimeline entries={inv.timeline} /></Card>
        </div>
        {has("record_payment") && inv.payments && inv.payments.length > 0 && (
          <Card title="Payments made" padded={false}>
            <Table>
              <THead><Th>Date</Th><Th>Mode</Th><Th>Reference</Th><Th>Recorded by</Th><Th right>Amount</Th></THead>
              <TBody>{inv.payments.map((p) => (
                <tr key={p.id}><Td>{formatDate(p.paid_on)}</Td><Td>{p.mode}</Td><Td>{p.reference_no}</Td><Td>{p.recorded_by.name}</Td><Td right>{formatINR(p.amount)}</Td></tr>
              ))}</TBody>
            </Table>
          </Card>
        )}
      </div>

      <ReasonDialog open={rejecting} title={`Reject ${inv.supplier_invoice_number}`} label="Reason for rejection" confirmLabel="Reject invoice"
                    variant="danger" onClose={() => setRejecting(false)}
                    intro="Rejection is final. The supplier can then issue a corrected invoice under the same number."
                    onConfirm={async (text) => {
                      const r = await run("reject", () => api.invoices.reject(inv.id, text), (x) => `${x.supplier_invoice_number} rejected`);
                      if (r) setData(r);
                      return Boolean(r);
                    }} />
    </>
  );
}
