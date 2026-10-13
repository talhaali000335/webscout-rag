import { useEffect, useRef, useState } from "react";
import { Lock, ShieldAlert, Loader2, CheckCircle2, X } from "lucide-react";
import { Button } from "./ui/button";
import { browserSocketUrl } from "../lib/api";

const NAMED = new Set(["Enter", "Backspace", "Tab", "Escape", "Delete", "Home", "End",
  "PageUp", "PageDown", "ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight"]);

// Live view of the server's browser. You click/type here; events go to the real page.
export default function LoginModal({ page, onContinue, onCancel }) {
  const imgRef = useRef(null);
  const wsRef = useRef(null);
  const urlRef = useRef(null);
  const [connected, setConnected] = useState(false);
  const [pageUrl, setPageUrl] = useState("");
  const [busy, setBusy] = useState(false);

  const insecure = location.protocol === "http:" && !["localhost", "127.0.0.1"].includes(location.hostname);

  useEffect(() => {
    const ws = new WebSocket(browserSocketUrl(page.jobId));
    ws.binaryType = "blob";
    wsRef.current = ws;
    let lastUrl = null;
    ws.onopen = () => setConnected(true);
    ws.onclose = () => setConnected(false);
    ws.onmessage = (m) => {
      if (typeof m.data === "string") {
        try { setPageUrl(JSON.parse(m.data).url || ""); } catch {}
        return;
      }
      const url = URL.createObjectURL(m.data);
      if (imgRef.current) imgRef.current.src = url;
      if (lastUrl) URL.revokeObjectURL(lastUrl);
      lastUrl = url;
    };
    return () => ws.close();
  }, [page.jobId]);

  const send = (ev) => wsRef.current?.readyState === 1 && wsRef.current.send(JSON.stringify(ev));

  const onClick = (e) => {
    const img = imgRef.current;
    const r = img.getBoundingClientRect();
    send({ t: "click", x: (e.clientX - r.left) * (img.naturalWidth / r.width),
           y: (e.clientY - r.top) * (img.naturalHeight / r.height) });
  };
  const onKeyDown = (e) => {
    if (e.ctrlKey || e.metaKey) return;           // let Ctrl+V reach onPaste
    if (e.key.length === 1) { send({ t: "type", text: e.key }); e.preventDefault(); }
    else if (e.key === " ") { send({ t: "key", key: "Space" }); e.preventDefault(); }
    else if (NAMED.has(e.key)) { send({ t: "key", key: e.key }); e.preventDefault(); }
  };
  const onPaste = (e) => { send({ t: "type", text: e.clipboardData.getData("text") }); e.preventDefault(); };
  const onWheel = (e) => send({ t: "scroll", dy: e.deltaY });

  return (
    <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm grid place-items-center p-4">
      <div className="w-full max-w-4xl rounded-2xl border bg-card shadow-2xl animate-rise flex flex-col max-h-[95vh]">
        <div className="flex items-start gap-3 p-4 border-b">
          <div className="h-9 w-9 rounded-lg bg-amber-500/15 grid place-items-center shrink-0">
            <Lock className="h-4 w-4 text-amber-400" />
          </div>
          <div className="min-w-0 flex-1">
            <h3 className="font-semibold">Sign-in needed to continue</h3>
            <p className="text-xs text-muted-foreground">
              {page.loginReason || "The site asked you to sign in or pass a check."} Do it below (this is a
              live view of a browser on the server), then press <b>Continue</b>.
            </p>
          </div>
          <Button variant="ghost" size="sm" onClick={onCancel} title="Cancel"><X className="h-4 w-4" /></Button>
        </div>

        {insecure && (
          <div className="mx-4 mt-3 flex gap-2 rounded-lg border border-amber-500/30 bg-amber-500/10 p-2.5 text-xs text-amber-300">
            <ShieldAlert className="h-4 w-4 shrink-0" />
            This page is on plain http — anything you type, including passwords, is not encrypted. Set up
            HTTPS first (see README, "Turn on HTTPS") before signing in to real accounts.
          </div>
        )}

        <div className="p-4 overflow-auto">
          <div className="mb-2 text-[11px] text-muted-foreground truncate">{pageUrl || page.url}</div>
          <div tabIndex={0} ref={urlRef} onKeyDown={onKeyDown} onPaste={onPaste} onWheel={onWheel}
               className="relative rounded-lg border bg-black outline-none focus:ring-2 focus:ring-primary/60 cursor-pointer overflow-hidden">
            <img ref={imgRef} alt="" onClick={(e) => { urlRef.current?.focus(); onClick(e); }}
                 className="w-full select-none" draggable={false}
                 style={{ aspectRatio: "1024 / 720", display: "block" }} />
            {!connected && (
              <div className="absolute inset-0 grid place-items-center text-sm text-muted-foreground">
                <span className="flex items-center gap-2"><Loader2 className="h-4 w-4 animate-spin" /> Connecting to browser…</span>
              </div>
            )}
          </div>
          <p className="mt-2 text-[11px] text-muted-foreground">
            Click the page to focus it, then type. Scroll with the mouse wheel. If you see a captcha, solve it here too.
          </p>
        </div>

        <div className="flex justify-end gap-2 p-4 border-t">
          <Button variant="outline" onClick={onCancel}>Cancel</Button>
          <Button disabled={busy} onClick={async () => { setBusy(true); await onContinue(); setBusy(false); }}>
            <CheckCircle2 className="h-4 w-4" /> I'm signed in — Continue
          </Button>
        </div>
      </div>
    </div>
  );
}
