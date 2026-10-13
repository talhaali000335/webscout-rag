import { useState } from "react";
import { Globe, Loader2, CheckCircle2, AlertTriangle, Search, RefreshCw, Trash2, Lock, KeyRound } from "lucide-react";
import { Button } from "./ui/button";
import { Input } from "./ui/input";
import { Badge } from "./ui/badge";
import { cn } from "../lib/utils";

const STAGES = ["queued", "scraping", "chunking", "embedding", "done"];
const STAGE_LABEL = {
  queued: "Waiting in queue…",
  scraping: "Scraping the page…",
  chunking: "Splitting into chunks…",
  embedding: "Creating embeddings…",
};

function Progress({ stage }) {
  const pct = Math.max(8, (STAGES.indexOf(stage) / (STAGES.length - 1)) * 100);
  return (
    <div className="mt-2">
      <div className="h-1 rounded-full bg-muted overflow-hidden">
        <div className="h-full bg-primary transition-all duration-500" style={{ width: `${pct}%` }} />
      </div>
      <p className="mt-1 text-[11px] text-muted-foreground">{STAGE_LABEL[stage] || "Working…"}</p>
    </div>
  );
}

export default function Sidebar({ pages, activeCid, onSelect, onAdd, onRetry, onRemove, onForget }) {
  const [url, setUrl] = useState("");
  const [loginFirst, setLoginFirst] = useState(false);

  const submit = (e) => {
    e.preventDefault();
    if (!url.trim()) return;
    onAdd(url.trim(), false, loginFirst);
    setUrl("");
  };

  return (
    <aside className="w-full md:w-80 shrink-0 border-b md:border-b-0 md:border-r bg-card/60 backdrop-blur flex flex-col">
      <div className="p-5 pb-3">
        <div className="flex items-center gap-2.5">
          <div className="h-9 w-9 rounded-xl bg-gradient-to-br from-primary to-cyan-400 grid place-items-center shadow-lg shadow-primary/30">
            <Search className="h-4 w-4 text-white" />
          </div>
          <div>
            <h1 className="font-bold leading-tight">WebScout</h1>
            <p className="text-[11px] text-muted-foreground">Chat with any web page</p>
          </div>
        </div>

        <form onSubmit={submit} className="mt-5 space-y-2">
          <label className="text-xs font-medium text-muted-foreground">Page URL</label>
          <Input
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://www.amazon.com/dp/…"
          />
          <label className="flex items-center gap-2 text-[11px] text-muted-foreground cursor-pointer select-none">
            <input type="checkbox" checked={loginFirst} onChange={(e) => setLoginFirst(e.target.checked)}
                   className="accent-[hsl(var(--primary))]" />
            This page needs me to sign in first
          </label>
          <Button type="submit" className="w-full" disabled={!url.trim()}>
            <Globe className="h-4 w-4" /> Scrape & index
          </Button>
        </form>
      </div>

      <div className="px-5 pb-2 text-xs font-medium text-muted-foreground">Your pages</div>
      <div className="flex-1 overflow-y-auto px-3 pb-4 space-y-2 max-h-56 md:max-h-none">
        {pages.length === 0 && (
          <p className="px-2 text-xs text-muted-foreground">Nothing yet — add a URL above.</p>
        )}
        {pages.map((p) => {
          const busy = p.status === "queued" || p.status === "running";
          const needsLogin = p.status === "needs_login";
          return (
            <div
              key={p.cid}
              onClick={() => p.status === "ready" && onSelect(p.cid)}
              className={cn(
                "group rounded-xl border p-3 transition animate-rise",
                p.status === "ready" && "cursor-pointer hover:bg-muted/70",
                activeCid === p.cid ? "bg-muted border-primary/50" : "bg-transparent"
              )}
            >
              <div className="flex items-start justify-between gap-2">
                <p className="text-sm font-medium line-clamp-2 break-words">{p.title || p.url}</p>
                <div className="flex shrink-0">
                  {p.status === "error" || p.status === "expired" ? (
                    <Button variant="ghost" size="sm" className="h-6 w-6 p-0" title="Retry"
                      onClick={(e) => { e.stopPropagation(); onRetry(p); }}>
                      <RefreshCw className="h-3.5 w-3.5" />
                    </Button>
                  ) : null}
                  <Button variant="ghost" size="sm" className="h-6 w-6 p-0 opacity-0 group-hover:opacity-100" title="Remove"
                    onClick={(e) => { e.stopPropagation(); onRemove(p.cid); }}>
                    <Trash2 className="h-3.5 w-3.5" />
                  </Button>
                </div>
              </div>
              <p className="text-[11px] text-muted-foreground truncate">{p.url}</p>
              <div className="mt-2 flex items-center gap-2">
                {needsLogin && <Badge tone="warn"><Lock className="h-3 w-3" /> Sign-in needed</Badge>}
                {busy && <Badge tone="brand"><Loader2 className="h-3 w-3 animate-spin" /> Indexing</Badge>}
                {p.status === "ready" && (
                  <>
                    <Badge tone="good"><CheckCircle2 className="h-3 w-3" /> Ready</Badge>
                    <span className="text-[11px] text-muted-foreground">{p.chunks} chunks</span>
                  </>
                )}
                {p.status === "expired" && <Badge tone="warn">Cache expired</Badge>}
                {p.status === "error" && <Badge tone="bad"><AlertTriangle className="h-3 w-3" /> Failed</Badge>}
              </div>
              {busy && <Progress stage={p.stage} />}
              {p.status === "error" && <p className="mt-2 text-[11px] text-rose-400">{p.error}</p>}
            </div>
          );
        })}
      </div>
      <div className="border-t p-3">
        <Button variant="ghost" size="sm" className="w-full justify-start text-[11px]" onClick={onForget}>
          <KeyRound className="h-3.5 w-3.5" /> Forget my saved site logins
        </Button>
      </div>
    </aside>
  );
}
