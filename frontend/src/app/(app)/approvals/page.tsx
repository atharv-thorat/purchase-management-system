"use client";

import { Icon } from "@/components/Icon";
import { StatusBadge } from "@/components/StatusBadge";
import { Card, PageHeader } from "@/components/ui/Layout";
import { EmptyState, ErrorState, Loading } from "@/components/ui/States";
import { DocLink, RowLink, Table, TBody, Td, Th, THead } from "@/components/ui/Table";
import { api } from "@/lib/api";
import { formatDate, formatDateTime, formatINR } from "@/lib/format";
import { useApi } from "@/lib/hooks";

export default function ApprovalsPage() {
  const { data, error, loading, reload } = useApi(() => api.prs.pendingApprovals(), []);
  return (
    <>
      <PageHeader title="Approvals" subtitle="Purchase requests waiting for your decision. Open one to approve or reject." />
      <Card padded={false}>
        {loading && !data ? <Loading /> : error ? <ErrorState error={error} onRetry={reload} /> : data && (
          data.length === 0 ? <EmptyState icon="check" title="You're all caught up">Nothing is waiting for your approval.</EmptyState> : (
            <Table>
              <THead><Th>Request</Th><Th>Level</Th><Th>Justification</Th><Th>Raised by</Th><Th right>Amount</Th><Th>Budget</Th><Th>Submitted</Th><Th>Needed by</Th></THead>
              <TBody>
                {data.map((p) => (
                  <RowLink key={p.id} href={`/prs/${p.id}`}>
                    <Td><DocLink href={`/prs/${p.id}`}>{p.pr_number}</DocLink></Td>
                    <Td><StatusBadge status={p.status} /></Td>
                    <Td className="max-w-xs truncate text-slate-600">{p.justification}</Td>
                    <Td>{p.requester.name}<div className="text-xs text-slate-500">{p.department.name}</div></Td>
                    <Td right className="font-medium">{formatINR(p.estimated_total)}</Td>
                    <Td>
                      {p.budget.over_budget ? (
                        <span className="inline-flex items-center gap-1 rounded-full bg-red-50 px-2 py-0.5 text-xs font-semibold text-red-700 ring-1 ring-red-600/20">
                          <Icon name="alert" className="h-3.5 w-3.5" /> Over budget
                        </span>
                      ) : <span className="text-xs text-slate-500">Within budget</span>}
                    </Td>
                    <Td className="whitespace-nowrap text-slate-600">{formatDateTime(p.submitted_at)}</Td>
                    <Td className="whitespace-nowrap">{formatDate(p.required_by)}</Td>
                  </RowLink>
                ))}
              </TBody>
            </Table>
          )
        )}
      </Card>
    </>
  );
}
