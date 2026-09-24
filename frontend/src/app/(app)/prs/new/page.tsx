"use client";

import { useRouter } from "next/navigation";

import { PRForm } from "@/components/PRForm";
import { PageHeader } from "@/components/ui/Layout";
import { api } from "@/lib/api";
import { useAction } from "@/lib/hooks";

export default function NewPRPage() {
  const router = useRouter();
  const { run } = useAction();
  return (
    <>
      <PageHeader title="New purchase request" back={{ href: "/prs", label: "Requests" }}
                  subtitle="Saved as a draft. Submit it from the next screen when it's ready." />
      <PRForm submitLabel="Save draft" onSubmit={async (body) => {
        const pr = await run("create", () => api.prs.create(body), (p) => `${p.pr_number} saved as a draft`);
        if (pr) router.push(`/prs/${pr.id}`);
      }} />
    </>
  );
}
