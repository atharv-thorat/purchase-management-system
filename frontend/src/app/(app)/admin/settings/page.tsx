"use client";

import { useEffect, useState } from "react";

import { Button } from "@/components/ui/Button";
import { Field, Input } from "@/components/ui/Form";
import { Card, PageHeader } from "@/components/ui/Layout";
import { ErrorState, Loading } from "@/components/ui/States";
import { api } from "@/lib/api";
import { formatINR } from "@/lib/format";
import { useAction, useApi } from "@/lib/hooks";

const THRESHOLD = "FINANCE_APPROVAL_THRESHOLD";

export default function SettingsPage() {
  const { data, error, loading, reload } = useApi(() => api.masters.settings(), []);
  const { run, busy } = useAction();
  const current = data?.find((s) => s.key === THRESHOLD)?.value ?? "";
  const [value, setValue] = useState("");
  useEffect(() => setValue(current), [current]);

  if (loading && !data) return <Loading />;
  if (error) return <ErrorState error={error} onRetry={reload} />;
  return (
    <>
      <PageHeader title="Settings" />
      <Card title="Finance approval threshold" className="max-w-2xl">
        <p className="mb-4 text-slate-600">
          Requests above this amount need Finance approval after the department head. Currently <strong>{formatINR(current)}</strong>.
          A change applies to requests the department head approves from now on.
        </p>
        <form className="flex items-end gap-3" onSubmit={async (e) => {
          e.preventDefault();
          const r = await run("save", () => api.masters.putSetting(THRESHOLD, value), (s) => `Threshold set to ${formatINR(s.value)}`);
          if (r) void reload();
        }}>
          <Field label="Threshold (₹)" className="w-56"><Input inputMode="decimal" value={value} onChange={(e) => setValue(e.target.value)} /></Field>
          <Button type="submit" loading={busy === "save"}>Save</Button>
        </form>
      </Card>
    </>
  );
}
