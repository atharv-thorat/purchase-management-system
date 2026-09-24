"use client";

import { Suspense } from "react";

import { DateFilter, FilterBar, SearchFilter, StatusFilter, useUrlFilters } from "@/components/ListFilters";
import { StatusBadge } from "@/components/StatusBadge";
import { Card, PageHeader } from "@/components/ui/Layout";
import { EmptyState, ErrorState, Loading } from "@/components/ui/States";
import { DocLink, Pagination, RowLink, Table, TBody, Td, Th, THead } from "@/components/ui/Table";
import { api } from "@/lib/api";
import { formatDate, formatINR } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { InvoiceStatus } from "@/types/api";

const STATUSES: InvoiceStatus[] = ["MATCHED", "MISMATCH", "PARTIALLY_PAID", "PAID", "REJECTED"];

function InvoiceList() {
  const f = useUrlFilters();
  const query = f.params.toString();
  const { data, error, loading, reload } = useApi(
    () => api.invoices.list({ page: f.page, page_size: 15, status: f.statuses as InvoiceStatus[], q: f.get("q"),
                              invoice_from: f.get("from"), invoice_to: f.get("to") }),
    [query],
  );
  return (
    <>
      <PageHeader title="Invoices" subtitle="Supplier invoices and their three-way match result" />
      <Card padded={false}>
        <FilterBar>
          <StatusFilter options={STATUSES} value={f.statuses} onChange={(v) => f.set({ status: v })} />
          <SearchFilter value={f.get("q")} placeholder="Supplier invoice number" onChange={(v) => f.set({ q: v })} />
          <DateFilter label="Invoice date from" value={f.get("from")} onChange={(v) => f.set({ from: v })} />
          <DateFilter label="Invoice date to" value={f.get("to")} onChange={(v) => f.set({ to: v })} />
        </FilterBar>
        {loading && !data ? <Loading /> : error ? <ErrorState error={error} onRetry={reload} /> : data && (
          data.items.length === 0 ? <EmptyState icon="receipt" title="No invoices match">Try clearing the filters.</EmptyState> : (
            <>
              <Table>
                <THead><Th>Invoice</Th><Th>Status</Th><Th>Supplier</Th><Th>PO</Th><Th>Date</Th><Th right>Total</Th><Th right>Balance due</Th></THead>
                <TBody>
                  {data.items.map((i) => (
                    <RowLink key={i.id} href={`/invoices/${i.id}`}>
                      <Td><DocLink href={`/invoices/${i.id}`}>{i.supplier_invoice_number}</DocLink></Td>
                      <Td><StatusBadge status={i.status} /></Td>
                      <Td>{i.supplier.name}</Td>
                      <Td>{i.po.po_number}</Td>
                      <Td>{formatDate(i.invoice_date)}</Td>
                      <Td right>{formatINR(i.total)}</Td>
                      <Td right>{i.status === "REJECTED" ? "—" : formatINR(i.balance_due)}</Td>
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

export default function InvoiceListPage() {
  return <Suspense fallback={<Loading />}><InvoiceList /></Suspense>;
}
