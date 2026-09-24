import Link from "next/link";

import { Icon } from "@/components/Icon";

export function PageHeader({ title, subtitle, badge, back, actions }: {
  title: React.ReactNode;
  subtitle?: React.ReactNode;
  badge?: React.ReactNode;
  back?: { href: string; label: string };
  actions?: React.ReactNode;
}) {
  return (
    <div className="mb-6">
      {back && (
        <Link href={back.href} className="mb-2 inline-flex items-center gap-1 text-sm text-slate-500 hover:text-slate-800">
          <Icon name="chevronLeft" className="h-4 w-4" /> {back.label}
        </Link>
      )}
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-3">
            <h1 className="text-2xl font-semibold tracking-tight text-slate-900">{title}</h1>
            {badge}
          </div>
          {subtitle && <div className="mt-1 text-slate-600">{subtitle}</div>}
        </div>
        {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
      </div>
    </div>
  );
}

export function Card({ title, subtitle, actions, children, className = "", padded = true }: {
  title?: React.ReactNode;
  subtitle?: React.ReactNode;
  actions?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
  padded?: boolean;
}) {
  return (
    <section className={`rounded-xl border border-slate-200 bg-white shadow-sm ${className}`}>
      {(title || actions) && (
        <header className="flex items-center justify-between gap-3 border-b border-slate-100 px-5 py-3.5">
          <div>
            {title && <h2 className="font-semibold text-slate-900">{title}</h2>}
            {subtitle && <p className="text-sm text-slate-500">{subtitle}</p>}
          </div>
          {actions}
        </header>
      )}
      <div className={padded ? "p-5" : ""}>{children}</div>
    </section>
  );
}

/** Label / value pairs for detail headers. */
export function Facts({ items }: { items: [string, React.ReactNode][] }) {
  return (
    <dl className="grid grid-cols-2 gap-x-6 gap-y-4 sm:grid-cols-3 lg:grid-cols-4">
      {items.map(([label, value]) => (
        <div key={label} className="min-w-0">
          <dt className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</dt>
          <dd className="mt-1 text-slate-900">{value}</dd>
        </div>
      ))}
    </dl>
  );
}

export function Notice({ tone, icon = "info", title, children }: {
  tone: "info" | "warning" | "danger" | "success";
  icon?: Parameters<typeof Icon>[0]["name"];
  title: React.ReactNode;
  children?: React.ReactNode;
}) {
  const styles = {
    info: "border-blue-200 bg-blue-50 text-blue-900 [&_svg]:text-blue-600",
    warning: "border-amber-300 bg-amber-50 text-amber-950 [&_svg]:text-amber-600",
    danger: "border-red-300 bg-red-50 text-red-950 [&_svg]:text-red-600",
    success: "border-emerald-300 bg-emerald-50 text-emerald-950 [&_svg]:text-emerald-600",
  }[tone];
  return (
    <div className={`flex gap-3 rounded-lg border px-4 py-3 ${styles}`}>
      <Icon name={icon} className="mt-0.5 h-5 w-5 shrink-0" />
      <div className="min-w-0">
        <p className="font-medium">{title}</p>
        {children && <div className="mt-0.5 text-sm opacity-90">{children}</div>}
      </div>
    </div>
  );
}
