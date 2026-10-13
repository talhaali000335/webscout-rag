// All calls go to /api (Vite proxy in dev, nginx proxy in Docker)

// A random id for THIS browser. The server uses it so only you can see your sign-in
// window and use your saved logins.
export function getClientId() {
  try {
    let id = localStorage.getItem("ws.client");
    if (!id) {
      id = (crypto.randomUUID?.() ?? String(Math.random()).slice(2) + Date.now());
      localStorage.setItem("ws.client", id);
    }
    return id;
  } catch {
    return "anon-" + Math.random().toString(36).slice(2);
  }
}
const CLIENT = getClientId();

async function req(path, body, method) {
  const res = await fetch("/api" + path, {
    method: method || (body ? "POST" : "GET"),
    headers: { "X-Client-Id": CLIENT, ...(body ? { "Content-Type": "application/json" } : {}) },
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const err = new Error(typeof data.detail === "string" ? data.detail : "Request failed");
    err.status = res.status;
    throw err;
  }
  return data;
}

export const ingest = (url, force = false, login_first = false) =>
  req("/ingest", { url, force, login_first });
export const getJob = (id) => req(`/jobs/${id}`);
export const chat = (collection_id, question, history) =>
  req("/chat", { collection_id, question, history });
export const resumeJob = (id) => req(`/jobs/${id}/resume`, {});
export const cancelJob = (id) => req(`/jobs/${id}/cancel`, {});
export const forgetLogins = () => req("/sessions", null, "DELETE");

export const browserSocketUrl = (jobId) => {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  return `${proto}://${location.host}/api/ws/browser/${jobId}?client=${encodeURIComponent(CLIENT)}`;
};
