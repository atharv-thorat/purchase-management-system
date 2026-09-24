import Link from "next/link";

import { Icon, type IconName } from "@/components/Icon";
import { Spinner } from "@/components/ui/States";

type Variant = "primary" | "secondary" | "danger" | "success" | "ghost";
type Size = "sm" | "md";

const VARIANTS: Record<Variant, string> = {
  primary: "bg-brand-500 text-white hover:bg-brand-600 focus-visible:outline-brand-500 shadow-sm",
  secondary: "bg-white text-slate-800 ring-1 ring-inset ring-slate-300 hover:bg-slate-50 shadow-sm",
  danger: "bg-white text-red-700 ring-1 ring-inset ring-red-300 hover:bg-red-50 shadow-sm",
  success: "bg-emerald-600 text-white hover:bg-emerald-700 focus-visible:outline-emerald-600 shadow-sm",
  ghost: "text-slate-700 hover:bg-slate-100",
};
const SIZES: Record<Size, string> = { sm: "h-8 px-3 text-sm gap-1.5", md: "h-10 px-4 text-[15px] gap-2" };
const base =
  "inline-flex items-center justify-center rounded-md font-medium transition focus-visible:outline " +
  "focus-visible:outline-2 focus-visible:outline-offset-2 disabled:cursor-not-allowed disabled:opacity-50";

interface Props extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  icon?: IconName;
  loading?: boolean;
}

export function Button({ variant = "primary", size = "md", icon, loading, children, className = "", disabled, ...rest }: Props) {
  return (
    <button {...rest} disabled={disabled || loading} className={`${base} ${VARIANTS[variant]} ${SIZES[size]} ${className}`}>
      {loading ? <Spinner className="h-4 w-4" /> : icon ? <Icon name={icon} className="h-4 w-4" /> : null}
      {children}
    </button>
  );
}

export function ButtonLink({ href, variant = "primary", size = "md", icon, children, className = "" }: {
  href: string; variant?: Variant; size?: Size; icon?: IconName; children: React.ReactNode; className?: string;
}) {
  return (
    <Link href={href} className={`${base} ${VARIANTS[variant]} ${SIZES[size]} ${className}`}>
      {icon && <Icon name={icon} className="h-4 w-4" />}
      {children}
    </Link>
  );
}
