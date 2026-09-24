"use client";

import { useState } from "react";
import { useParams, useRouter } from "next/navigation";

import { Icon } from "@/components/Icon";
import { ReasonDialog } from "@/components/ReasonDialog";
import { StatusBadge } from "@/components/StatusBadge";
import { StatusTimeline } from "@/components/StatusTimeline";
import { Button, ButtonLink } from "@/components/ui/Button";
import { Card, Facts, Notice, PageHeader } from "@/components/ui/Layout";
import { Modal } from "@/components/ui/Modal";
import { ErrorState, Loading } from "@/components/ui/States";
import { DocLink, Table, TBody, Td, Th, THead } from "@/components/ui/Table";
import { api } from "@/lib/api";
import { formatDate, formatDateTime, formatINR, formatQty, humanize, ROLE_LABELS } from "@/lib/format";
import { useAction, useApi } from "@/lib/hooks";
import type { Budget, PRDetail } from "@/types/api";

function BudgetPanel({ budget }: { budget: Budget }) {
  const rows: [string, string][] = [
    [`${budget.department} budget this month`, formatINR(budget.monthly_budget)],
    ["Already approved this month", formatINR(budget.approved_this_month)],
    ["This request", formatINR(budget.this_request)],
    ["Projected", formatINR(budget.projected)],
  ];
  return (
    <div className="space-y-3">
      {budget.over_budget ? (
        <Notice tone="danger" icon="alert" title="Over budget">
          Approving takes {budget.department} to {formatINR(budget.projected)} against a budget of {formatINR(budget.monthly_budget)}.
          You can still approve; the warning is recorded with your approval.
        </Notice>
      ) : (
        <Notice tone="success" icon="checkCircle" title="Within budget">
          {formatINR(budget.remaining_after)} of the {budget.department} budget remains after this request.
        </Notice>
      )}
      <dl className="grid grid-cols-2 gap-3 text-sm lg:grid-cols-4">
        {rows.map(([k, v]) => (
          <div key={k} className="rounded-lg bg-slate-50 px-3 py-2">
            <dt className="text-slate-500">{k}</dt>
            <dd className="mt-0.5 font-semibold tabular-nums text-slate-900">{v}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

type Dialog = null | "approve" | "reject" | "delete";

function Actions({ pr, onChange }: { pr: PRDetail; onChange: (pr: PRDetail) => void }) {
  const router = useRouter();
  const { run, busy } = useAction();
  const [dialog, setDialog] = useState<Dialog>(null);
  const has = (a: string) => pr.actions.includes(a as never);
  const act = async (key: string, call: () => Promise<PRDetail>, message: (p: PRDetail) => string) => {
    const result = await run(key, call, message);
    if (result) onChange(result);
    return Boolean(result);
  };

  return (
    <>
      {has("edit") && <ButtonLink href={`/prs/${pr.id}/edit`} variant="secondary" icon="pencil">Edit</ButtonLink>}
      {has("delete") && <Button variant="danger" icon="trash" onClick={() => setDialog("delete")}>Delete</Button>}
      {(has("submit") || has("resubmit")) && (
        <Button icon="send" loading={busy === "submit"}
                onClick={() => act("submit", () => api.prs.submit(pr.id), (p) => `${p.pr_number} submitted — now ${humanize(p.status).toLowerCase()}`)}>
          {has("resubmit") ? "Resubmit" : "Submit for approval"}
        </Button>
      )}
      {has("reject") && <Button variant="danger" icon="xCircle" onClick={() => setDialog("reject")}>Reject</Button>}
      {has("approve") && <Button variant="success" icon="check" onClick={() => setDialog("approve")}>Approve</Button>}
      {(has("add_quotation") || has("select_quotation")) && (
        <ButtonLink href={`/prs/${pr.id}/quotations`} icon="scale">Quotations & PO</ButtonLink>
      )}
      {!has("add_quotation") && !has("select_quotation") && (pr.quotation_count ?? 0) > 0 && (
        <ButtonLink href={`/prs/${pr.id}/quotations`} variant="secondary" icon="scale">View quotations ({pr.quotation_count})</ButtonLink>
      )}

      <ReasonDialog open={dialog === "approve"} title={`Approve ${pr.pr_number}`} label="Comment (optional)" required={false}
                    confirmLabel="Approve" variant="success" onClose={() => setDialog(null)}
                    intro={pr.budget?.over_budget ? <Notice tone="danger" icon="alert" title="This request is over budget">It will be approved with the warning recorded.</Notice> : undefined}
                    onConfirm={(text) => act("approve", () => api.prs.approve(pr.id, text), (p) => `${p.pr_number} approved — now ${humanize(p.status).toLowerCase()}`)} />
      <ReasonDialog open={dialog === "reject"} title={`Reject ${pr.pr_number}`} label="Reason for rejection" confirmLabel="Reject"
                    variant="danger" onClose={() => setDialog(null)} intro="The requester sees this comment and can edit and resubmit."
                    onConfirm={(text) => act("reject", () => api.prs.reject(pr.id, text), (p) => `${p.pr_number} rejected`)} />
      <Modal open={dialog === "delete"} title={`Delete ${pr.pr_number}?`} onClose={() => setDialog(null)} footer={
        <>
          <Button variant="secondary" onClick={() => setDialog(null)}>Keep it</Button>
          <Button variant="danger" loading={busy === "delete"} onClick={async () => {
            const deleted = await run("delete", async () => { await api.prs.remove(pr.id); return true; }, `${pr.pr_number} deleted`);
            if (deleted) router.push("/prs");
          }}>Delete draft</Button>
        </>
      }>
        <p className="text-slate-600">This draft will be removed. This can&apos;t be undone.</p>
      </Modal>
    </>
  );
}

export default function PRDetailPage() {
  const id = Number(useParams<{ id: string }>().id);
  const { data: pr, error, loading, reload, setData } = useApi(() => api.prs.get(id), [id]);

  if (loading && !pr) return <Loading />;
  if (error || !pr) return error ? <ErrorState error={error} onRetry={reload} /> : null;

  return (
    <>
      <PageHeader title={pr.pr_number} badge={<StatusBadge status={pr.status} size="lg" />} back={{ href: "/prs", label: "Requests" }}
                  subtitle={pr.justification} actions={<Actions pr={pr} onChange={setData} />} />

      <div className="space-y-6">
        {pr.status === "REJECTED" && pr.rejection_reason && (
          <Notice tone="danger" icon="xCircle" title="Rejected">
            “{pr.rejection_reason}”{pr.actions.includes("edit") && " — edit the request and resubmit; the approval chain starts again."}
          </Notice>
        )}
        {pr.status === "PENDING_FINANCE" && pr.requester.role === "DEPT_HEAD" && (
          <Notice tone="info" title="Raised by a department head">Goes straight to Finance for approval, whatever the amount.</Notice>
        )}

        <Card>
          <Facts items={[
            ["Raised by", <>{pr.requester.name} <span className="text-slate-500">({ROLE_LABELS[pr.requester.role]})</span></>],
            ["Department", pr.department.name],
            ["Estimated total", <span key="t" className="font-semibold">{formatINR(pr.estimated_total)}</span>],
            ["Needed by", formatDate(pr.required_by)],
            ["Created", formatDateTime(pr.created_at)],
            ["Submitted", formatDateTime(pr.submitted_at)],
            ["Final approval", formatDateTime(pr.final_approved_at)],
            ["Purchase orders", pr.purchase_orders === null ? "—" : pr.purchase_orders.length === 0 ? "None yet" :
              <span className="flex flex-wrap gap-2">{pr.purchase_orders.map((po) => (
                <span key={po.id} className="inline-flex items-center gap-1.5"><DocLink href={`/pos/${po.id}`}>{po.po_number}</DocLink><StatusBadge status={po.status} size="sm" /></span>
              ))}</span>],
          ]} />
        </Card>

        {pr.budget && <Card title="Budget check" subtitle="Month to date, for approvers">{<BudgetPanel budget={pr.budget} />}</Card>}

        <Card title="Items" padded={false}>
          <Table>
            <THead><Th>Item</Th><Th>Category</Th><Th right>Quantity</Th><Th right>Est. unit price</Th><Th right>Line total</Th></THead>
            <TBody>
              {pr.lines.map((l) => (
                <tr key={l.id}>
                  <Td className="font-medium">{l.item.name}</Td>
                  <Td className="text-slate-500">{l.item.category}</Td>
                  <Td right>{formatQty(l.quantity, l.item.unit)}</Td>
                  <Td right>{formatINR(l.estimated_unit_price)}</Td>
                  <Td right>{formatINR(l.line_total)}</Td>
                </tr>
              ))}
              <tr className="bg-slate-50/60">
                <Td className="font-medium" /><Td /><Td /><Td right className="font-medium text-slate-600">Total</Td>
                <Td right className="font-semibold">{formatINR(pr.estimated_total)}</Td>
              </tr>
            </TBody>
          </Table>
        </Card>

        <div className="grid gap-6 lg:grid-cols-2">
          <Card title="Approvals">
            {pr.approvals.length === 0 ? <p className="text-sm text-slate-500">No approval decisions yet.</p> : (
              <ul className="space-y-4">
                {pr.approvals.map((a, i) => (
                  <li key={i} className="flex gap-3">
                    <span className={`mt-0.5 rounded-full p-1 ${a.action === "APPROVED" ? "bg-emerald-50 text-emerald-600" : "bg-red-50 text-red-600"}`}>
                      <Icon name={a.action === "APPROVED" ? "check" : "xCircle"} className="h-5 w-5" />
                    </span>
                    <div>
                      <p className="font-medium text-slate-900">
                        {a.action === "APPROVED" ? "Approved" : "Rejected"} at {a.level === "DEPT_HEAD" ? "department head" : "finance"} level
                      </p>
                      <p className="text-sm text-slate-500">{a.approver.name} · {formatDateTime(a.at)}</p>
                      {a.comment && <p className="mt-1 text-sm text-slate-700">“{a.comment}”</p>}
                      {a.over_budget && <p className="mt-1 inline-flex items-center gap-1 text-sm font-medium text-red-700"><Icon name="alert" className="h-4 w-4" />Over-budget warning was shown</p>}
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </Card>
          <Card title="Status history"><StatusTimeline entries={pr.timeline} /></Card>
        </div>
      </div>
    </>
  );
}
