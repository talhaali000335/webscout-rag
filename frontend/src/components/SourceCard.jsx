import { useState } from "react";
import { ChevronDown, ExternalLink } from "lucide-react";
import { cn } from "../lib/utils";

export default function SourceCard({ source, open: forceOpen }) {
  const [open, setOpen] = useState(false);
  const isOpen = open || forceOpen;
  // cross-encoder logits roughly span -10..+10; map to a 0-100% bar for display
  const pct = Math.max(4, Math.min(100, ((source.score + 6) / 14) * 100));

  return (
    <div
      id={`src-${source.id}`}
      className={cn("rounded-lg border bg-background/40 text-left", source.cited && "border-primary/40")}
    >
      <button onClick={() => setOpen(!isOpen)} className="w-full flex items-center gap-2 p-2.5 text-left">
        <span className={cn(
          "h-5 w-5 shrink-0 rounded-md grid place-items-center text-[11px] font-semibold",
          source.cited ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground")}>
          {source.id}
        </span>
        <span className="flex-1 min-w-0">
          <span className="block text-xs font-medium truncate">{source.heading}</span>
          <span className="mt-1 block h-1 rounded-full bg-muted overflow-hidden">
            <span className="block h-full bg-emerald-400/80" style={{ width: `${pct}%` }} />
          </span>
        </span>
        <span className="text-[10px] text-muted-foreground tabular-nums">rel {source.score.toFixed(1)}</span>
        <ChevronDown className={cn("h-4 w-4 text-muted-foreground transition", isOpen && "rotate-180")} />
      </button>
      {isOpen && (
        <div className="px-3 pb-3 animate-rise">
          <p className="text-xs text-muted-foreground whitespace-pre-wrap leading-relaxed max-h-48 overflow-y-auto">
            {source.snippet.replace(/^\[Section:[^\]]*\]\n/, "")}
          </p>
          <a href={source.url} target="_blank" rel="noreferrer"
            className="mt-2 inline-flex items-center gap-1 text-[11px] text-primary hover:underline">
            Open original page <ExternalLink className="h-3 w-3" />
          </a>
        </div>
      )}
    </div>
  );
}
