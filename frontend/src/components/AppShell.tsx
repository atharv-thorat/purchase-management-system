"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";

import { Icon } from "@/components/Icon";
import { Spinner } from "@/components/ui/States";
import { useToast } from "@/components/ui/Toast";
import { api, ApiError } from "@/lib/api";
import { FLASH_KEY, useAuth, useUser } from "@/lib/auth";
import { ROLE_LABELS } from "@/lib/format";
import { NAV } from "@/lib/nav";
import type { DemoUsers } from "@/types/api";

function Sidebar() {
  const user = useUser();
  const pathname = usePathname();
  const isActive = (href: string) =>
    href === "/prs" ? pathname === "/prs" || (/^\/prs\/\d+/.test(pathname)) : pathname === href || pathname.startsWith(`${href}/`);

  return (
    <aside className="fixed inset-y-0 left-0 z-30 flex w-60 flex-col border-r border-slate-200 bg-white">
      <Link href="/dashboard" className="flex h-16 items-center gap-2.5 border-b border-slate-100 px-5">
        <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand-500 text-white"><Icon name="cart" className="h-5 w-5" /></span>
        <span className="font-semibold text-slate-900">Purchase Mgmt</span>
      </Link>
      <nav className="flex-1 space-y-6 overflow-y-auto px-3 py-5">
        {NAV[user.role].map((section, i) => (
          <div key={i}>
            {section.title && <p className="mb-2 px-3 text-xs font-semibold uppercase tracking-wide text-slate-400">{section.title}</p>}
            <ul className="space-y-1">
              {section.items.map((item) => {
                const active = isActive(item.href);
                return (
                  <li key={item.href}>
                    <Link href={item.href}
                          className={`flex items-center gap-3 rounded-md px-3 py-2 text-[15px] font-medium transition ${
                            active ? "bg-brand-50 text-brand-700" : "text-slate-700 hover:bg-slate-100 hover:text-slate-900"}`}>
                      <Icon name={item.icon} className={`h-5 w-5 ${active ? "text-brand-600" : "text-slate-400"}`} />
                      {item.label}
                    </Link>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </nav>
      <p className="border-t border-slate-100 px-5 py-3 text-xs text-slate-400">Demo · single company · INR</p>
    </aside>
  );
}

/** Current user + role, always visible; the switcher logs in as another demo user in one click. */
function UserMenu() {
  const user = useUser();
  const { switchUser, logout } = useAuth();
  const toast = useToast();
  const [open, setOpen] = useState(false);
  const [demo, setDemo] = useState<DemoUsers | null>(null);
  const [switching, setSwitching] = useState<number | null>(null);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (open && !demo) api.auth.demoUsers().then(setDemo).catch(() => setDemo({ password: "", users: [] }));
  }, [open, demo]);
  useEffect(() => {
    const close = (e: MouseEvent) => ref.current && !ref.current.contains(e.target as Node) && setOpen(false);
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);

  const switchTo = async (id: number, email: string) => {
    if (!demo) return;
    setSwitching(id);
    try {
      await switchUser(email, demo.password); // reloads the page on success
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : String(e));
      setSwitching(null);
    }
  };

  return (
    <div className="relative" ref={ref}>
      <button onClick={() => setOpen((v) => !v)}
              className="flex items-center gap-3 rounded-lg px-2 py-1.5 text-left hover:bg-slate-100" aria-expanded={open}>
        <span className="flex h-9 w-9 items-center justify-center rounded-full bg-brand-500 text-sm font-semibold text-white">
          {user.name.split(" ").map((p) => p[0]).join("")}
        </span>
        <span className="leading-tight">
          <span className="block text-sm font-semibold text-slate-900">{user.name}</span>
          <span className="block text-xs text-slate-500">{ROLE_LABELS[user.role]}{user.department ? ` · ${user.department.name}` : ""}</span>
        </span>
        <Icon name="chevronDown" className="h-4 w-4 text-slate-400" />
      </button>
      {open && (
        <div className="absolute right-0 z-40 mt-2 w-80 overflow-hidden rounded-xl border border-slate-200 bg-white shadow-xl">
          <p className="flex items-center gap-2 border-b border-slate-100 px-4 py-2.5 text-xs font-semibold uppercase tracking-wide text-slate-500">
            <Icon name="switch" className="h-4 w-4" /> Switch demo user
          </p>
          <ul className="max-h-[60vh] overflow-y-auto py-1">
            {!demo && <li className="flex items-center gap-2 px-4 py-3 text-sm text-slate-500"><Spinner className="h-4 w-4" /> Loading…</li>}
            {demo?.users.map((u) => (
              <li key={u.id}>
                <button onClick={() => switchTo(u.id, u.email)} disabled={u.id === user.id || switching !== null}
                        className="flex w-full items-center justify-between gap-3 px-4 py-2 text-left hover:bg-slate-50 disabled:cursor-default disabled:bg-brand-50/60">
                  <span>
                    <span className="block text-sm font-medium text-slate-900">{u.name}</span>
                    <span className="block text-xs text-slate-500">{ROLE_LABELS[u.role]}{u.department ? ` · ${u.department.name}` : ""}</span>
                  </span>
                  {switching === u.id ? <Spinner className="h-4 w-4" /> : u.id === user.id ?
                    <span className="text-xs font-medium text-brand-600">current</span> : null}
                </button>
              </li>
            ))}
          </ul>
          <button onClick={logout} className="flex w-full items-center gap-2 border-t border-slate-100 px-4 py-2.5 text-sm text-slate-700 hover:bg-slate-50">
            <Icon name="logout" className="h-4 w-4" /> Log out
          </button>
        </div>
      )}
    </div>
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const { user, ready } = useAuth();
  const router = useRouter();
  const pathname = usePathname();
  const toast = useToast();

  useEffect(() => {
    const flash = window.sessionStorage.getItem(FLASH_KEY);
    if (flash && user) {
      window.sessionStorage.removeItem(FLASH_KEY);
      toast.success(flash);
    }
  }, [user, toast]);

  useEffect(() => {
    if (ready && !user) router.replace(`/login?next=${encodeURIComponent(pathname)}`);
  }, [ready, user, router, pathname]);

  if (!ready || !user) {
    return <div className="flex min-h-screen items-center justify-center text-slate-500"><Spinner className="h-6 w-6" /></div>;
  }
  return (
    <div className="min-h-screen">
      <Sidebar />
      <div className="pl-60">
        <header className="sticky top-0 z-20 flex h-16 items-center justify-end gap-4 border-b border-slate-200 bg-white/90 px-8 backdrop-blur">
          <span className="mr-auto rounded-full bg-slate-100 px-3 py-1 text-xs font-medium text-slate-600">
            Signed in as <span className="text-slate-900">{ROLE_LABELS[user.role]}</span>
          </span>
          <UserMenu />
        </header>
        <main className="mx-auto max-w-7xl px-8 py-8">{children}</main>
      </div>
    </div>
  );
}
