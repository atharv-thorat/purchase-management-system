"use client";

import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { Field, Input } from "@/components/ui/Form";
import { Card, PageHeader } from "@/components/ui/Layout";
import { EmptyState, ErrorState, Loading } from "@/components/ui/States";
import { Table, TBody, Td, Th, THead } from "@/components/ui/Table";
import { api } from "@/lib/api";
import { useAction, useApi } from "@/lib/hooks";

const blank = { name: "", contact_person: "", email: "", phone: "", gstin: "" };

export default function SuppliersPage() {
  const { data, error, loading, reload } = useApi(() => api.masters.suppliers(), []);
  const { run, busy } = useAction();
  const [form, setForm] = useState(blank);
  const field = (key: keyof typeof blank, label: string, extra: React.InputHTMLAttributes<HTMLInputElement> = {}) => (
    <Field label={label} required><Input {...extra} value={form[key]} onChange={(e) => setForm({ ...form, [key]: e.target.value })} /></Field>
  );

  return (
    <>
      <PageHeader title="Suppliers" subtitle="Only admins onboard suppliers. Inactive suppliers can't quote or be selected." />
      <div className="grid gap-6 lg:grid-cols-[1fr_22rem]">
        <Card padded={false}>
          {loading && !data ? <Loading /> : error ? <ErrorState error={error} onRetry={reload} /> : !data?.length ? <EmptyState title="No suppliers" /> : (
            <Table>
              <THead><Th>Supplier</Th><Th>Contact</Th><Th>GSTIN</Th><Th>Status</Th><Th /></THead>
              <TBody>
                {data.map((s) => (
                  <tr key={s.id} className={s.is_active ? "" : "text-slate-400"}>
                    <Td><div className="font-medium">{s.name}</div><div className="text-xs text-slate-500">{s.email}</div></Td>
                    <Td>{s.contact_person}<div className="text-xs text-slate-500">{s.phone}</div></Td>
                    <Td className="font-mono text-xs">{s.gstin}</Td>
                    <Td>{s.is_active ? <span className="text-emerald-700">Active</span> : "Inactive"}</Td>
                    <Td right>
                      <Button size="sm" variant={s.is_active ? "ghost" : "secondary"} loading={busy === `s${s.id}`}
                              onClick={async () => {
                                const r = await run(`s${s.id}`, () => api.masters.updateSupplier(s.id, { is_active: !s.is_active }),
                                                    (x) => `${x.name} ${x.is_active ? "activated" : "deactivated"}`);
                                if (r) void reload();
                              }}>{s.is_active ? "Deactivate" : "Activate"}</Button>
                    </Td>
                  </tr>
                ))}
              </TBody>
            </Table>
          )}
        </Card>
        <Card title="Add supplier">
          <form className="space-y-4" onSubmit={async (e) => {
            e.preventDefault();
            const r = await run("add", () => api.masters.createSupplier(form), (x) => `${x.name} added`);
            if (r) { setForm(blank); void reload(); }
          }}>
            {field("name", "Name")}
            {field("contact_person", "Contact person")}
            {field("email", "Email", { type: "email" })}
            {field("phone", "Phone")}
            {field("gstin", "GSTIN", { placeholder: "27AAACT2727Q1ZW", className: "font-mono uppercase" })}
            <Button type="submit" icon="plus" loading={busy === "add"} className="w-full">Add supplier</Button>
          </form>
        </Card>
      </div>
    </>
  );
}
