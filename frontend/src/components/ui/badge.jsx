import { cva } from "class-variance-authority";
import { cn } from "../../lib/utils";

const variants = cva("inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium border", {
  variants: {
    tone: {
      neutral: "bg-muted text-muted-foreground",
      good: "bg-emerald-500/10 text-emerald-400 border-emerald-500/30",
      warn: "bg-amber-500/10 text-amber-400 border-amber-500/30",
      bad: "bg-rose-500/10 text-rose-400 border-rose-500/30",
      brand: "bg-primary/15 text-primary border-primary/30",
    },
  },
  defaultVariants: { tone: "neutral" },
});

export function Badge({ className, tone, ...props }) {
  return <span className={cn(variants({ tone }), className)} {...props} />;
}
