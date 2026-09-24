"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useCallback } from "react";

import { Icon } from "@/components/Icon";
import { Input, Select } from "@/components/ui/Form";
import { humanize } from "@/lib/format";

/** Filters live in the URL, so dashboard tiles can deep-link into a filtered list. */
export function useUrlFilters() {
  const params = useSearchParams();
  const router = useRouter();
  const set = useCallback(
    (changes: Record<string, string | null>) => {
      const next = new URLSearchParams(params.toString());
      for (const [key, value] of Object.entries(changes)) {
        next.delete(key);
        if (value) next.set(key, value);
      }
      if (!("page" in changes)) next.delete("page");
      router.replace(`?${next.toString()}`);
    },
    [params, router],
  );
  return {
    params,
    set,
    page: Number(params.get("page") ?? 1),
    statuses: params.getAll("status"),
    get: (key: string) => params.get(key) ?? "",
  };
}

export function FilterBar({ children }: { children: React.ReactNode }) {
  return <div className="flex flex-wrap items-end gap-3 border-b border-slate-100 px-4 py-3">{children}</div>;
}

export function StatusFilter({ options, value, onChange }: { options: string[]; value: string[]; onChange: (v: string | null) => void }) {
  // Several statuses can arrive from a dashboard link; the select shows "several" then.
  const current = value.length === 1 ? value[0] : value.length > 1 ? "__many" : "";
  return (
    <label className="block w-52">
      <span className="mb-1 block text-xs font-medium text-slate-500">Status</span>
      <Select value={current} onChange={(e) => onChange(e.target.value || null)}>
        <option value="">All statuses</option>
        {value.length > 1 && <option value="__many" disabled>{value.map(humanize).join(", ")}</option>}
        {options.map((s) => <option key={s} value={s}>{humanize(s)}</option>)}
      </Select>
    </label>
  );
}

export function SearchFilter({ value, placeholder, onChange }: { value: string; placeholder: string; onChange: (v: string | null) => void }) {
  return (
    <label className="block w-64">
      <span className="mb-1 block text-xs font-medium text-slate-500">Search</span>
      <div className="relative">
        <Icon name="search" className="pointer-events-none absolute left-2.5 top-2.5 h-4 w-4 text-slate-400" />
        <Input defaultValue={value} placeholder={placeholder} className="pl-8"
               onKeyDown={(e) => e.key === "Enter" && onChange((e.target as HTMLInputElement).value || null)}
               onBlur={(e) => e.target.value !== value && onChange(e.target.value || null)} />
      </div>
    </label>
  );
}

export function DateFilter({ label, value, onChange }: { label: string; value: string; onChange: (v: string | null) => void }) {
  return (
    <label className="block w-40">
      <span className="mb-1 block text-xs font-medium text-slate-500">{label}</span>
      <Input type="date" value={value} onChange={(e) => onChange(e.target.value || null)} />
    </label>
  );
}
