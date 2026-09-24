"use client";

import { useState } from "react";
import { useParams } from "next/navigation";

import { QtyProgress } from "@/components/Progress";
import { ReasonDialog } from "@/components/ReasonDialog";
import { StatusBadge } from "@/components/StatusBadge";
import { StatusTimeline } from "@/components/StatusTimeline";
import { Button, ButtonLink } from "@/components/ui/Button";
import { Card, Facts, Notice, PageHeader } from "@/components/ui/Layout";
import { EmptyState, ErrorState, Loading } from "@/components/ui/States";
import { DocLink, RowLink, Table, TBody, Td, Th, THead } from "@/components/ui/Table";
import { api } from "@/lib/api";
import { formatDate, formatDateTime, formatINR, formatQty, humanize } from "@/lib/format";
import { useAction, useApi } from "@/lib/hooks";
import type { PODetail } from "@/types/api";

function Actions({ po, onChange }: { po: PODetail; onChange: (po: PODetail) => void }) {
  const { run } = useAction();
  const [dialog, setDialog] = useState<null | "cancel" | "short_close">(null);
  const has = (a: string) => po.actions.includes(a as never);
  const act = async (key: string, call: () => Promise<PODetail>, message: (p: PODetail) => string) => {
    const result = await run(key, call, message);
    if (result) onChange(result);
    return Boolean(result);
  };
  return (
    <>
      {has("record_grn") && <ButtonLink href={`/pos/${po.id}/receive`} icon="truck">Record goods receipt</ButtonLink>}
      {has("enter_invoice") && <ButtonLink href={`/pos/${po.id}/invoice`} icon="receipt">Enter supplier invoice</ButtonLink>}
      {has("short_close") && <Button variant="secondary" onClick={() => setDialog("short_close")}>Short-close</Button>}
      {has("cancel") && <Button variant="danger" icon="xCircle" onClick={() => setDialog("cancel")}>Cancel PO</Button>}

      <ReasonDialog open={dialog === "cancel"} title={`Cancel ${po.po_number}`} label="Cancellation reason" confirmLabel="Cancel PO"
                    variant="danger" onClose={() => setDialog(null)}
                    intro={`${po.pr.pr_number} goes back to Approved, so another quotation can be selected without re-approval.`}
                    onConfirm={(text) => act("cancel", () => api.pos.cancel(po.id, text), (p) => `${p.po_number} cancelled; ${p.pr.pr_number} is approved again`)} />
      <ReasonDialog open={dialog === "short_close"} title={`Short-close ${po.po_number}`} label="Why won't the rest be delivered?"
                    confirmLabel="Short-close" onClose={() => setDialog(null)}
                    intro="No more goods receipts will be accepted. Goods already accepted can still be invoiced and paid; the PO closes once they are."
                    onConfirm={(text) => act("short", () => api.pos.shortClose(po.id, text), (p) => `${p.po_number} is now ${humanize(p.status).toLowerCase()}`)} />
    </>
  );
}

export default function PODetailPage() {
  const id = Number(useParams<{ id: string }>().id);
  const { data: po, error, loading, reload, setData } = useApi(() => api.pos.get(id), [id]);

  if (loading && !po) return <Loading />;
  if (error || !po) return error ? <ErrorState error={error} onRetry={reload} /> : null;

  return (
    <>
      <PageHeader title={po.po_number} badge={<StatusBadge status={po.status} size="lg" />} back={{ href: "/pos", label: "Purchase orders" }}
                  subtitle={<>{po.supplier.name} · for <DocLink href={`/prs/${po.pr.id}`}>{po.pr.pr_number}</DocLink> ({po.pr.department.name})</>}
                  actions={<Actions po={po} onChange={setData} />} />
      <div className="space-y-6">
        {po.status === "CANCELLED" && po.cancel_reason && <Notice tone="danger" icon="xCircle" title="Cancelled">“{po.cancel_reason}”</Notice>}
        {po.short_close_reason && <Notice tone="warning" icon="alert" title="Short-closed — no further deliveries">“{po.short_close_reason}”</Notice>}
        {po.status === "CLOSED" && <Notice tone="success" icon="checkCircle" title="Closed">Everything received has been invoiced, matched and paid.</Notice>}

        <Card>
          <Facts items={[
            ["Supplier", po.supplier.name],
            ["Total", <span key="t" className="font-semibold">{formatINR(po.total)}</span>],
            ["Issued", formatDateTime(po.created_at)],
            ["Issued by", po.created_by.name],
            ["Requested by", `${po.pr.requester.name} (${po.pr.department.name})`],
            ...(po.selection_reason ? [["Why this supplier", po.selection_reason] as [string, string]] : []),
            ...(po.single_quote_justification ? [["Single-quote justification", po.single_quote_justification] as [string, string]] : []),
          ]} />
        </Card>

        <Card title="Lines" subtitle="Prices are fixed from the selected quotation" padded={false}>
          <Table>
            <THead><Th>Item</Th><Th right>Unit price</Th><Th right>Line total</Th><Th>Received (accepted)</Th><Th>Invoiced (matched)</Th></THead>
            <TBody>
              {po.lines.map((l) => (
                <tr key={l.id}>
                  <Td>
                    <div className="font-medium">{l.item.name}</div>
                    <div className="text-xs text-slate-500">Ordered {formatQty(l.qty_ordered, l.item.unit)}</div>
                  </Td>
                  <Td right>{formatINR(l.unit_price)}</Td>
                  <Td right>{formatINR(l.line_total)}</Td>
                  <Td className="w-64"><QtyProgress label="Accepted" value={l.qty_accepted} of={l.qty_ordered} unit={l.item.unit} tone="blue" /></Td>
                  <Td className="w-64"><QtyProgress label="Invoiced" value={l.qty_invoiced} of={l.qty_ordered} unit={l.item.unit} tone="green" /></Td>
                </tr>
              ))}
            </TBody>
          </Table>
        </Card>

        {po.goods_receipts && (
          <Card title="Goods receipts" padded={false}>
            {po.goods_receipts.length === 0 ? <EmptyState icon="truck" title="Nothing received yet" /> : (
              <Table>
                <THead><Th>GRN</Th><Th>Received</Th><Th>By</Th><Th>Lines</Th><Th>Remarks</Th></THead>
                <TBody>
                  {po.goods_receipts.map((g) => (
                    <RowLink key={g.id} href={`/grns/${g.id}`}>
                      <Td><DocLink href={`/grns/${g.id}`}>{g.grn_number}</DocLink></Td>
                      <Td>{formatDate(g.received_date)}</Td>
                      <Td>{g.received_by.name}</Td>
                      <Td>
                        {g.lines.map((gl) => (
                          <div key={gl.id} className="text-sm">
                            {gl.item.name}: {formatQty(gl.qty_accepted, gl.item.unit)} accepted
                            {gl.qty_rejected !== "0.000" && <span className="text-red-700">, {formatQty(gl.qty_rejected)} rejected ({gl.rejection_reason})</span>}
                          </div>
                        ))}
                      </Td>
                      <Td className="text-slate-600">{g.remarks ?? "—"}</Td>
                    </RowLink>
                  ))}
                </TBody>
              </Table>
            )}
          </Card>
        )}

        <div className="grid gap-6 lg:grid-cols-2">
          {po.invoices && (
            <Card title="Invoices" padded={false}>
              {po.invoices.length === 0 ? <EmptyState icon="receipt" title="No invoices yet" /> : (
                <Table>
                  <THead><Th>Invoice</Th><Th>Status</Th><Th right>Total</Th><Th right>Balance due</Th></THead>
                  <TBody>
                    {po.invoices.map((i) => (
                      <RowLink key={i.id} href={`/invoices/${i.id}`}>
                        <Td><DocLink href={`/invoices/${i.id}`}>{i.supplier_invoice_number}</DocLink><div className="text-xs text-slate-500">{formatDate(i.invoice_date)}</div></Td>
                        <Td><StatusBadge status={i.status} /></Td>
                        <Td right>{formatINR(i.total)}</Td>
                        <Td right>{i.status === "REJECTED" ? "—" : formatINR(i.balance_due)}</Td>
                      </RowLink>
                    ))}
                  </TBody>
                </Table>
              )}
            </Card>
          )}
          {po.payments && (
            <Card title="Payments" padded={false}>
              {po.payments.length === 0 ? <EmptyState icon="rupee" title="No payments yet" /> : (
                <Table>
                  <THead><Th>Date</Th><Th>Invoice</Th><Th>Mode</Th><Th right>Amount</Th></THead>
                  <TBody>
                    {po.payments.map((p) => (
                      <tr key={p.id}>
                        <Td>{formatDate(p.paid_on)}</Td>
                        <Td>{p.supplier_invoice_number}</Td>
                        <Td>{p.mode} <span className="text-xs text-slate-500">{p.reference_no}</span></Td>
                        <Td right>{formatINR(p.amount)}</Td>
                      </tr>
                    ))}
                  </TBody>
                </Table>
              )}
            </Card>
          )}
        </div>

        <Card title="History" subtitle="This PO and its invoices"><StatusTimeline entries={po.timeline} showEntity /></Card>
      </div>
    </>
  );
}
