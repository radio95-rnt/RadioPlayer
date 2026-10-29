let playlist = [];
let queue = [];
let last_q_len = Infinity;
let currentTrackPath = "";
let currentTrackIndex = 0;
let selectedPlaylistIndex = null;
let selectedDir = null;
let basePath = "";
let subBasePath = "";
let skipCount = 0;
let skipCountToRender = 0;
let indexDigits = 1;
let skippedIndices = [];
let lastElapsed = 0;
let lastUpdateTime = 0;
let currentRealTotal = 1;
let pollLockHeld = false;
let alarmEnabled = false;
let alarmFired = false;
let alarmAudioCtx = null;

function toggleSection(id) {
    const pairMap = {
        'section-dirs': 'section-subdir',
        'section-subdir': 'section-dirs'
    };

    const el = document.getElementById(id);
    const partnerId = pairMap[id];

    if (partnerId) {
        const willCollapse = !el.classList.contains('collapsed');
        const partner = document.getElementById(partnerId);

        if (willCollapse && partner.classList.contains('collapsed')) {
            partner.classList.remove('collapsed');
        }
    }

    el.classList.toggle('collapsed');
}

function formatTime(s) {
    s = Number(s || 0);
    const h = Math.floor(s / 3600);
    const m = Math.floor((s % 3600) / 60);
    const sec = Math.floor(s % 60);
    const parts = h ? [h, m, sec] : [m, sec];
    return parts.map(x => String(x).padStart(2, "0")).join(":");
}

function clearListSelections(...ids) {
    for (const id of ids) {
        Array.from(document.getElementById(id).children).forEach(c => c.classList.remove("selected"));
    }
}

const PANELS = {
    fsdb: { title: "FSDB", url: "/fsdb.html?embed", w: 900, h: 600 },
    fm95: { title: "FM95", url: "/fm95.html?embed", w: 760, h: 640 },
};
const MIN_W = 320, MIN_H = 200;
const winRoot = document.getElementById("windows");
const wins = new Map();            // name -> { el, g }
let zTop = 50;
let savedGeo = {};
try { savedGeo = JSON.parse(localStorage.getItem("winGeo") || "{}"); } catch {}

const saveGeo = () => localStorage.setItem("winGeo",
    JSON.stringify(Object.fromEntries([...wins].map(([n, w]) => [n, w.g]))
        .constructor === Object ? { ...savedGeo, ...Object.fromEntries([...wins].map(([n, w]) => [n, w.g])) } : savedGeo));

function clampGeo(g) {
    g.w = Math.min(Math.max(g.w, MIN_W), window.innerWidth);
    g.h = Math.min(Math.max(g.h, MIN_H), window.innerHeight);
    g.x = Math.min(Math.max(g.x, 80 - g.w), window.innerWidth - 80);   // keep part of the bar reachable
    g.y = Math.min(Math.max(g.y, 0), window.innerHeight - 30);
}

function applyGeo(w) {
    const { el, g } = w;
    clampGeo(g);
    el.style.left = g.x + "px";
    el.style.top = g.y + "px";
    el.style.width = g.w + "px";
    el.style.height = g.h + "px";
    el.classList.toggle("maximized", !!g.max);
    el.querySelector(".win-max").textContent = g.max ? "❐" : "□";
}

function focusWin(name) {
    wins.forEach((w, n) => w.el.classList.toggle("focused", n === name));
    const w = wins.get(name);
    if (w) w.el.style.zIndex = ++zTop;
}

function syncButtons() {
    document.querySelectorAll("[data-panel]").forEach(b =>
        b.classList.toggle("activated", wins.has(b.dataset.panel)));
}

function openPanel(name) {
    const p = PANELS[name];
    if (!p) return;
    if (wins.has(name)) return focusWin(name);

    const n = wins.size;
    const g = savedGeo[name] ? { ...savedGeo[name] } : {
        w: p.w, h: p.h,
        x: Math.round((window.innerWidth - p.w) / 2) + n * 30,
        y: Math.round((window.innerHeight - p.h) / 2) + n * 30,
    };
    if (window.innerWidth <= 800) g.max = true;

    const el = document.createElement("div");
    el.className = "win";
    el.innerHTML = `
        <div class="win-bar">
            <span class="win-title">${p.title}</span>
            <button class="btn win-max" title="Maximize">□</button>
            <button class="btn win-close" title="Close">✕</button>
        </div>
        <div class="win-body">
            <iframe src="${p.url}"></iframe>
            <div class="win-shield"></div>
        </div>
        ${["n","s","e","w","nw","ne","sw","se"].map(d => `<div class="rz" data-dir="${d}"></div>`).join("")}`;
    winRoot.appendChild(el);

    const w = { el, g };
    wins.set(name, w);
    applyGeo(w);
    focusWin(name);
    syncButtons();

    el.addEventListener("pointerdown", () => focusWin(name), true);

    // buttons
    const toggleMax = () => { g.max = !g.max; applyGeo(w); persist(); };
    el.querySelector(".win-max").addEventListener("click", toggleMax);
    el.querySelector(".win-close").addEventListener("click", () => closePanel(name));

    // drag by title bar
    const bar = el.querySelector(".win-bar");
    bar.addEventListener("dblclick", e => { if (e.target === bar || e.target.classList.contains("win-title")) toggleMax(); });
    bar.addEventListener("pointerdown", e => {
        if (e.target.closest("button") || g.max || e.button !== 0) return;
        const sx = e.clientX, sy = e.clientY, ox = g.x, oy = g.y;
        bar.setPointerCapture(e.pointerId);
        document.body.classList.add("dragging");
        const move = ev => { g.x = ox + ev.clientX - sx; g.y = oy + ev.clientY - sy; applyGeo(w); };
        const up = () => {
            document.body.classList.remove("dragging");
            bar.removeEventListener("pointermove", move);
            bar.removeEventListener("pointerup", up);
            bar.removeEventListener("pointercancel", up);
            persist();
        };
        bar.addEventListener("pointermove", move);
        bar.addEventListener("pointerup", up);
        bar.addEventListener("pointercancel", up);
    });

    // resize from edges and corners
    el.querySelectorAll(".rz").forEach(h => h.addEventListener("pointerdown", e => {
        if (e.button !== 0) return;
        const dir = h.dataset.dir;
        const sx = e.clientX, sy = e.clientY, o = { ...g };
        h.setPointerCapture(e.pointerId);
        document.body.classList.add("dragging");
        const move = ev => {
            const dx = ev.clientX - sx, dy = ev.clientY - sy;
            if (dir.includes("e")) g.w = Math.max(MIN_W, o.w + dx);
            if (dir.includes("s")) g.h = Math.max(MIN_H, o.h + dy);
            if (dir.includes("w")) { g.w = Math.max(MIN_W, o.w - dx); g.x = o.x + (o.w - g.w); }
            if (dir.includes("n")) { g.h = Math.max(MIN_H, o.h - dy); g.y = o.y + (o.h - g.h); }
            applyGeo(w);
        };
        const up = () => {
            document.body.classList.remove("dragging");
            h.removeEventListener("pointermove", move);
            h.removeEventListener("pointerup", up);
            h.removeEventListener("pointercancel", up);
            persist();
        };
        h.addEventListener("pointermove", move);
        h.addEventListener("pointerup", up);
        h.addEventListener("pointercancel", up);
    }));
}

function persist() {
    wins.forEach((w, n) => { savedGeo[n] = { ...w.g }; });
    localStorage.setItem("winGeo", JSON.stringify(savedGeo));
}

function closePanel(name) {
    const w = wins.get(name);
    if (!w) return;
    w.el.remove();                 // unloads the iframe → pagehide → worker drops its subscriptions
    wins.delete(name);
    syncButtons();
}

document.querySelectorAll("[data-panel]").forEach(b =>
    b.addEventListener("click", () =>
        wins.has(b.dataset.panel) ? closePanel(b.dataset.panel) : openPanel(b.dataset.panel)));

addEventListener("resize", () => wins.forEach(applyGeo));

// deep links: /#fsdb or /#fsdb,fm95
location.hash.slice(1).split(",").forEach(n => { if (PANELS[n]) openPanel(n); });

function initLayout() {
    if (window.innerWidth <= 800) {
        ["section-playlist", "section-subdir"].forEach(id =>
            document.getElementById(id).classList.add("collapsed")
        );
    }
}

function connectWs() {
    const statusEl = document.getElementById("server-status");
    statusEl.textContent = "connecting...";

    WS.on("_status", s => {
        if (s === "open") {
            statusEl.textContent = "connected";
            // not every tab gets these from the replay cache, so ask again
            wsSend({ action: "get_toplay" });
            wsSend({ action: "skipc" });
            wsSend({ action: "skipi" });
        } else {
            statusEl.textContent = "disconnected — reconnecting...";
        }
    });

    // full message objects, same shape handleMessage already expects
    WS.on("*", m => {
        if (m.event?.startsWith("_")) return;   // skip worker-internal events
        handleMessage(m);
    });
}

function wsSend(obj) {
    WS.send(obj);
}
function handleMessage(msg) {
    switch (msg.event) {
        case "state": {
            const d = msg.data || {};
            if(d.dirs) updateDirs(d.dirs);
            if(d.track) applyProgressState(d.track);
            break;
        }
        case "rds":
            document.getElementById("rds-text").textContent = msg.data?.rt ?? "";
            break;
        case "playlist":
            playlist = msg.data?.playlist || [];
            renderAll();
            break;
        case "new_track":
            applyTrackState(msg.data);
            wsSend({ action: "get_toplay" });
            wsSend({ action: "skipc" });
            wsSend({ action: "skipi" });
            break;
        case "progress":
            applyProgressState(msg.data);
            break;
        case "toplay":
            queue = msg.data.data || [];
            renderAll();
            break;
        case "request_dir":
            applySubdir(msg.data || {});
            break;
        case "skipc":
            skipCount = msg.data?.data ?? 0;
            document.getElementById("skpn-count").textContent = skipCount;
            renderAll();
            break;
        case "skipi":
            skippedIndices = msg.data?.data ?? skippedIndices;
            renderAll();
            break;
        case "users":
            document.getElementById("user-count").textContent = msg.data;
            break;
    }
}

function renderAll() {
    skipCountToRender = skipCount;
    renderQueue();
    renderPlaylist();
}

function trackLabel(track, index) {
    const prefix = track.official ? "(official) " : "(unofficial) ";
    return prefix + track.path.replace(basePath, "").slice(1);
}

function applyTrackState(payload) {
    const track = payload.track || {};
    const next = payload.next_track || {};
    currentTrackPath = track.path;
    currentTrackIndex = payload.index;
    indexDigits = playlist.length.toString().length;
    document.getElementById("now-track").textContent =
        `${String(currentTrackIndex).padStart(indexDigits, "0")}: ${trackLabel(track)}`;
    document.getElementById("next-track").textContent = trackLabel(next);
    renderAll();
}

function applyProgressState(payload) {
    const track = payload.track || {};
    const next = payload.next_track || {};
    const elapsed = Number(payload.elapsed || 0);
    const total = Number(payload.total || payload.real_total || 1) || 1;
    const realTotal = Number(payload.real_total || payload.total || 1) || 1;
    const percent = Math.max(0, Math.min(100, (elapsed / realTotal) * 100));

    lastElapsed = elapsed;
    lastUpdateTime = performance.now();
    currentRealTotal = realTotal;

    document.getElementById("time-label").textContent =
        `${formatTime(elapsed)} / ${formatTime(total)} (${formatTime(total - elapsed)})`;

    currentTrackIndex = payload.index;
    if (track.path) {
        currentTrackPath = track.path;
        document.getElementById("now-track").textContent =
            `${String(currentTrackIndex).padStart(indexDigits, "0")}: ${trackLabel(track)}`;
    }
    if (next.path) {
        document.getElementById("next-track").textContent =
            `${next.official ? "(official)" : "(unofficial)"} ${next.path.replace(basePath, "").slice(1)}`;
    }
}

function renderPlaylist() {
    const ul = document.getElementById("playlist-ul");
    ul.innerHTML = "";
    indexDigits = playlist.length.toString().length;
    let currentIndex = null;

    playlist.forEach((t, i) => {
        const li = document.createElement("li");
        const path = t.path || "<no path>";
        const displayPath = (t.official ? "(official) " : "(unofficial) ") + path.replace(basePath, "").slice(1);
        li.dataset.path = path;
        li.dataset.idx = i;
        li.addEventListener("click", () => selectPlaylistItem(i, li));

        if (path === currentTrackPath && i === currentTrackIndex) {
            li.classList.add("current");
            currentIndex = i;
        } else if (i === currentTrackIndex) {
            li.classList.add("pointer");
            currentIndex = i - 1;
            if(skipCountToRender > 0) {
                li.style.textDecoration = "line-through";
                skipCountToRender--;
            }
        }

        if (skipCountToRender > 0 && i > currentTrackIndex) {
            li.style.textDecoration = "line-through";
            skipCountToRender--;
        }
        if (skippedIndices.includes(i)) li.style.textDecoration = "line-through";

        li.textContent = `${i === currentTrackIndex ? "▶ " : "  "}${String(i).padStart(indexDigits, "0")}: ${displayPath}`;
        ul.appendChild(li);
    });

    if (currentIndex !== null) ul.children[currentIndex]?.scrollIntoView({ block: "center", behavior: "smooth" });
    updateControls();
}

function renderQueue() {
    const ul = document.getElementById("queue-ul");
    ul.innerHTML = "";
    var i = 0;
    queue.forEach(path => {
        const li = document.createElement("li");
        li.dataset.idx = i++;

        var c = path.replace(basePath, "");
        if(c.startsWith("!")) c = "(unofficial) " + c.slice(2)
        else c = "(official) " + c.slice(1)
        li.textContent = c;
        if (skipCountToRender > 0) {
            li.style.textDecoration = "line-through";
            skipCountToRender--;
        }

        li.addEventListener("click", () => {
            wsSend({ action: "remove_toplay", indexes: [Number(li.dataset.idx)] });
            renderAll();
        });
        li.addEventListener("contextmenu", e => {
            e.preventDefault();
            wsSend({ action: "toggle_official_toplay", indexes: [Number(li.dataset.idx)] });
            renderAll();
        })
        ul.appendChild(li);
    });

    if (alarmEnabled) {
        if (queue.length === 0 && !alarmFired && last_q_len > queue.length) {
            playAlarmTone();
            alarmFired = true;
        } else if (queue.length !== 1) {
            alarmFired = false;
        }
    }
    last_q_len = queue.length;
    updateControls();
}

function updateDirs(payload) {
    const box = document.getElementById("dirs-box");
    box.innerHTML = "";
    basePath = payload.base || "";

    const addItem = (name, onClick, onContext) => {
        const node = document.createElement("div");
        node.className = "item";
        node.textContent = name;
        node.addEventListener("click", (e) => onClick(node, e));
        if(onContext !== undefined) node.addEventListener("contextmenu", (e) => onContext(node, e));
        box.appendChild(node);
    };

    (payload.dirs || []).sort().forEach(name => {
        if (!name.startsWith(".")) addItem(name, (node, e) => onDirClicked(name, node));
    });

    (payload.files || []).sort().forEach(name => {
        if (!name.startsWith(".")) {
            addItem(name, () => {
                wsSend({ action: "add_to_toplay", songs: [basePath.replace(/\/$/, "") + "/" + name], top: false })
            }, (node, e) => {
                e.preventDefault()
                wsSend({ action: "add_to_toplay", songs: [basePath.replace(/\/$/, "") + "/" + name], top: true })
            });
        }
    });
}

function onDirClicked(name, node) {
    if (node.classList.contains("selected")) {
        node.classList.remove("selected");
        selectedDir = null;
        document.getElementById("subdir-box").innerHTML = "";
        return;
    }
    clearListSelections("dirs-box", "playlist-ul");
    node.classList.add("selected");
    selectedDir = name;
    wsSend({ action: "request_dir", what: selectedDir });
}

function applySubdir(payload) {
    if (payload.dir !== selectedDir) return;
    const box = document.getElementById("subdir-box");
    box.innerHTML = "";
    subBasePath = payload.base || "";

    (payload.files || []).sort().forEach(f => {
        const node = document.createElement("div");
        node.className = "item";
        node.textContent = f;
        node.addEventListener("click", () => {
            wsSend({ action: "add_to_toplay", songs: [subBasePath.replace(/\/$/, "") + "/" + f], top: false });
        });
        node.addEventListener("contextmenu", (e) => {
            e.preventDefault()
            wsSend({ action: "add_to_toplay", songs: [subBasePath.replace(/\/$/, "") + "/" + f], top: true });
        });
        box.appendChild(node);
    });
}

function selectPlaylistItem(i, el) {
    const action = skippedIndices.includes(i)
        ? { action: "skipi", remove: i }
        : { action: "skipi", add: i };
    wsSend(action);
    updateControls();
}

function updateControls() {
    document.getElementById("clear-btn").disabled = queue.length === 0;
}

function toggleAlarm() {
    alarmEnabled = !alarmEnabled;
    document.getElementById("alarm-btn").classList.toggle("activated", alarmEnabled);
    if (!alarmEnabled) alarmFired = false;
}

function playAlarmTone() {
    if (!alarmAudioCtx) alarmAudioCtx = new (window.AudioContext || window.webkitAudioContext)();
    const ctx = alarmAudioCtx;
    const now = ctx.currentTime;
    const beeps = 5;
    for (let i = 0; i < beeps; i++) {
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.type = "square";
        osc.frequency.value = 880;
        const t = now + i * 0.45;
        gain.gain.setValueAtTime(0, t);
        gain.gain.linearRampToValueAtTime(1, t + 0.02);
        gain.gain.setValueAtTime(1, t + 0.28);
        gain.gain.linearRampToValueAtTime(0, t + 0.32);
        osc.connect(gain);
        gain.connect(ctx.destination);
        osc.start(t);
        osc.stop(t + 0.35);
    }
}

document.getElementById("alarm-btn").addEventListener("click", e => {
    e.stopPropagation();
    toggleAlarm();
});

document.getElementById("skip-btn").addEventListener("click", () => wsSend({ action: "skip" }));
document.getElementById("skpn-inc").addEventListener("click", () => wsSend({ action: "skipc", add: 1 }));
document.getElementById("skpn-dec").addEventListener("click", () => wsSend({ action: "skipc", remove: -1 }));

document.getElementById("jingle-btn").addEventListener("click", () => wsSend({ action: "jingle" }));
document.getElementById("jingle-btn").addEventListener("contextmenu", e => {
    e.preventDefault();
    wsSend({ action: "jingle", top: true });
});

document.getElementById("queue-title").addEventListener("click", () => toggleSection("section-queue"));
document.getElementById("clear-btn").addEventListener("click", e => {
    e.stopPropagation();
    wsSend({ action: "clear_toplay" });
});

document.addEventListener("keydown", e => {
    if (e.target.tagName === "INPUT") return;
    // else if (e.key === "s") wsSend({ action: "skip" });
    else if (e.key === "n") wsSend({ action: "skipc", add: 1 });
    else if (e.key === "m") wsSend({ action: "skipc", remove: -1 });
    else if (e.key.toLowerCase() === "j") wsSend({ action: "jingle", top: e.shiftKey });
});

let whepPc = null;
let whepAudio = null;
let whepConnected = false;

function whepLog(msg, type = "info") {
    const el = document.getElementById("whep-log");
    const line = document.createElement("div");
    line.className = "wlog-" + type;
    line.textContent = `[${new Date().toLocaleTimeString("pl-PL")}] ${msg}`;
    el.appendChild(line);
    el.scrollTop = el.scrollHeight;
    while (el.children.length > 30) el.removeChild(el.firstChild);
}

function whepSetDot(state) {
    document.getElementById("whep-dot").className =
        "whep-status-dot" + (state !== "idle" ? " " + state : "");
    const btn = document.getElementById("whep-btn");
    const active = state === "connected" || state === "connecting";
    btn.textContent = active ? "⏹ Disconnect" : "▶ Connect";
    btn.classList.toggle("activated", active);
}

function whepSetVol(v) {
    document.getElementById("whep-vol-out").textContent =
        (Math.round(v * 1000) / 10).toFixed(1) + "%";
    if (whepAudio) whepAudio.volume = parseFloat(v);
}

function whepToggle() {
    if (whepConnected || whepPc) whepDisconnect();
    else whepConnect();
}

function whepDisconnect() {
    whepConnected = false;
    if (whepPc) { try { whepPc.close(); } catch (e) {} whepPc = null; }
    if (whepAudio) { whepAudio.pause(); whepAudio.srcObject = null; whepAudio = null; }
    whepSetDot("idle");
    whepLog("Disconnected");
}

async function whepConnect() {
    const url = document.getElementById("whep-url-input").value.trim();
    if (!url) return;
    whepSetDot("connecting");
    whepLog("Creating peer connection…");
    try {
        whepPc = new RTCPeerConnection();

        whepPc.ontrack = e => {
            whepLog("Track received, starting playback", "ok");
            whepAudio = new Audio();
            whepAudio.srcObject = e.streams[0];
            whepAudio.volume = parseFloat(document.getElementById("whep-vol").value);
            whepAudio.play()
                .then(() => {
                    whepLog("Audio playing", "ok");
                    whepConnected = true;
                    whepSetDot("connected");
                })
                .catch(() => {
                    whepLog("Autoplay blocked — click anywhere to resume", "err");
                    document.addEventListener("click", () => whepAudio?.play(), { once: true });
                });
        };

        whepPc.onconnectionstatechange = () => {
            whepLog("State: " + whepPc.connectionState);
            if (["failed", "disconnected"].includes(whepPc.connectionState)) {
                whepLog("Connection lost", "err");
                whepDisconnect();
                whepSetDot("error");
            }
        };

        whepPc.oniceconnectionstatechange = () => whepLog("ICE: " + whepPc.iceConnectionState);
        whepPc.addTransceiver("audio", { direction: "recvonly" });

        const offer = await whepPc.createOffer();
        offer.sdp = offer.sdp
            .replace(/useinbandfec=1/g, "useinbandfec=1;stereo=1;sprop-stereo=1")
            .replace(/minptime=10/g, "minptime=10;ptime=10;maxptime=10");
        await whepPc.setLocalDescription(offer);

        whepLog("Sending offer to " + url);
        const resp = await fetch(url, {
            method: "POST",
            headers: { "Content-Type": "application/sdp", Accept: "application/sdp" },
            body: whepPc.localDescription.sdp,
        });
        if (!resp.ok) throw new Error(`Server returned ${resp.status} ${resp.statusText}`);

        const answerSdp = await resp.text();
        whepLog(`Got SDP answer (${answerSdp.length} bytes)`, "ok");
        await whepPc.setRemoteDescription({ type: "answer", sdp: answerSdp });
        whepLog("Waiting for ICE + track…");
    } catch (err) {
        whepLog("Error: " + err.message, "err");
        whepDisconnect();
        whepSetDot("error");
    }
}

function animateProgress() {
    const now = performance.now();
    const delta = (now - lastUpdateTime) / 1000; // seconds
    const smoothElapsed = lastElapsed + delta;

    const percent = Math.max(0, Math.min(100, (smoothElapsed / currentRealTotal) * 100));
    document.getElementById("prog-fill").style.width = percent + "%";

    requestAnimationFrame(animateProgress);
}

initLayout();
connectWs();
requestAnimationFrame(animateProgress);
setTimeout(() => {
    document.getElementById("prog-fill").classList.remove("init")
}, 1000)