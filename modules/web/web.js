let ws = null;
let reconnectDelay = 1000;
let playlist = [];
let queue = [];
let currentTrackPath = "";
let currentTrackIndex = 0;
let selectedPlaylistPath = null;
let selectedPlaylistIndex = null;
let selectedDir = null;
let selectedSubFile = null;
let basePath = "";
let subBasePath = "";
let skipCount = 0;
let skipCountToRender = 0;
let indexDigits = 1;
let skippedIndices = [];
let lastElapsed = 0;
let lastUpdateTime = 0;
let currentRealTotal = 1;

function toggleSection(id) {
    document.getElementById(id).classList.toggle("collapsed");
}

function isTnet() {
    return window.location.protocol === "file:" || window.location.hostname.includes("tnet");
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

// ─── Init ─────────────────────────────────────────────────────────────────────

function initLayout() {
    if (window.innerWidth <= 800) {
        ["section-playlist", "section-dirs", "section-subdir"].forEach(id =>
            document.getElementById(id).classList.add("collapsed")
        );
    }
    if (isTnet()) {
        document.getElementById("whep-url-input").value = "https://webrtc.terminal.tnet/radio/whep";
    }
}

// ─── WebSocket ───────────────────────────────────────────────────────────────

function connectWs() {
    const statusEl = document.getElementById("server-status");
    statusEl.textContent = "connecting...";

    ws = new WebSocket(isTnet() ? "https://radio95.tnet/ws" : "/ws");

    ws.addEventListener("open", () => {
        statusEl.textContent = "connected";
        reconnectDelay = 1500;
        ws.send(JSON.stringify({ action: "get_toplay" }));
        ws.send(JSON.stringify({ action: "skipc" }));
        ws.send(JSON.stringify({ action: "skipi" }));
    });

    ws.addEventListener("close", () => {
        statusEl.textContent = "disconnected — reconnecting...";
        setTimeout(connectWs, reconnectDelay);
        reconnectDelay = Math.min(10000, reconnectDelay + 1500);
    });

    ws.addEventListener("error", e => {
        console.error("WS error", e);
        statusEl.textContent = "error";
    });

    ws.addEventListener("message", evt => {
        handleMessage(JSON.parse(evt.data));
    });
}

function wsSend(obj) {
    ws.send(JSON.stringify(obj));
}

// ─── Message Handling ────────────────────────────────────────────────────────

function handleMessage(msg) {
    switch (msg.event) {
        case "state": {
            const d = msg.data || {};
            if (d.dirs) updateDirs(d.dirs);
            if (d.track) applyProgressState(d.track);
            break;
        }
        case "rds":
            document.getElementById("rds-text").textContent = msg.data?.rt ?? "";
            break;
        case "playlist":
            playlist = msg.data || [];
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

// ─── Track State ─────────────────────────────────────────────────────────────

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
        }

        if (skipCountToRender > 0 && i > currentTrackIndex) {
            li.style.textDecoration = "line-through";
            skipCountToRender--;
        }
        if (skippedIndices.includes(i)) {
            li.style.textDecoration = "line-through";
        }

        li.textContent = `${i === currentTrackIndex ? "▶ " : "  "}${String(i).padStart(indexDigits, "0")}: ${displayPath}`;
        ul.appendChild(li);
    });

    if (currentIndex !== null) {
        ul.children[currentIndex]?.scrollIntoView({ block: "center", behavior: "smooth" });
    }
    updateControls();
}

function renderQueue() {
    const ul = document.getElementById("queue-ul");
    ul.innerHTML = "";
    queue.forEach(path => {
        const li = document.createElement("li");
        var c = path.replace(basePath, "");
        if(c.startsWith("!")) c = "(unofficial) " + c.slice(2)
        else c = "(official) " + c.slice(1)
        li.textContent = c;
        if (skipCountToRender > 0) {
            li.style.textDecoration = "line-through";
            skipCountToRender--;
        }
        ul.appendChild(li);
    });
    updateControls();
}

function updateDirs(payload) {
    const box = document.getElementById("dirs-box");
    box.innerHTML = "";
    basePath = payload.base || "";

    const addItem = (name, onClick) => {
        const node = document.createElement("div");
        node.className = "item";
        node.textContent = name;
        node.addEventListener("click", () => onClick(node));
        box.appendChild(node);
    };

    (payload.dirs || []).sort().forEach(name => {
        if (!name.startsWith(".")) addItem(name, node => onDirClicked(name, node));
    });

    (payload.files || []).sort().forEach(name => {
        if (!name.startsWith(".")) {
            addItem(name, node => {
                if (node.classList.contains("selected")) {
                    node.classList.remove("selected");
                    selectedDir = null;
                    selectedSubFile = null;
                    return;
                }
                clearListSelections("playlist-ul", "subdir-box");
                Array.from(box.children).forEach(c => c.classList.remove("selected"));
                node.classList.add("selected");
                node.dataset.type = "file";
                selectedDir = null;
                selectedSubFile = null;
                document.getElementById("subdir-box").innerHTML = "";
            });
        }
    });
}

function onDirClicked(name, node) {
    if (node.classList.contains("selected")) {
        node.classList.remove("selected");
        selectedDir = null;
        selectedSubFile = null;
        document.getElementById("subdir-box").innerHTML = "";
        return;
    }
    clearListSelections("dirs-box", "playlist-ul");
    node.classList.add("selected");
    selectedDir = name;
    selectedSubFile = null;
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
            if (node.classList.contains("selected")) {
                node.classList.remove("selected");
                selectedSubFile = null;
                return;
            }
            clearListSelections("subdir-box", "playlist-ul");
            Array.from(document.getElementById("dirs-box").children).forEach(c => c.classList.remove("selected"));

            // Re-select the parent dir node
            Array.from(document.getElementById("dirs-box").children).forEach(c => {
                if (c.textContent === selectedDir) c.classList.add("selected");
            });

            node.classList.add("selected");
            selectedSubFile = f;
        });
        box.appendChild(node);
    });
}

function selectPlaylistItem(i, el) {
    const path = el.dataset.path;
    if (el.classList.contains("selected")) {
        el.classList.remove("selected");
        selectedPlaylistPath = null;
        updateControls();
        return;
    }
    clearListSelections("playlist-ul", "dirs-box", "subdir-box");
    el.classList.add("selected");
    selectedPlaylistPath = path;
    selectedPlaylistIndex = i;
    updateControls();
}

function addSelectedFileToQueue(top) {
    let fullPath = null;

    if (selectedPlaylistPath != null) {
        const selected = playlist.find(t => t.path === selectedPlaylistPath);
        if (!selected) return false;
        const path = (selected.official ? "" : "!") + selected.path;
        wsSend({ action: "add_to_toplay", songs: [path], top });
        clearListSelections("playlist-ul");
        selectedPlaylistPath = null;
        selectedPlaylistIndex = null;
        updateControls();
        return true;
    }

    if (selectedSubFile && selectedDir) {
        fullPath = subBasePath.replace(/\/$/, "") + "/" + selectedSubFile;
    } else {
        const selectedFileEl = Array.from(document.getElementById("dirs-box").children).find(el => el.classList.contains("selected") && el.dataset.type === "file");
        if (selectedFileEl) {
            fullPath = basePath.replace(/\/$/, "") + "/" + selectedFileEl.textContent;
        }
    }

    if (fullPath) {
        wsSend({ action: "add_to_toplay", songs: [fullPath], top });
        // Dir/subdir selections are intentionally preserved here
        return true;
    }

    return false;
}

function updateControls() {
    document.getElementById("clear-btn").disabled = queue.length === 0;

    const btn = document.getElementById("skipidx-btn");
    if (selectedPlaylistIndex == null) {
        btn.textContent = "⏭+ Skip in playlist";
        btn.disabled = true;
        btn.classList.remove("activated");
    } else if (skippedIndices.includes(selectedPlaylistIndex)) {
        btn.textContent = "✓ Unskip in playlist";
        btn.disabled = false;
        btn.classList.add("activated");
    } else {
        btn.textContent = "⏭+ Skip in playlist";
        btn.disabled = false;
        btn.classList.remove("activated");
    }
}

document.getElementById("skip-btn").addEventListener("click", () => wsSend({ action: "skip" }));
document.getElementById("skpn-inc").addEventListener("click", () => wsSend({ action: "skipc", add: 1 }));
document.getElementById("skpn-dec").addEventListener("click", () => wsSend({ action: "skipc", remove: -1 }));

document.getElementById("jingle-btn").addEventListener("click", () => wsSend({ action: "jingle" }));
document.getElementById("jingle-btn").addEventListener("contextmenu", e => {
    e.preventDefault();
    wsSend({ action: "jingle", top: true });
});

document.getElementById("skipidx-btn").addEventListener("click", () => {
    if (selectedPlaylistIndex == null) return;
    const action = skippedIndices.includes(selectedPlaylistIndex)
        ? { action: "skipi", remove: selectedPlaylistIndex }
        : { action: "skipi", add: selectedPlaylistIndex };
    wsSend(action);
});

document.getElementById("queue-title").addEventListener("click", () => toggleSection("section-queue"));
document.getElementById("clear-btn").addEventListener("click", e => {
    e.stopPropagation();
    wsSend({ action: "clear_toplay" });
});

document.getElementById("add-to-queue-btn").addEventListener("click", () => addSelectedFileToQueue(false));
document.getElementById("add-to-queue2-btn").addEventListener("click", () => addSelectedFileToQueue(true));

document.addEventListener("keydown", e => {
    if (e.target.tagName === "INPUT") return;
    if (e.key === "Enter" && addSelectedFileToQueue(e.shiftKey)) e.preventDefault();
    else if (e.key === "s") wsSend({ action: "skip" });
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
setTimeout(connectWs, 100);
requestAnimationFrame(animateProgress);
setTimeout(() => {
    document.getElementById("prog-fill").classList.remove("init")
}, 1000)