import { Icon, type IconName } from "@/components/Icon";
import type { ApiError } from "@/lib/api";

export function Spinner({ className = "h-5 w-5" }: { className?: string }) {
  return (
    <svg className={`animate-spin text-current ${className}`} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle className="opacity-20" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" />
      <path className="opacity-80" d="M22 12a10 10 0 00-10-10" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
    </svg>
  );
}

export function Loading({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="flex items-center justify-center gap-3 py-16 text-slate-500" role="status">
      <Spinner /> <span>{label}</span>
    </div>
  );
}

export function EmptyState({ icon = "inbox", title, children }: { icon?: IconName; title: string; children?: React.ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center px-6 py-12 text-center">
      <div className="mb-3 rounded-full bg-slate-100 p-3 text-slate-400"><Icon name={icon} className="h-6 w-6" /></div>
      <p className="font-medium text-slate-700">{title}</p>
      {children && <div className="mt-1 max-w-md text-sm text-slate-500">{children}</div>}
    </div>
  );
}

export function ErrorState({ error, onRetry }: { error: ApiError; onRetry?: () => void }) {
  const notFound = error.status === 404;
  return (
    <div className="mx-auto mt-10 max-w-lg rounded-xl border border-slate-200 bg-white p-8 text-center shadow-sm">
      <div className="mx-auto mb-3 w-fit rounded-full bg-red-50 p-3 text-red-600"><Icon name="alert" className="h-6 w-6" /></div>
      <h2 className="text-lg font-semibold text-slate-900">{notFound ? "Not found" : "Something went wrong"}</h2>
      <p className="mt-2 text-slate-600">
        {notFound ? "This record doesn't exist, or it isn't visible to your role." : error.message}
      </p>
      {onRetry && !notFound && (
        <button onClick={onRetry} className="mt-4 text-sm font-medium text-brand-600 hover:underline">Try again</button>
      )}
    </div>
  );
}
