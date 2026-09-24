// Display formatting. Values from the API are decimal strings; they are formatted as text,
// never parsed into floats, so ₹ amounts are shown exactly as the server computed them.

import type { ItemUnit } from "@/types/api";

/** "600000" | "600000.5" | 600000 → "₹6,00,000.00" (Indian digit grouping). */
export function formatINR(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === "") return "—";
  const text = typeof value === "number" ? value.toFixed(2) : value.trim();
  const negative = text.startsWith("-");
  const [intPart, fracPart = ""] = text.replace(/^[-+]/, "").split(".");
  const paise = (fracPart + "00").slice(0, 2);
  const digits = intPart.replace(/^0+(?=\d)/, "") || "0";
  const lastThree = digits.slice(-3);
  const rest = digits.slice(0, -3);
  const grouped = rest ? `${rest.replace(/\B(?=(\d{2})+(?!\d))/g, ",")},${lastThree}` : lastThree;
  return `${negative ? "-" : ""}₹${grouped}.${paise}`;
}

/** "50.000" → "50", "280.250" → "280.25" (for form inputs: no grouping). */
export function trimZeros(value: string): string {
  return value.includes(".") ? value.replace(/0+$/, "").replace(/\.$/, "") : value;
}

/** "50.000" → "50", "280.250" → "280.25"; with a unit: "280.25 kg". */
export function formatQty(value: string | null | undefined, unit?: ItemUnit): string {
  if (value === null || value === undefined || value === "") return "—";
  const trimmed = trimZeros(value);
  const withGrouping = trimmed.replace(/^(\d+)/, (int) => Number(int).toLocaleString("en-IN"));
  return unit ? `${withGrouping} ${unit}` : withGrouping;
}

/** Ratio for progress bars only (display, not business logic). */
export function ratio(part: string, whole: string): number {
  const w = Number(whole);
  if (!w) return 0;
  return Math.max(0, Math.min(1, Number(part) / w));
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** "2026-09-15" or an ISO datetime → "15 Sep 2026". */
export function formatDate(value: string | null | undefined): string {
  if (!value) return "—";
  const [y, m, d] = value.slice(0, 10).split("-").map(Number);
  return `${d} ${MONTHS[m - 1]} ${y}`;
}

/** Server datetimes are IST wall-clock without a zone; shown as-is: "15 Sep 2026, 10:05". */
export function formatDateTime(value: string | null | undefined): string {
  if (!value) return "—";
  const time = value.slice(11, 16);
  return time ? `${formatDate(value)}, ${time}` : formatDate(value);
}

export function todayISO(): string {
  const now = new Date();
  const local = new Date(now.getTime() - now.getTimezoneOffset() * 60000);
  return local.toISOString().slice(0, 10);
}

export function addDaysISO(iso: string, days: number): string {
  const date = new Date(`${iso}T00:00:00`);
  date.setDate(date.getDate() + days);
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60000);
  return local.toISOString().slice(0, 10);
}

const WORDS: Record<string, string> = {
  PO_CREATED: "PO created",
  PENDING_DEPT_HEAD: "Pending dept head",
  PENDING_FINANCE: "Pending finance",
  PENDING_MATCH: "Pending match",
  GRN_RECORDED: "Goods received",
  PO_CANCELLED: "PO cancelled",
  REMATCH_REQUESTED: "Rematch requested",
  MISMATCHED: "Mismatch found",
  PAYMENT_RECORDED: "Payment recorded",
  DEPT_HEAD: "Dept head",
  NEFT: "NEFT",
  UPI: "UPI",
};

/** "PARTIALLY_RECEIVED" → "Partially received". */
export function humanize(value: string): string {
  if (WORDS[value]) return WORDS[value];
  const lower = value.toLowerCase().replace(/_/g, " ");
  return lower.charAt(0).toUpperCase() + lower.slice(1);
}

export const ROLE_LABELS: Record<string, string> = {
  REQUESTER: "Requester",
  DEPT_HEAD: "Department head",
  FINANCE: "Finance",
  PURCHASE: "Purchase",
  STORE: "Store",
  ACCOUNTS: "Accounts",
  ADMIN: "Admin",
};
