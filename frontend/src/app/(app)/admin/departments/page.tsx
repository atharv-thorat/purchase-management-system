"use client";

import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { Field, Input } from "@/components/ui/Form";
import { Card, PageHeader } from "@/components/ui/Layout";
import { EmptyState, ErrorState, Loading } from "@/components/ui/States";
import { Table, TBody, Td, Th, THead } from "@/components/ui/Table";
import { api } from "@/lib/api";
import { formatINR } from "@/lib/format";
import { useAction, useApi } from "@/lib/hooks";

export default function DepartmentsPage() {
  const { data, error, loading, reload } = useApi(() => api.masters.departments(), []);
  const { run, busy } = useAction();
  const [editing, setEditing] = useState<{ id: number; budget: string } | null>(null);
  const [form, setForm] = useState({ name: "", monthly_budget: "" });

  return (
    <>
      <PageHeader title="Departments" subtitle="Monthly budgets drive the over-budget warning shown to approvers" />
      <div className="grid gap-6 lg:grid-cols-[1fr_22rem]">
        <Card padded={false}>
          {loading && !data ? <Loading /> : error ? <ErrorState error={error} onRetry={reload} /> : !data?.length ? <EmptyState title="No departments" /> : (
            <Table>
              <THead><Th>Department</Th><Th right>Monthly budget</Th><Th /></THead>
              <TBody>
                {data.map((d) => (
                  <tr key={d.id}>
                    <Td className="font-medium">{d.name}</Td>
                    <Td right>
                      {editing?.id === d.id ? (
                        <Input className="ml-auto w-40 text-right" inputMode="decimal" autoFocus value={editing.budget}
                               onChange={(e) => setEditing({ id: d.id, budget: e.target.value })} aria-label="Monthly budget" />
                      ) : formatINR(d.monthly_budget)}
                    </Td>
                    <Td right className="w-40">
                      {editing?.id === d.id ? (
                        <div className="flex justify-end gap-2">
                          <Button size="sm" variant="secondary" onClick={() => setEditing(null)}>Cancel</Button>
                          <Button size="sm" loading={busy === "save"} onClick={async () => {
                            const r = await run("save", () => api.masters.updateDepartment(d.id, { monthly_budget: editing.budget }), `${d.name} budget updated`);
                            if (r) { setEditing(null); void reload(); }
                          }}>Save</Button>
                        </div>
                      ) : <Button size="sm" variant="ghost" icon="pencil" onClick={() => setEditing({ id: d.id, budget: d.monthly_budget })}>Edit budget</Button>}
                    </Td>
                  </tr>
                ))}
              </TBody>
            </Table>
          )}
        </Card>
        <Card title="Add department">
          <form className="space-y-4" onSubmit={async (e) => {
            e.preventDefault();
            const r = await run("add", () => api.masters.createDepartment(form), (x) => `${x.name} added`);
            if (r) { setForm({ name: "", monthly_budget: "" }); void reload(); }
          }}>
            <Field label="Name" required><Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></Field>
            <Field label="Monthly budget (₹)" required><Input inputMode="decimal" value={form.monthly_budget} onChange={(e) => setForm({ ...form, monthly_budget: e.target.value })} /></Field>
            <Button type="submit" icon="plus" loading={busy === "add"} className="w-full">Add department</Button>
          </form>
        </Card>
      </div>
    </>
  );
}
