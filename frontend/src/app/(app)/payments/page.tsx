"use client";

import { Suspense } from "react";

import { DateFilter, FilterBar, useUrlFilters } from "@/components/ListFilters";
import { Select } from "@/components/ui/Form";
import { Card, PageHeader } from "@/components/ui/Layout";
import { EmptyState, ErrorState, Loading } from "@/components/ui/States";
import { DocLink, Pagination, RowLink, Table, TBody, Td, Th, THead } from "@/components/ui/Table";
import { api } from "@/lib/api";
import { formatDate, formatINR } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { PaymentMode } from "@/types/api";

function PaymentList() {
  const f = useUrlFilters();
  const query = f.params.toString();
  const { data, error, loading, reload } = useApi(
    () => api.payments.list({ page: f.page, page_size: 15, mode: (f.get("mode") || undefined) as PaymentMode | undefined,
                              paid_from: f.get("from"), paid_to: f.get("to") }),
    [query],
  );
  return (
    <>
      <PageHeader title="Payments" subtitle="Payments recorded against matched invoices. To pay, open the invoice." />
      <Card padded={false}>
        <FilterBar>
          <label className="block w-40">
            <span className="mb-1 block text-xs font-medium text-slate-500">Mode</span>
            <Select value={f.get("mode")} onChange={(e) => f.set({ mode: e.target.value || null })}>
              <option value="">All modes</option><option value="NEFT">NEFT</option><option value="CHEQUE">Cheque</option><option value="UPI">UPI</option>
            </Select>
          </label>
          <DateFilter label="Paid from" value={f.get("from")} onChange={(v) => f.set({ from: v })} />
          <DateFilter label="Paid to" value={f.get("to")} onChange={(v) => f.set({ to: v })} />
        </FilterBar>
        {loading && !data ? <Loading /> : error ? <ErrorState error={error} onRetry={reload} /> : data && (
          data.items.length === 0 ? <EmptyState icon="rupee" title="No payments match" /> : (
            <>
              <Table>
                <THead><Th>Paid on</Th><Th>Invoice</Th><Th>Supplier</Th><Th>PO</Th><Th>Mode</Th><Th>Reference</Th><Th>Recorded by</Th><Th right>Amount</Th></THead>
                <TBody>
                  {data.items.map((p) => (
                    <RowLink key={p.id} href={`/invoices/${p.invoice_id}`}>
                      <Td>{formatDate(p.paid_on)}</Td>
                      <Td><DocLink href={`/invoices/${p.invoice_id}`}>{p.supplier_invoice_number}</DocLink></Td>
                      <Td>{p.supplier.name}</Td>
                      <Td>{p.po_number}</Td>
                      <Td>{p.mode}</Td>
                      <Td className="text-slate-600">{p.reference_no}</Td>
                      <Td>{p.recorded_by.name}</Td>
                      <Td right className="font-medium">{formatINR(p.amount)}</Td>
                    </RowLink>
                  ))}
                </TBody>
              </Table>
              <Pagination page={data.page} pages={data.pages} total={data.total} onPage={(p) => f.set({ page: String(p) })} />
            </>
          )
        )}
      </Card>
    </>
  );
}

export default function PaymentListPage() {
  return <Suspense fallback={<Loading />}><PaymentList /></Suspense>;
}
