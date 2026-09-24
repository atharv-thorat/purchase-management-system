"use client";

import { Suspense } from "react";

import { DateFilter, FilterBar, SearchFilter, StatusFilter, useUrlFilters } from "@/components/ListFilters";
import { StatusBadge } from "@/components/StatusBadge";
import { ButtonLink } from "@/components/ui/Button";
import { Card, PageHeader } from "@/components/ui/Layout";
import { EmptyState, ErrorState, Loading } from "@/components/ui/States";
import { DocLink, Pagination, RowLink, Table, TBody, Td, Th, THead } from "@/components/ui/Table";
import { api } from "@/lib/api";
import { useUser } from "@/lib/auth";
import { formatDate, formatINR } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import { RAISES_PRS } from "@/lib/nav";
import type { PRStatus } from "@/types/api";

const STATUSES: PRStatus[] = ["DRAFT", "PENDING_DEPT_HEAD", "PENDING_FINANCE", "APPROVED", "PO_CREATED", "REJECTED"];

function PRList() {
  const user = useUser();
  const f = useUrlFilters();
  const mine = f.get("mine") === "1";
  const query = f.params.toString();
  const { data, error, loading, reload } = useApi(
    () => api.prs.list({
      page: f.page, page_size: 15, status: f.statuses as PRStatus[], mine: mine || undefined, q: f.get("q"),
      created_from: f.get("from"), created_to: f.get("to"),
    }),
    [query],
  );
  const title = { REQUESTER: "My requests", DEPT_HEAD: "Department requests", PURCHASE: "Approved requests" }[user.role as string] ?? "Purchase requests";

  return (
    <>
      <PageHeader title={title}
                  subtitle={user.role === "PURCHASE" ? "Approved requests ready for quotations, and those already on a PO" : undefined}
                  actions={RAISES_PRS.includes(user.role) && <ButtonLink href="/prs/new" icon="plus">New request</ButtonLink>} />
      <Card padded={false}>
        <FilterBar>
          <StatusFilter options={STATUSES} value={f.statuses} onChange={(v) => f.set({ status: v })} />
          <SearchFilter value={f.get("q")} placeholder="PR number or justification" onChange={(v) => f.set({ q: v })} />
          <DateFilter label="Created from" value={f.get("from")} onChange={(v) => f.set({ from: v })} />
          <DateFilter label="Created to" value={f.get("to")} onChange={(v) => f.set({ to: v })} />
          {RAISES_PRS.includes(user.role) && user.role !== "REQUESTER" && (
            <label className="flex h-10 items-center gap-2 text-sm text-slate-700">
              <input type="checkbox" checked={mine} onChange={(e) => f.set({ mine: e.target.checked ? "1" : null })}
                     className="h-4 w-4 rounded border-slate-300 text-brand-600" />
              Only mine
            </label>
          )}
        </FilterBar>
        {loading && !data ? <Loading /> : error ? <ErrorState error={error} onRetry={reload} /> : data && (
          data.items.length === 0 ? <EmptyState icon="doc" title="No purchase requests match">Try clearing the filters.</EmptyState> : (
            <>
              <Table>
                <THead><Th>Request</Th><Th>Status</Th><Th>Justification</Th><Th>Raised by</Th><Th>Department</Th><Th right>Estimated</Th><Th>Needed by</Th></THead>
                <TBody>
                  {data.items.map((pr) => (
                    <RowLink key={pr.id} href={`/prs/${pr.id}`}>
                      <Td><DocLink href={`/prs/${pr.id}`}>{pr.pr_number}</DocLink></Td>
                      <Td><StatusBadge status={pr.status} /></Td>
                      <Td className="max-w-xs truncate text-slate-600">{pr.justification}</Td>
                      <Td>{pr.requester.name}</Td>
                      <Td>{pr.department.name}</Td>
                      <Td right>{formatINR(pr.estimated_total)}</Td>
                      <Td>{formatDate(pr.required_by)}</Td>
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

export default function PRListPage() {
  return <Suspense fallback={<Loading />}><PRList /></Suspense>;
}
