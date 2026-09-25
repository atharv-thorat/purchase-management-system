import { humanize } from "@/lib/format";
import { BADGE_CLASSES, DOT_CLASSES, toneOf } from "@/lib/status";

/** `muted` is for a status that no longer applies, e.g. the "from" side of a transition. */
export function StatusBadge({ status, size = "md", muted = false }: {
  status: string;
  size?: "sm" | "md" | "lg";
  muted?: boolean;
}) {
  const tone = toneOf(status);
  const sizes = { sm: "px-2 py-0.5 text-xs", md: "px-2.5 py-1 text-xs", lg: "px-3 py-1 text-sm" }[size];
  const colours = muted ? "bg-white text-slate-500 ring-slate-300" : BADGE_CLASSES[tone];
  const dot = muted ? "bg-slate-300" : DOT_CLASSES[tone];
  return (
    <span className={`inline-flex items-center gap-1.5 whitespace-nowrap rounded-full font-medium ring-1 ring-inset ${colours} ${sizes}`}>
      <span className={`h-1.5 w-1.5 rounded-full ${dot}`} aria-hidden="true" />
      {humanize(status)}
    </span>
  );
}
