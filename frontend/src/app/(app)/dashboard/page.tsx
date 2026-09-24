"use client";

import Link from "next/link";

import { Icon } from "@/components/Icon";
import { SpendChart } from "@/components/SpendChart";
import { StatusBadge } from "@/components/StatusBadge";
import { StatusTimeline } from "@/components/StatusTimeline";
import { ButtonLink } from "@/components/ui/Button";
import { Card, PageHeader } from "@/components/ui/Layout";
import { EmptyState, ErrorState, Loading } from "@/components/ui/States";
import { DocLink, RowLink, Table, TBody, Td, Th, THead } from "@/components/ui/Table";
import { api } from "@/lib/api";
import { useUser } from "@/lib/auth";
import { formatDate, formatINR, humanize, ROLE_LABELS, todayISO } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import { RAISES_PRS } from "@/lib/nav";
import { BADGE_CLASSES, toneOf } from "@/lib/status";
import type { Dashboard, InvoiceListItem, POStatus, PRStatus } from "@/types/api";

const PO_ORDER: POStatus[] = ["ISSUED", "PARTIALLY_RECEIVED", "FULLY_RECEIVED", "SHORT_CLOSED", "CLOSED", "CANCELLED"];
const PR_ORDER: PRStatus[] = ["DRAFT", "PENDING_DEPT_HEAD", "PENDING_FINANCE", "APPROVED", "PO_CREATED", "REJECTED"];

function StatTile({ label, value, href, tone }: { label: string; value: React.ReactNode; href?: string; tone?: "warning" | "danger" }) {
  const body = (
    <div className={`h-full rounded-xl border bg-white p-5 shadow-sm transition ${href ? "hover:border-brand-500" : ""} ${
      tone === "danger" ? "border-red-200" : tone === "warning" ? "border-amber-200" : "border-slate-200"}`}>
      <p className="text-sm text-slate-500">{label}</p>
      <p className="mt-2 text-3xl font-semibold text-slate-900">{value}</p>
    </div>
  );
  return href ? <Link href={href}>{body}</Link> : body;
}

function StatusCounts({ counts, order, hrefBase }: { counts: Record<string, number>; order: string[]; hrefBase: string }) {
  const total = order.reduce((sum, s) => sum + (counts[s] ?? 0), 0);
  if (!total) return <EmptyState title="Nothing here yet" />;
  return (
    <ul className="grid grid-cols-2 gap-3 sm:grid-cols-3">
      {order.filter((s) => counts[s]).map((s) => (
        <li key={s}>
          <Link href={`${hrefBase}?status=${s}`}
                className={`flex items-center justify-between rounded-lg px-3 py-2.5 ring-1 ring-inset hover:opacity-80 ${BADGE_CLASSES[toneOf(s)]}`}>
            <span className="text-sm font-medium">{humanize(s)}</span>
            <span className="text-lg font-semibold tabular-nums">{counts[s]}</span>
          </Link>
        </li>
      ))}
    </ul>
  );
}

function InvoiceTable({ invoices, showBalance }: { invoices: InvoiceListItem[]; showBalance?: boolean }) {
  return (
    <Table>
      <THead><Th>Invoice</Th><Th>PO</Th><Th>Status</Th><Th right>{showBalance ? "Balance due" : "Total"}</Th></THead>
      <TBody>
        {invoices.map((i) => (
          <RowLink key={i.id} href={`/invoices/${i.id}`}>
            <Td><DocLink href={`/invoices/${i.id}`}>{i.supplier_invoice_number}</DocLink>
              <div className="text-xs text-slate-500">{i.supplier.name}</div></Td>
            <Td className="whitespace-nowrap">{i.po.po_number}</Td>
            <Td><StatusBadge status={i.status} /></Td>
            <Td right>{formatINR(showBalance ? i.balance_due : i.total)}</Td>
          </RowLink>
        ))}
      </TBody>
    </Table>
  );
}

function Widgets({ d }: { d: Dashboard }) {
  const user = useUser();
  const tiles: React.ReactNode[] = [];
  if (d.pending_approvals) tiles.push(<StatTile key="a" label="Waiting for your approval" value={d.pending_approvals.length} href="/approvals" tone={d.pending_approvals.length ? "warning" : undefined} />);
  if (d.my_requests) {
    const open = d.my_requests.DRAFT + d.my_requests.PENDING_DEPT_HEAD + d.my_requests.PENDING_FINANCE;
    tiles.push(<StatTile key="m" label="My requests in progress" value={open} href="/prs?mine=1" />);
  }
  if (d.pos_by_status) {
    const open = (d.pos_by_status.ISSUED ?? 0) + (d.pos_by_status.PARTIALLY_RECEIVED ?? 0);
    tiles.push(<StatTile key="p" label="POs awaiting delivery" value={open} href="/pos?status=ISSUED&status=PARTIALLY_RECEIVED" />);
  }
  if (d.mismatch_invoices) tiles.push(<StatTile key="x" label="Invoices in mismatch" value={d.mismatch_invoices.length} href="/invoices?status=MISMATCH" tone={d.mismatch_invoices.length ? "danger" : undefined} />);
  if (d.pending_payments) tiles.push(<StatTile key="$" label={`Payments due (${d.pending_payments.count})`} value={formatINR(d.pending_payments.total_due)} href="/invoices?status=MATCHED&status=PARTIALLY_PAID" />);

  return (
    <div className="space-y-6">
      {tiles.length > 0 && <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">{tiles}</div>}

      {d.pending_approvals && (
        <Card title="Pending approvals" subtitle="Requests waiting for you" padded={false}
              actions={<Link href="/approvals" className="text-sm font-medium text-brand-600 hover:underline">Open inbox</Link>}>
          {d.pending_approvals.length === 0 ? <EmptyState icon="check" title="You're all caught up" /> : (
            <Table>
              <THead><Th>Request</Th><Th>Raised by</Th><Th>Department</Th><Th right>Amount</Th><Th>Budget</Th></THead>
              <TBody>
                {d.pending_approvals.map((p) => (
                  <RowLink key={p.id} href={`/prs/${p.id}`}>
                    <Td><DocLink href={`/prs/${p.id}`}>{p.pr_number}</DocLink></Td>
                    <Td>{p.requester.name}</Td>
                    <Td>{p.department.name}</Td>
                    <Td right>{formatINR(p.estimated_total)}</Td>
                    <Td>{p.budget.over_budget
                      ? <span className="inline-flex items-center gap-1 text-sm font-medium text-red-700"><Icon name="alert" className="h-4 w-4" />Over budget</span>
                      : <span className="text-sm text-slate-500">Within budget</span>}</Td>
                  </RowLink>
                ))}
              </TBody>
            </Table>
          )}
        </Card>
      )}

      {d.spend_vs_budget && (
        <Card title="Spend vs budget this month" subtitle="Approved requests, valued at their PO total once a PO exists">
          <SpendChart data={d.spend_vs_budget} />
        </Card>
      )}

      <div className="grid gap-6 lg:grid-cols-2">
        {d.my_requests && (
          <Card title="My requests" actions={RAISES_PRS.includes(user.role) && <ButtonLink href="/prs/new" size="sm" icon="plus">New request</ButtonLink>}>
            <StatusCounts counts={d.my_requests} order={PR_ORDER} hrefBase="/prs" />
          </Card>
        )}
        {d.pos_by_status && (
          <Card title="Purchase orders by status">
            <StatusCounts counts={d.pos_by_status as Record<string, number>} order={PO_ORDER} hrefBase="/pos" />
          </Card>
        )}
        {d.mismatch_invoices && (
          <Card title="Invoices in mismatch" subtitle="Failed the three-way match" padded={false}>
            {d.mismatch_invoices.length === 0 ? <EmptyState icon="check" title="No mismatched invoices" /> : <InvoiceTable invoices={d.mismatch_invoices} />}
          </Card>
        )}
        {d.pending_payments && (
          <Card title="Pending payments" subtitle="Matched invoices with a balance due" padded={false}>
            {d.pending_payments.invoices.length === 0 ? <EmptyState icon="check" title="Nothing to pay" /> : <InvoiceTable invoices={d.pending_payments.invoices} showBalance />}
          </Card>
        )}
      </div>

      <Card title="Recent activity" subtitle="Latest status changes you can see">
        {d.recent_activity.length === 0 ? <EmptyState title="No activity yet" /> : <StatusTimeline entries={d.recent_activity} showEntity />}
      </Card>
    </div>
  );
}

export default function DashboardPage() {
  const user = useUser();
  const { data, error, loading, reload } = useApi(() => api.dashboard(), []);
  return (
    <>
      <PageHeader title={`Welcome, ${user.name.split(" ")[0]}`}
                  subtitle={`${ROLE_LABELS[user.role]}${user.department ? ` · ${user.department.name}` : ""} · ${formatDate(todayISO())}`} />
      {loading && !data ? <Loading /> : error ? <ErrorState error={error} onRetry={reload} /> : data && <Widgets d={data} />}
    </>
  );
}
