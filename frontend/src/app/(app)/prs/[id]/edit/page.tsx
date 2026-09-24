"use client";

import { useParams, useRouter } from "next/navigation";

import { PRForm } from "@/components/PRForm";
import { StatusBadge } from "@/components/StatusBadge";
import { Notice, PageHeader } from "@/components/ui/Layout";
import { ErrorState, Loading } from "@/components/ui/States";
import { api } from "@/lib/api";
import { trimZeros } from "@/lib/format";
import { useAction, useApi } from "@/lib/hooks";

export default function EditPRPage() {
  const id = Number(useParams<{ id: string }>().id);
  const router = useRouter();
  const { run } = useAction();
  const { data: pr, error, loading } = useApi(() => api.prs.get(id), [id]);

  if (loading && !pr) return <Loading />;
  if (error || !pr) return error ? <ErrorState error={error} /> : null;
  if (!pr.actions.includes("edit")) {
    return (
      <>
        <PageHeader title={`Edit ${pr.pr_number}`} badge={<StatusBadge status={pr.status} size="lg" />}
                    back={{ href: `/prs/${id}`, label: pr.pr_number }} />
        <Notice tone="info" title="This request can't be edited">Only its requester can edit it, and only while it is a draft or rejected.</Notice>
      </>
    );
  }
  return (
    <>
      <PageHeader title={`Edit ${pr.pr_number}`} badge={<StatusBadge status={pr.status} size="lg" />}
                  back={{ href: `/prs/${id}`, label: pr.pr_number }} />
      {pr.rejection_reason && (
        <div className="mb-6"><Notice tone="danger" icon="xCircle" title="Rejected — address this before resubmitting">{pr.rejection_reason}</Notice></div>
      )}
      <PRForm submitLabel="Save changes"
              initial={{ justification: pr.justification, required_by: pr.required_by,
                         lines: pr.lines.map((l) => ({ item_id: l.item.id, quantity: trimZeros(l.quantity), estimated_unit_price: l.estimated_unit_price })) }}
              onSubmit={async (body) => {
                const saved = await run("save", () => api.prs.update(id, body), "Changes saved");
                if (saved) router.push(`/prs/${id}`);
              }} />
    </>
  );
}
