"use client";

import { useParams } from "next/navigation";

import { StatusBadge } from "@/components/StatusBadge";
import { Card, Facts, PageHeader } from "@/components/ui/Layout";
import { ErrorState, Loading } from "@/components/ui/States";
import { DocLink, Table, TBody, Td, Th, THead } from "@/components/ui/Table";
import { api } from "@/lib/api";
import { formatDate, formatDateTime, formatQty } from "@/lib/format";
import { useApi } from "@/lib/hooks";

export default function GRNDetailPage() {
  const id = Number(useParams<{ id: string }>().id);
  const { data: grn, error, loading, reload } = useApi(() => api.grns.get(id), [id]);
  if (loading && !grn) return <Loading />;
  if (error || !grn) return error ? <ErrorState error={error} onRetry={reload} /> : null;
  return (
    <>
      <PageHeader title={grn.grn_number} back={{ href: "/grns", label: "Goods receipts" }}
                  subtitle={<>Against <DocLink href={`/pos/${grn.po.id}`}>{grn.po.po_number}</DocLink> <StatusBadge status={grn.po.status} size="sm" /> · {grn.po.supplier.name}</>} />
      <div className="space-y-6">
        <Card>
          <Facts items={[
            ["Received on", formatDate(grn.received_date)],
            ["Received by", grn.received_by.name],
            ["Recorded", formatDateTime(grn.created_at)],
            ["Remarks", grn.remarks ?? "—"],
          ]} />
        </Card>
        <Card title="Lines" padded={false}>
          <Table>
            <THead><Th>Item</Th><Th right>Received</Th><Th right>Accepted</Th><Th right>Rejected</Th><Th>Rejection reason</Th></THead>
            <TBody>
              {grn.lines.map((l) => (
                <tr key={l.id}>
                  <Td className="font-medium">{l.item.name}</Td>
                  <Td right>{formatQty(l.qty_received, l.item.unit)}</Td>
                  <Td right className="font-medium text-emerald-700">{formatQty(l.qty_accepted, l.item.unit)}</Td>
                  <Td right className={l.qty_rejected !== "0.000" ? "font-medium text-red-700" : "text-slate-400"}>{formatQty(l.qty_rejected, l.item.unit)}</Td>
                  <Td className="text-slate-600">{l.rejection_reason ?? "—"}</Td>
                </tr>
              ))}
            </TBody>
          </Table>
        </Card>
      </div>
    </>
  );
}
