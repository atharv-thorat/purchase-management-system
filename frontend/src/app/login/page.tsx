"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import { Icon } from "@/components/Icon";
import { Button } from "@/components/ui/Button";
import { Field, Input } from "@/components/ui/Form";
import { Spinner } from "@/components/ui/States";
import { useToast } from "@/components/ui/Toast";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { ROLE_LABELS } from "@/lib/format";
import type { CurrentUser, DemoUsers } from "@/types/api";

const ROLE_HINTS: Record<string, string> = {
  REQUESTER: "Raises purchase requests",
  DEPT_HEAD: "Approves department requests",
  FINANCE: "Approves high-value requests",
  PURCHASE: "Quotations and POs",
  STORE: "Records goods receipts",
  ACCOUNTS: "Invoices and payments",
  ADMIN: "Master data; read-only",
};

function LoginScreen() {
  const router = useRouter();
  const params = useSearchParams();
  const toast = useToast();
  const { login, user, ready } = useAuth();
  const [demo, setDemo] = useState<DemoUsers | null>(null);
  const [demoError, setDemoError] = useState<string | null>(null);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState<string | null>(null);

  useEffect(() => {
    api.auth.demoUsers().then(setDemo).catch((e: ApiError) => setDemoError(e.message));
  }, []);
  useEffect(() => {
    if (params.get("expired")) toast.info("Your session ended. Please log in again.");
  }, [params, toast]);
  useEffect(() => {
    if (ready && user) router.replace("/dashboard");
  }, [ready, user, router]);

  const signIn = async (mail: string, pass: string) => {
    setBusy(mail);
    try {
      await login(mail, pass);
      router.replace(params.get("next") || "/dashboard");
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : String(e));
      setBusy(null);
    }
  };

  return (
    <main className="min-h-screen bg-gradient-to-b from-slate-50 to-slate-100 px-4 py-12">
      <div className="mx-auto max-w-6xl">
        <div className="mb-10 text-center">
          <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-xl bg-brand-500 text-white shadow">
            <Icon name="cart" className="h-6 w-6" />
          </div>
          <h1 className="text-3xl font-semibold tracking-tight text-slate-900">Purchase Management</h1>
          <p className="mt-2 text-slate-600">Purchase request → approval → quotations → PO → goods receipt → invoice → payment</p>
        </div>

        <div className="grid gap-8 lg:grid-cols-[1fr_19rem]">
          <section>
            <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500">One-click demo login</h2>
            {demoError && <p className="rounded-lg border border-red-200 bg-red-50 p-4 text-red-800">{demoError}</p>}
            {!demo && !demoError && <div className="flex items-center gap-2 text-slate-500"><Spinner /> Loading demo users…</div>}
            <div className="grid gap-3 sm:grid-cols-2">
              {demo?.users.map((u: CurrentUser) => (
                <button key={u.id} onClick={() => signIn(u.email, demo.password)} disabled={busy !== null}
                        className="group flex items-center gap-4 rounded-xl border border-slate-200 bg-white p-4 text-left shadow-sm transition hover:border-brand-500 hover:shadow disabled:opacity-60">
                  <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-brand-50 font-semibold text-brand-700">
                    {u.name.split(" ").map((p) => p[0]).join("")}
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="font-semibold text-slate-900">{u.name}</p>
                    <p className="mt-0.5 text-sm font-medium text-brand-700">
                      {ROLE_LABELS[u.role]}{u.department ? <span className="text-slate-500"> · {u.department.name}</span> : ""}
                    </p>
                    <p className="text-sm text-slate-500">{ROLE_HINTS[u.role]}</p>
                  </div>
                  {busy === u.email ? <Spinner className="h-5 w-5 text-brand-500" /> :
                    <Icon name="arrowRight" className="h-5 w-5 text-slate-300 group-hover:text-brand-500" />}
                </button>
              ))}
            </div>
          </section>

          <section className="h-fit rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
            <h2 className="mb-4 font-semibold text-slate-900">Sign in with email</h2>
            <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); void signIn(email, password); }}>
              <Field label="Email"><Input type="email" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} required /></Field>
              <Field label="Password"><Input type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required /></Field>
              <Button type="submit" className="w-full" loading={busy === email}>Sign in</Button>
            </form>
            {demo && <p className="mt-4 text-xs text-slate-500">Demo password for every user: <code className="font-mono">{demo.password}</code></p>}
          </section>
        </div>
      </div>
    </main>
  );
}

export default function LoginPage() {
  return <Suspense><LoginScreen /></Suspense>;
}
