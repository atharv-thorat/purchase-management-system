"use client";

import { useState } from "react";

import { Icon } from "@/components/Icon";
import { formatINR } from "@/lib/format";
import type { DepartmentSpend } from "@/types/api";

// Spend vs budget per department on one shared ₹ scale: the light track is the month's
// budget, the fill is committed spend (D-05). One series, so no legend; values are printed as
// text beside each bar. Over budget turns the fill to the reserved "critical" red and always
// adds an icon + label. Colours validated with the dataviz palette checker (D-56).

function niceMax(value: number): number {
  const steps = [1, 2, 2.5, 5, 10];
  const magnitude = 10 ** Math.floor(Math.log10(value || 1));
  for (const s of steps) if (s * magnitude >= value) return s * magnitude;
  return 10 * magnitude;
}

function lakhs(value: number): string {
  if (value >= 1e7) return `₹${+(value / 1e7).toFixed(2)} Cr`;
  if (value >= 1e5) return `₹${+(value / 1e5).toFixed(2)} L`;
  if (value >= 1e3) return `₹${+(value / 1e3).toFixed(1)}K`;
  return `₹${value}`;
}

export function SpendChart({ data }: { data: DepartmentSpend[] }) {
  const [hover, setHover] = useState<number | null>(null);
  const max = niceMax(Math.max(...data.map((d) => Math.max(Number(d.monthly_budget), Number(d.committed)))));
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((t) => t * max);
  const pct = (v: string) => `${(Number(v) / max) * 100}%`;

  return (
    <div>
      <div className="grid grid-cols-[7.5rem_1fr_12rem] items-center gap-x-4">
        {data.map((d, i) => (
          <div key={d.department.id} className="contents">
            <div className="py-3 text-sm font-medium text-slate-800">{d.department.name}</div>
            <div className="relative h-6" onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)}>
              {ticks.slice(1).map((t) => (
                <div key={t} className="absolute inset-y-[-6px] w-px bg-slate-100" style={{ left: `${(t / max) * 100}%` }} />
              ))}
              {/* budget track */}
              <div className="absolute inset-y-0 left-0 rounded-r bg-chart-track" style={{ width: pct(d.monthly_budget) }} />
              {/* committed fill, 4px rounded data end, square at the baseline */}
              <div className={`absolute inset-y-1 left-0 rounded-r ${d.over_budget ? "bg-chart-critical" : "bg-chart-fill"}`}
                   style={{ width: pct(d.committed) }} />
              {hover === i && (
                <div className="pointer-events-none absolute -top-2 z-10 -translate-y-full rounded-md bg-slate-900 px-3 py-2 text-xs text-white shadow-lg"
                     style={{ left: `min(${pct(d.committed)}, 70%)` }}>
                  <div className="font-semibold">{d.department.name}</div>
                  <div>Committed {formatINR(d.committed)}</div>
                  <div>Budget {formatINR(d.monthly_budget)}</div>
                  <div>{d.over_budget ? "Over by" : "Remaining"} {formatINR(d.remaining.replace("-", ""))}</div>
                </div>
              )}
            </div>
            <div className="text-sm leading-tight">
              <div className="tabular-nums text-slate-900">{formatINR(d.committed)}</div>
              <div className="flex items-center gap-1 text-xs text-slate-500">
                {d.over_budget ? (
                  <span className="inline-flex items-center gap-1 font-medium text-red-700">
                    <Icon name="alert" className="h-3.5 w-3.5" /> Over budget · {d.utilisation_pct}%
                  </span>
                ) : (
                  <>of {formatINR(d.monthly_budget)} · {d.utilisation_pct}%</>
                )}
              </div>
            </div>
          </div>
        ))}
        {/* axis */}
        <div />
        <div className="relative mt-1 h-5 border-t border-slate-300 text-[11px] text-slate-500">
          {ticks.map((t, i) => (
            <span key={t} style={{ left: `${(t / max) * 100}%` }}
                  className={`absolute top-1 whitespace-nowrap tabular-nums ${i === 0 ? "" : i === ticks.length - 1 ? "-translate-x-full" : "-translate-x-1/2"}`}>
              {lakhs(t)}
            </span>
          ))}
        </div>
        <div />
      </div>
      <p className="mt-4 flex items-center gap-4 text-xs text-slate-500">
        <span className="inline-flex items-center gap-1.5"><span className="h-2.5 w-4 rounded-sm bg-chart-fill" /> Committed this month</span>
        <span className="inline-flex items-center gap-1.5"><span className="h-2.5 w-4 rounded-sm bg-chart-track" /> Monthly budget</span>
      </p>
    </div>
  );
}
