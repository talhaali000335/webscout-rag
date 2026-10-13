import { useEffect, useRef, useState } from "react";
import Sidebar from "./components/Sidebar";
import Chat from "./components/Chat";
import LoginModal from "./components/LoginModal";
import { cancelJob, chat, forgetLogins, getJob, ingest, resumeJob } from "./lib/api";

const load = (k, d) => {
  try { return JSON.parse(localStorage.getItem(k)) ?? d; } catch { return d; }
};
const save = (k, v) => { try { localStorage.setItem(k, JSON.stringify(v)); } catch {} };

export default function App() {
  const [pages, setPages] = useState(() => load("ws.pages", []));
  const [activeCid, setActiveCid] = useState(() => load("ws.active", null));
  const [threads, setThreads] = useState({});      // cid -> messages
  const [busy, setBusy] = useState(false);
  const pagesRef = useRef(pages);
  pagesRef.current = pages;

  useEffect(() => save("ws.pages", pages), [pages]);
  useEffect(() => save("ws.active", activeCid), [activeCid]);

  const patch = (cid, p) => setPages((ps) => ps.map((x) => (x.cid === cid ? { ...x, ...p } : x)));

  // poll running jobs
  useEffect(() => {
    const t = setInterval(async () => {
      for (const p of pagesRef.current) {
        if (!["queued", "running", "needs_login"].includes(p.status) || !p.jobId) continue;
        try {
          const j = await getJob(p.jobId);
          if (j.status === "ready") {
            patch(p.cid, { status: "ready", title: j.title, chunks: Number(j.chunks) });
            setActiveCid((a) => a ?? p.cid);
          } else if (j.status === "error") patch(p.cid, { status: "error", error: j.error });
          else if (j.status === "needs_login") patch(p.cid, { status: "needs_login", stage: j.stage, loginReason: j.login_reason });
          else patch(p.cid, { status: j.status, stage: j.stage });
        } catch { patch(p.cid, { status: "error", error: "Lost track of this job. Retry." }); }
      }
    }, 1500);
    return () => clearInterval(t);
  }, []);

  const add = async (url, force = false, loginFirst = false) => {
    try {
      const r = await ingest(url, force, loginFirst);
      const entry = { cid: r.collection_id, url: r.url, title: r.title || r.url, status: r.status,
                      stage: "queued", jobId: r.job_id, chunks: r.chunks };
      setPages((ps) => [entry, ...ps.filter((x) => x.cid !== entry.cid)]);
      if (r.status === "ready") setActiveCid(r.collection_id);
    } catch (e) {
      const cid = "err-" + Date.now();
      setPages((ps) => [{ cid, url, title: url, status: "error", error: e.message }, ...ps]);
    }
  };

  const remove = (cid) => {
    setPages((ps) => ps.filter((x) => x.cid !== cid));
    if (activeCid === cid) setActiveCid(null);
  };

  const loginPage = pages.find((p) => p.status === "needs_login");
  const doContinue = async () => { try { await resumeJob(loginPage.jobId); patch(loginPage.cid, { status: "running", stage: "scraping" }); } catch {} };
  const doCancel = async () => { try { await cancelJob(loginPage.jobId); } catch {} patch(loginPage.cid, { status: "error", error: "Sign-in cancelled." }); };
  const forget = async () => { try { const r = await forgetLogins(); alert(`Removed ${r.deleted} saved login(s).`); } catch { alert("Could not remove logins."); } };

  const send = async (question) => {
    const cid = activeCid;
    const history = (threads[cid] || []).filter((m) => !m.error).map((m) => ({ role: m.role, content: m.content }));
    setThreads((t) => ({ ...t, [cid]: [...(t[cid] || []), { role: "user", content: question }] }));
    setBusy(true);
    try {
      const r = await chat(cid, question, history);
      setThreads((t) => ({ ...t, [cid]: [...t[cid], { role: "assistant", ...r, content: r.answer }] }));
    } catch (e) {
      let msg = e.message;
      if (e.status === 404) { patch(cid, { status: "expired" }); msg = "This page's cache expired. Click the retry icon in the sidebar to re-index it."; }
      if (e.status === 429) msg = "Slow down a little — too many requests.";
      setThreads((t) => ({ ...t, [cid]: [...t[cid], { role: "assistant", content: msg, error: true }] }));
    } finally { setBusy(false); }
  };

  const active = pages.find((p) => p.cid === activeCid && p.status === "ready");

  return (
    <div className="h-screen flex flex-col md:flex-row">
      <Sidebar pages={pages} activeCid={activeCid} onSelect={setActiveCid} onAdd={add}
               onRetry={(p) => add(p.url, true)} onRemove={remove} onForget={forget} />
      {loginPage && <LoginModal key={loginPage.jobId} page={loginPage} onContinue={doContinue} onCancel={doCancel} />}
      <Chat page={active} messages={threads[activeCid] || []} busy={busy} onSend={send} />
    </div>
  );
}
