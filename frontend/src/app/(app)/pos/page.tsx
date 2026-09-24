"use client";

import { Suspense } from "react";

import { DateFilter, FilterBar, SearchFilter, StatusFilter, useUrlFilters } from "@/components/ListFilters";
import { StatusBadge } from "@/components/StatusBadge";
import { Select } from "@/components/ui/Form";
import { Card, PageHeader } from "@/components/ui/Layout";
import { EmptyState, ErrorState, Loading } from "@/components/ui/States";
import { DocLink, Pagination, RowLink, Table, TBody, Td, Th, THead } from "@/components/ui/Table";
import { api } from "@/lib/api";
import { useUser } from "@/lib/auth";
import { formatDate, formatINR } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { POStatus } from "@/types/api";

const STATUSES: POStatus[] = ["ISSUED", "PARTIALLY_RECEIVED", "FULLY_RECEIVED", "SHORT_CLOSED", "CLOSED", "CANCELLED"];

function POList() {
  const user = useUser();
  const f = useUrlFilters();
  const query = f.params.toString();
  const departments = useApi(() => api.masters.departments(), []);
  const { data, error, loading, reload } = useApi(
    () => api.pos.list({
      page: f.page, page_size: 15, status: f.statuses as POStatus[], q: f.get("q"),
      department_id: f.get("department") ? Number(f.get("department")) : undefined,
      created_from: f.get("from"), created_to: f.get("to"),
    }),
    [query],
  );
  const showDept = !["REQUESTER", "DEPT_HEAD"].includes(user.role);

  return (
    <>
      <PageHeader title="Purchase orders"
                  subtitle={user.role === "STORE" ? "Open a PO to record goods received against it" : user.role === "ACCOUNTS" ? "Open a received PO to enter the supplier's invoice" : undefined} />
      <Card padded={false}>
        <FilterBar>
          <StatusFilter options={STATUSES} value={f.statuses} onChange={(v) => f.set({ status: v })} />
          <SearchFilter value={f.get("q")} placeholder="PO number" onChange={(v) => f.set({ q: v })} />
          {showDept && (
            <label className="block w-44">
              <span className="mb-1 block text-xs font-medium text-slate-500">Department</span>
              <Select value={f.get("department")} onChange={(e) => f.set({ department: e.target.value || null })}>
                <option value="">All departments</option>
                {departments.data?.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
              </Select>
            </label>
          )}
          <DateFilter label="Issued from" value={f.get("from")} onChange={(v) => f.set({ from: v })} />
          <DateFilter label="Issued to" value={f.get("to")} onChange={(v) => f.set({ to: v })} />
        </FilterBar>
        {loading && !data ? <Loading /> : error ? <ErrorState error={error} onRetry={reload} /> : data && (
          data.items.length === 0 ? <EmptyState icon="cart" title="No purchase orders match">Try clearing the filters.</EmptyState> : (
            <>
              <Table>
                <THead><Th>PO</Th><Th>Status</Th><Th>Supplier</Th><Th>Request</Th><Th>Department</Th><Th right>Total</Th><Th>Issued</Th></THead>
                <TBody>
                  {data.items.map((po) => (
                    <RowLink key={po.id} href={`/pos/${po.id}`}>
                      <Td><DocLink href={`/pos/${po.id}`}>{po.po_number}</DocLink></Td>
                      <Td><StatusBadge status={po.status} /></Td>
                      <Td>{po.supplier.name}</Td>
                      <Td>{po.pr.pr_number}</Td>
                      <Td>{po.pr.department.name}</Td>
                      <Td right>{formatINR(po.total)}</Td>
                      <Td>{formatDate(po.created_at)}</Td>
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

export default function POListPage() {
  return <Suspense fallback={<Loading />}><POList /></Suspense>;
}
