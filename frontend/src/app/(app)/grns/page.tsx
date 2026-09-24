"use client";

import { Suspense } from "react";

import { DateFilter, FilterBar, useUrlFilters } from "@/components/ListFilters";
import { StatusBadge } from "@/components/StatusBadge";
import { Card, PageHeader } from "@/components/ui/Layout";
import { EmptyState, ErrorState, Loading } from "@/components/ui/States";
import { DocLink, Pagination, RowLink, Table, TBody, Td, Th, THead } from "@/components/ui/Table";
import { api } from "@/lib/api";
import { formatDate, formatQty } from "@/lib/format";
import { useApi } from "@/lib/hooks";

function GRNList() {
  const f = useUrlFilters();
  const query = f.params.toString();
  const { data, error, loading, reload } = useApi(
    () => api.grns.list({ page: f.page, page_size: 15, received_from: f.get("from"), received_to: f.get("to") }),
    [query],
  );
  return (
    <>
      <PageHeader title="Goods receipts" subtitle="To record a new receipt, open the purchase order" />
      <Card padded={false}>
        <FilterBar>
          <DateFilter label="Received from" value={f.get("from")} onChange={(v) => f.set({ from: v })} />
          <DateFilter label="Received to" value={f.get("to")} onChange={(v) => f.set({ to: v })} />
        </FilterBar>
        {loading && !data ? <Loading /> : error ? <ErrorState error={error} onRetry={reload} /> : data && (
          data.items.length === 0 ? <EmptyState icon="truck" title="No goods receipts yet" /> : (
            <>
              <Table>
                <THead><Th>GRN</Th><Th>PO</Th><Th>Supplier</Th><Th>Received</Th><Th>By</Th><Th>Accepted</Th></THead>
                <TBody>
                  {data.items.map((g) => (
                    <RowLink key={g.id} href={`/grns/${g.id}`}>
                      <Td><DocLink href={`/grns/${g.id}`}>{g.grn_number}</DocLink></Td>
                      <Td><span className="mr-2">{g.po.po_number}</span><StatusBadge status={g.po.status} size="sm" /></Td>
                      <Td>{g.po.supplier.name}</Td>
                      <Td>{formatDate(g.received_date)}</Td>
                      <Td>{g.received_by.name}</Td>
                      <Td className="text-slate-600">{g.lines.map((l) => `${l.item.name} ${formatQty(l.qty_accepted, l.item.unit)}`).join(", ")}</Td>
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

export default function GRNListPage() {
  return <Suspense fallback={<Loading />}><GRNList /></Suspense>;
}
