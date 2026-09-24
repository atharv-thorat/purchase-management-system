// Sidebar entries per role: only the pages a role actually uses. This is navigation, not
// permission — every page and action is still enforced by the API.

import type { Role } from "@/types/api";
import type { IconName } from "@/components/Icon";

export interface NavItem { href: string; label: string; icon: IconName }
export interface NavSection { title?: string; items: NavItem[] }

const dashboard: NavItem = { href: "/dashboard", label: "Dashboard", icon: "home" };
const approvals: NavItem = { href: "/approvals", label: "Approvals", icon: "check" };
const newRequest: NavItem = { href: "/prs/new", label: "New request", icon: "plus" };
const pos: NavItem = { href: "/pos", label: "Purchase orders", icon: "cart" };
const grns: NavItem = { href: "/grns", label: "Goods receipts", icon: "truck" };
const invoices: NavItem = { href: "/invoices", label: "Invoices", icon: "receipt" };
const payments: NavItem = { href: "/payments", label: "Payments", icon: "rupee" };
const requests = (label: string): NavItem => ({ href: "/prs", label, icon: "doc" });

const masters: NavSection = {
  title: "Masters",
  items: [
    { href: "/admin/departments", label: "Departments", icon: "building" },
    { href: "/admin/users", label: "Users", icon: "users" },
    { href: "/admin/suppliers", label: "Suppliers", icon: "briefcase" },
    { href: "/admin/items", label: "Items", icon: "box" },
    { href: "/admin/settings", label: "Settings", icon: "cog" },
  ],
};

export const NAV: Record<Role, NavSection[]> = {
  REQUESTER: [{ items: [dashboard, requests("My requests"), newRequest, pos] }],
  DEPT_HEAD: [{ items: [dashboard, approvals, requests("Department requests"), newRequest, pos] }],
  FINANCE: [{ items: [dashboard, approvals, requests("Purchase requests"), pos, invoices, payments] }],
  PURCHASE: [{ items: [dashboard, requests("Approved requests"), pos, grns, invoices] }],
  STORE: [{ items: [dashboard, pos, grns] }],
  ACCOUNTS: [{ items: [dashboard, pos, grns, invoices, payments] }],
  ADMIN: [{ items: [dashboard, requests("Purchase requests"), pos, grns, invoices, payments] }, masters],
};

/** Roles that raise PRs get a "New request" button on the requests list. */
export const RAISES_PRS: Role[] = ["REQUESTER", "DEPT_HEAD"];
