import { humanize } from "@/lib/format";
import { BADGE_CLASSES, DOT_CLASSES, toneOf } from "@/lib/status";

export function StatusBadge({ status, size = "md" }: { status: string; size?: "sm" | "md" | "lg" }) {
  const tone = toneOf(status);
  const sizes = { sm: "px-2 py-0.5 text-xs", md: "px-2.5 py-1 text-xs", lg: "px-3 py-1 text-sm" }[size];
  return (
    <span className={`inline-flex items-center gap-1.5 whitespace-nowrap rounded-full font-medium ring-1 ring-inset ${BADGE_CLASSES[tone]} ${sizes}`}>
      <span className={`h-1.5 w-1.5 rounded-full ${DOT_CLASSES[tone]}`} aria-hidden="true" />
      {humanize(status)}
    </span>
  );
}
