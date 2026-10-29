const ports = new Set();
const sticky = new Map();      // event -> last message, replayed to new tabs
const STICKY = new Set(["state", "playlist", "rds", "new_track", "progress", "toplay", "users"]);
const lockOwner = new Map();   // lock id -> port that holds it
const lockState = new Map();   // lock id -> true (as reported by server)
const fm95Subs = new Set();

let ws = null, retry = 0, status = "closed", inflight = 0, pollTimer = null;

const toPort = (p, m) => { try { p.postMessage(m); } catch {} };
const toAll = m => ports.forEach(p => toPort(p, m));
const sendServer = o => { if (ws && ws.readyState === 1) ws.send(JSON.stringify(o)); };

function setStatus(s) { status = s; toAll({ event: "_status", data: s }); }

function connect() {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  ws = new WebSocket(`${proto}://${location.host}/ws`);

  ws.onopen = () => {
    retry = 0;
    setStatus("open");
    lockOwner.forEach((_, id) => sendServer({ action: "lock", id })); // server forgot them
    updatePolling();
  };

  ws.onmessage = e => {
    let m; try { m = JSON.parse(e.data); } catch { return; }

    if (m.event === "fm95") {
      inflight = 0;
      fm95Subs.forEach(p => toPort(p, m));
      return;
    }
    if (m.event === "state" && m.data?.locks) {
      lockState.clear();
      for (const id in m.data.locks) lockState.set(id, true);
    }
    if (m.event === "lock") {
      if (m.error) lockOwner.delete(m.id);           // server refused our claim
      else if (m.data) lockState.set(m.id, true);
      else lockState.delete(m.id);
    }
    if (STICKY.has(m.event)) sticky.set(m.event, m);
    toAll(m);
  };

  ws.onclose = () => {
    setStatus("closed");
    inflight = 0;
    updatePolling();
    setTimeout(connect, Math.min(1000 * 2 ** retry++, 10000));
  };
}

function updatePolling() {
  const want = fm95Subs.size > 0 && ws && ws.readyState === 1;
  if (want && !pollTimer) {
    pollTimer = setInterval(() => {
      if (inflight && Date.now() - inflight < 500) return;   // one request in flight at a time
      inflight = Date.now();
      sendServer({ action: "fm95", data: "/w==" });
    }, 60);
  } else if (!want && pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
}

function attach(port) {
  ports.add(port);
  toPort(port, { event: "_status", data: status });
  sticky.forEach(m => toPort(port, m));
  lockState.forEach((v, id) => toPort(port, { event: "lock", id, data: v }));
}

function drop(port) {
  ports.delete(port);
  fm95Subs.delete(port);
  for (const [id, p] of lockOwner) {
    if (p === port) { lockOwner.delete(id); sendServer({ action: "unlock", id }); }
  }
  updatePolling();
}

function handle(port, m) {
  if (!ports.has(port)) attach(port);   // e.g. tab restored from bfcache

  switch (m.action) {
    case "_hello": return;
    case "_bye": return drop(port);
    case "fm95_sub": fm95Subs.add(port); updatePolling(); return;
    case "fm95_unsub": fm95Subs.delete(port); updatePolling(); return;
    case "lock":
      if (lockOwner.has(m.id) && lockOwner.get(m.id) !== port)
        return toPort(port, { event: "lock", id: m.id, data: true, error: "already locked" });
      lockOwner.set(m.id, port);
      break;
    case "unlock":
      if (lockOwner.get(m.id) !== port)
        return toPort(port, { event: "error", error: "not lock owner" });
      lockOwner.delete(m.id);
      break;
  }
  sendServer(m);
}

onconnect = e => {
  const port = e.ports[0];
  attach(port);
  port.onmessage = ev => handle(port, ev.data);
  if (!ws) connect();
};