// One colour per status meaning, used by every badge and timeline dot in the app:
//   done / good → green · waiting on someone → amber · in progress → blue
//   problem → red · exception (short-closed) → orange · inert (draft, cancelled) → grey
// Colour never carries meaning alone: badges always show the status label.

export type Tone = "green" | "amber" | "blue" | "red" | "orange" | "grey" | "indigo";

const TONE_BY_STATUS: Record<string, Tone> = {
  // purchase requests
  DRAFT: "grey",
  PENDING_DEPT_HEAD: "amber",
  PENDING_FINANCE: "amber",
  APPROVED: "green",
  REJECTED: "red",
  PO_CREATED: "indigo",
  // purchase orders
  ISSUED: "blue",
  PARTIALLY_RECEIVED: "blue",
  FULLY_RECEIVED: "blue",
  SHORT_CLOSED: "orange",
  CLOSED: "green",
  CANCELLED: "grey",
  // invoices
  PENDING_MATCH: "amber",
  MATCHED: "green",
  MISMATCH: "red",
  PARTIALLY_PAID: "blue",
  PAID: "green",
};

export function toneOf(status: string | null | undefined): Tone {
  return (status && TONE_BY_STATUS[status]) || "grey";
}

export const BADGE_CLASSES: Record<Tone, string> = {
  green: "bg-emerald-50 text-emerald-800 ring-emerald-600/25",
  amber: "bg-amber-50 text-amber-900 ring-amber-600/30",
  blue: "bg-blue-50 text-blue-800 ring-blue-600/25",
  indigo: "bg-indigo-50 text-indigo-800 ring-indigo-600/25",
  red: "bg-red-50 text-red-800 ring-red-600/25",
  orange: "bg-orange-50 text-orange-900 ring-orange-600/30",
  grey: "bg-slate-100 text-slate-700 ring-slate-500/25",
};

export const DOT_CLASSES: Record<Tone, string> = {
  green: "bg-emerald-500",
  amber: "bg-amber-500",
  blue: "bg-blue-500",
  indigo: "bg-indigo-500",
  red: "bg-red-500",
  orange: "bg-orange-500",
  grey: "bg-slate-400",
};
