const WS = (() => {
  const handlers = new Map();
  const on = (ev, fn) => {
    if (!handlers.has(ev)) handlers.set(ev, new Set());
    handlers.get(ev).add(fn);
    return () => handlers.get(ev).delete(fn);
  };
  const emit = m => {
    handlers.get(m.event ?? "_raw")?.forEach(f => f(m.data, m));
    handlers.get("*")?.forEach(f => f(m));
  };

  let send;

  if ("SharedWorker" in window) {
    const w = new SharedWorker("/ws-worker.js");
    w.port.addEventListener("message", e => emit(e.data));
    addEventListener("DOMContentLoaded", () => w.port.start());
    send = m => w.port.postMessage(m);
    addEventListener("pagehide", () => send({ action: "_bye" }));
    addEventListener("pageshow", e => { if (e.persisted) send({ action: "_hello" }); });
  } else {
    let ws, retry = 0, poll = null;
    const open = () => {
      ws = new WebSocket(`${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws`);
      ws.onopen = () => { retry = 0; emit({ event: "_status", data: "open" }); };
      ws.onmessage = e => { try { emit(JSON.parse(e.data)); } catch {} };
      ws.onclose = () => {
        emit({ event: "_status", data: "closed" });
        setTimeout(open, Math.min(1000 * 2 ** retry++, 10000));
      };
    };
    open();
    send = m => {
      if (m.action === "fm95_sub") {
        poll ??= setInterval(() => ws.readyState === 1 && ws.send(JSON.stringify({ action: "fm95", data: "/w==" })), 60);
      } else if (m.action === "fm95_unsub") {
        clearInterval(poll); poll = null;
      } else if (ws.readyState === 1) ws.send(JSON.stringify(m));
    };
  }

  return { on, send };
})();