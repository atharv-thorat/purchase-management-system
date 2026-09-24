"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";

import { Icon } from "@/components/Icon";

export function Table({ children }: { children: React.ReactNode }) {
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full text-sm">{children}</table>
    </div>
  );
}

export function THead({ children }: { children: React.ReactNode }) {
  return (
    <thead className="border-b border-slate-200 bg-slate-50/80 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
      <tr>{children}</tr>
    </thead>
  );
}

export function Th({ children, right, className = "" }: { children?: React.ReactNode; right?: boolean; className?: string }) {
  return <th className={`whitespace-nowrap px-4 py-2.5 ${right ? "text-right" : ""} ${className}`}>{children}</th>;
}

export function TBody({ children }: { children: React.ReactNode }) {
  return <tbody className="divide-y divide-slate-100">{children}</tbody>;
}

export function Td({ children, right, className = "" }: { children?: React.ReactNode; right?: boolean; className?: string }) {
  return (
    <td className={`px-4 py-3 align-middle text-slate-800 ${right ? "text-right tabular-nums" : ""} ${className}`}>{children}</td>
  );
}

/** A row that navigates on click; the first cell holds the real link for keyboard users. */
export function RowLink({ href, children }: { href: string; children: React.ReactNode }) {
  const router = useRouter();
  return <tr className="cursor-pointer hover:bg-slate-50" onClick={() => router.push(href)}>{children}</tr>;
}

export function DocLink({ href, children }: { href: string; children: React.ReactNode }) {
  return (
    <Link href={href} onClick={(e) => e.stopPropagation()} className="whitespace-nowrap font-medium text-brand-600 hover:text-brand-700 hover:underline">
      {children}
    </Link>
  );
}

export function Pagination({ page, pages, total, onPage }: { page: number; pages: number; total: number; onPage: (p: number) => void }) {
  if (total === 0) return null;
  return (
    <div className="flex items-center justify-between border-t border-slate-100 px-4 py-3 text-sm text-slate-600">
      <span>{total} result{total === 1 ? "" : "s"} · page {page} of {Math.max(pages, 1)}</span>
      <div className="flex gap-1">
        <button disabled={page <= 1} onClick={() => onPage(page - 1)} aria-label="Previous page"
                className="rounded-md p-1.5 ring-1 ring-slate-200 hover:bg-slate-50 disabled:opacity-40">
          <Icon name="chevronLeft" className="h-4 w-4" />
        </button>
        <button disabled={page >= pages} onClick={() => onPage(page + 1)} aria-label="Next page"
                className="rounded-md p-1.5 ring-1 ring-slate-200 hover:bg-slate-50 disabled:opacity-40">
          <Icon name="chevronRight" className="h-4 w-4" />
        </button>
      </div>
    </div>
  );
}
