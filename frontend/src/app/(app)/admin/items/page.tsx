"use client";

import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { Field, Input, Select } from "@/components/ui/Form";
import { Card, PageHeader } from "@/components/ui/Layout";
import { EmptyState, ErrorState, Loading } from "@/components/ui/States";
import { Table, TBody, Td, Th, THead } from "@/components/ui/Table";
import { api } from "@/lib/api";
import { useAction, useApi } from "@/lib/hooks";
import type { ItemUnit } from "@/types/api";

const blank = { name: "", unit: "pcs" as ItemUnit, category: "" };

export default function ItemsPage() {
  const { data, error, loading, reload } = useApi(() => api.masters.items(), []);
  const { run, busy } = useAction();
  const [form, setForm] = useState(blank);

  return (
    <>
      <PageHeader title="Items" subtitle="What can be requested, quoted and ordered" />
      <div className="grid gap-6 lg:grid-cols-[1fr_22rem]">
        <Card padded={false}>
          {loading && !data ? <Loading /> : error ? <ErrorState error={error} onRetry={reload} /> : !data?.length ? <EmptyState icon="box" title="No items" /> : (
            <Table>
              <THead><Th>Item</Th><Th>Category</Th><Th>Unit</Th></THead>
              <TBody>
                {data.map((i) => (
                  <tr key={i.id}><Td className="font-medium">{i.name}</Td><Td>{i.category}</Td><Td>{i.unit}</Td></tr>
                ))}
              </TBody>
            </Table>
          )}
        </Card>
        <Card title="Add item">
          <form className="space-y-4" onSubmit={async (e) => {
            e.preventDefault();
            const r = await run("add", () => api.masters.createItem(form), (x) => `${x.name} added`);
            if (r) { setForm(blank); void reload(); }
          }}>
            <Field label="Name" required><Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></Field>
            <Field label="Category" required><Input value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })} /></Field>
            <Field label="Unit" required>
              <Select value={form.unit} onChange={(e) => setForm({ ...form, unit: e.target.value as ItemUnit })}>
                <option value="pcs">pcs</option><option value="kg">kg</option><option value="box">box</option>
              </Select>
            </Field>
            <Button type="submit" icon="plus" loading={busy === "add"} className="w-full">Add item</Button>
          </form>
        </Card>
      </div>
    </>
  );
}
