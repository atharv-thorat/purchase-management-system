"use client";

import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { Field, Input, Select } from "@/components/ui/Form";
import { Card, PageHeader } from "@/components/ui/Layout";
import { EmptyState, ErrorState, Loading } from "@/components/ui/States";
import { Table, TBody, Td, Th, THead } from "@/components/ui/Table";
import { api } from "@/lib/api";
import { useUser } from "@/lib/auth";
import { ROLE_LABELS } from "@/lib/format";
import { useAction, useApi } from "@/lib/hooks";
import type { Role } from "@/types/api";

const ROLES = Object.keys(ROLE_LABELS) as Role[];
const blank = { name: "", email: "", password: "", role: "REQUESTER" as Role, department_id: "" };

export default function UsersPage() {
  const me = useUser();
  const users = useApi(() => api.masters.users(), []);
  const departments = useApi(() => api.masters.departments(), []);
  const { run, busy } = useAction();
  const [form, setForm] = useState(blank);

  return (
    <>
      <PageHeader title="Users" subtitle="One role per user. Only requesters and department heads belong to a department." />
      <div className="grid gap-6 lg:grid-cols-[1fr_22rem]">
        <Card padded={false}>
          {users.loading && !users.data ? <Loading /> : users.error ? <ErrorState error={users.error} onRetry={users.reload} /> : !users.data?.length ? <EmptyState title="No users" /> : (
            <Table>
              <THead><Th>Name</Th><Th>Email</Th><Th>Role</Th><Th>Department</Th><Th>Status</Th><Th /></THead>
              <TBody>
                {users.data.map((u) => (
                  <tr key={u.id} className={u.is_active ? "" : "text-slate-400"}>
                    <Td className="font-medium">{u.name}</Td>
                    <Td>{u.email}</Td>
                    <Td>{ROLE_LABELS[u.role]}</Td>
                    <Td>{u.department?.name ?? "—"}</Td>
                    <Td>{u.is_active ? <span className="text-emerald-700">Active</span> : <span>Deactivated</span>}</Td>
                    <Td right>
                      {u.id !== me.id && (
                        <Button size="sm" variant={u.is_active ? "ghost" : "secondary"} loading={busy === `u${u.id}`}
                                onClick={async () => {
                                  const r = await run(`u${u.id}`, () => api.masters.updateUser(u.id, { is_active: !u.is_active }),
                                                      (x) => `${x.name} ${x.is_active ? "reactivated" : "deactivated"}`);
                                  if (r) void users.reload();
                                }}>{u.is_active ? "Deactivate" : "Reactivate"}</Button>
                      )}
                    </Td>
                  </tr>
                ))}
              </TBody>
            </Table>
          )}
        </Card>
        <Card title="Add user">
          <form className="space-y-4" onSubmit={async (e) => {
            e.preventDefault();
            const r = await run("add", () => api.masters.createUser({ ...form, department_id: form.department_id ? Number(form.department_id) : null }),
                                (x) => `${x.name} added`);
            if (r) { setForm(blank); void users.reload(); }
          }}>
            <Field label="Name" required><Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></Field>
            <Field label="Email" required><Input type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} /></Field>
            <Field label="Initial password" required><Input type="password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} /></Field>
            <Field label="Role" required>
              <Select value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value as Role })}>
                {ROLES.map((r) => <option key={r} value={r}>{ROLE_LABELS[r]}</option>)}
              </Select>
            </Field>
            <Field label="Department" hint="Requesters and department heads only">
              <Select value={form.department_id} onChange={(e) => setForm({ ...form, department_id: e.target.value })}>
                <option value="">None</option>
                {departments.data?.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
              </Select>
            </Field>
            <Button type="submit" icon="plus" loading={busy === "add"} className="w-full">Add user</Button>
          </form>
        </Card>
      </div>
    </>
  );
}
