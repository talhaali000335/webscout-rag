import { useEffect, useRef, useState } from "react";
import { Send, Sparkles, ShieldCheck, ShieldAlert, Clock, Bot } from "lucide-react";
import { Button } from "./ui/button";
import { Input } from "./ui/input";
import { Badge } from "./ui/badge";
import SourceCard from "./SourceCard";

const SUGGESTIONS = [
  "Summarize this page",
  "What is the price?",
  "What do customers say?",
  "List the key features",
];

function Answer({ text, sources }) {
  // turn [1] markers into little clickable badges that scroll to the source
  const parts = text.split(/(\[\d+\])/g);
  return (
    <p className="whitespace-pre-wrap leading-relaxed text-sm">
      {parts.map((p, i) => {
        const m = p.match(/^\[(\d+)\]$/);
        if (!m) return <span key={i}>{p}</span>;
        return (
          <a key={i} href={`#src-${m[1]}`}
            onClick={(e) => { e.preventDefault(); document.getElementById(`src-${m[1]}`)?.scrollIntoView({ behavior: "smooth", block: "center" }); }}
            className="mx-0.5 inline-grid h-4 min-w-4 px-1 place-items-center rounded bg-primary/20 text-[10px] font-semibold text-primary hover:bg-primary/40 align-text-top">
            {m[1]}
          </a>
        );
      })}
    </p>
  );
}

function Thinking() {
  return (
    <div className="flex items-center gap-2 text-sm text-muted-foreground">
      <span className="flex gap-1">
        {[0, 1, 2].map((i) => (
          <span key={i} className="h-1.5 w-1.5 rounded-full bg-primary animate-blink" style={{ animationDelay: `${i * 0.2}s` }} />
        ))}
      </span>
      Retrieving, re-ranking, answering…
    </div>
  );
}

export default function Chat({ page, messages, busy, onSend }) {
  const [q, setQ] = useState("");
  const endRef = useRef(null);
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages, busy]);

  const send = (text) => {
    const t = (text ?? q).trim();
    if (!t || busy) return;
    setQ("");
    onSend(t);
  };

  if (!page) {
    return (
      <div className="flex-1 grid place-items-center p-8 text-center">
        <div className="max-w-md animate-rise">
          <div className="mx-auto h-14 w-14 rounded-2xl bg-gradient-to-br from-primary to-cyan-400 grid place-items-center shadow-xl shadow-primary/30">
            <Sparkles className="h-6 w-6 text-white" />
          </div>
          <h2 className="mt-5 text-2xl font-bold">Ask any web page anything</h2>
          <p className="mt-2 text-sm text-muted-foreground">
            Paste a URL on the left. WebScout scrapes it, indexes it, and answers using <b>only</b> what's
            on the page — with sources, so you can check every claim.
          </p>
        </div>
      </div>
    );
  }

  return (
    <section className="flex-1 flex flex-col min-w-0 min-h-0">
      <header className="px-6 py-3 border-b flex items-center gap-3 bg-card/40 backdrop-blur">
        <div className="min-w-0">
          <p className="text-sm font-semibold truncate">{page.title || page.url}</p>
          <p className="text-[11px] text-muted-foreground truncate">{page.url}</p>
        </div>
        <Badge tone="brand" className="ml-auto shrink-0">{page.chunks} chunks</Badge>
      </header>

      <div className="flex-1 overflow-y-auto px-4 md:px-8 py-6 space-y-6">
        {messages.length === 0 && (
          <div className="animate-rise">
            <p className="text-sm text-muted-foreground mb-3">Try asking:</p>
            <div className="flex flex-wrap gap-2">
              {SUGGESTIONS.map((s) => (
                <button key={s} onClick={() => send(s)}
                  className="rounded-full border px-3 py-1.5 text-xs hover:bg-muted hover:border-primary/50 transition">
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((m, i) =>
          m.role === "user" ? (
            <div key={i} className="flex justify-end animate-rise">
              <div className="max-w-[80%] rounded-2xl rounded-br-sm bg-primary px-4 py-2.5 text-sm text-primary-foreground">
                {m.content}
              </div>
            </div>
          ) : (
            <div key={i} className="flex gap-3 animate-rise">
              <div className="h-8 w-8 shrink-0 rounded-lg bg-muted grid place-items-center"><Bot className="h-4 w-4 text-primary" /></div>
              <div className="max-w-[85%] min-w-0 space-y-3">
                <div className={`rounded-2xl rounded-tl-sm border bg-card px-4 py-3 ${m.error ? "border-rose-500/40" : ""}`}>
                  <Answer text={m.content} sources={m.sources} />
                  {!m.error && (
                    <div className="mt-3 flex flex-wrap items-center gap-2">
                      {m.grounded ? (
                        <Badge tone="good"><ShieldCheck className="h-3 w-3" /> Grounded in page</Badge>
                      ) : (
                        <Badge tone="warn"><ShieldAlert className="h-3 w-3" /> No citation — verify</Badge>
                      )}
                      {m.latency_ms != null && (
                        <Badge><Clock className="h-3 w-3" /> {(m.latency_ms / 1000).toFixed(1)}s</Badge>
                      )}
                    </div>
                  )}
                </div>
                {m.sources?.length > 0 && (
                  <div className="space-y-1.5">
                    <p className="text-[11px] font-medium text-muted-foreground">
                      Sources ({m.sources.filter((s) => s.cited).length} cited · {m.sources.length} retrieved after re-ranking)
                    </p>
                    {m.sources.map((s) => <SourceCard key={s.id} source={s} />)}
                  </div>
                )}
              </div>
            </div>
          )
        )}

        {busy && (
          <div className="flex gap-3 animate-rise">
            <div className="h-8 w-8 shrink-0 rounded-lg bg-muted grid place-items-center"><Bot className="h-4 w-4 text-primary" /></div>
            <div className="rounded-2xl rounded-tl-sm border bg-card px-4 py-3"><Thinking /></div>
          </div>
        )}
        <div ref={endRef} />
      </div>

      <form onSubmit={(e) => { e.preventDefault(); send(); }} className="p-4 border-t bg-card/40 backdrop-blur flex gap-2">
        <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Ask about this page…" className="h-11" />
        <Button type="submit" size="icon" className="h-11 w-11" disabled={busy || !q.trim()}>
          <Send className="h-4 w-4" />
        </Button>
      </form>
    </section>
  );
}
