let ws = null;
let reconnectDelay = 1000;
let playlist = [];
let Queue = [];
let currentTrackPath = "";
let currentTrackIndex = 0;
let selectedPlaylistIndex = null;
let selectedDir = null;
let selectedSubFile = null;
let basePath = "";
let subbasePath = "";
let skipCount = 0;
let indexDigits = 1;
let skipped_idx = [];

function toggleSection(id) {
    document.getElementById(id).classList.toggle('collapsed');
}

function initLayout() {
    if (window.innerWidth <= 800) {
        document.getElementById('section-playlist').classList.add('collapsed');
        document.getElementById('section-dirs').classList.add('collapsed');
        document.getElementById('section-subdir').classList.add('collapsed');
    }
    if(window.location.protocol === "file:") document.getElementById("whep-url-input").value = "https://webrtc.terminal.tnet/radio/whep"
}

function connectWs() {
    const statusText = document.getElementById("server-status");
    statusText.textContent = "connecting...";

    let url = "/ws";
    if(window.location.protocol === "file:") url = "https://radio95.tnet/ws"
    ws = new WebSocket(url);

    ws.addEventListener("open", () => {
        statusText.textContent = "connected";
        reconnectDelay = 1500;
        ws.send(JSON.stringify({action:"get_toplay"}));
        ws.send(JSON.stringify({action:"skipc"}));
        ws.send(JSON.stringify({action:"skipi"}));
    });

    ws.addEventListener("close", () => {
        statusText.textContent = "disconnected — reconnecting...";
        setTimeout(connectWs, reconnectDelay);
        reconnectDelay = Math.min(10000, reconnectDelay + 1500);
    });

    ws.addEventListener("error", (e) => {
        console.error("WS error", e);
        statusText.textContent = "error";
    });

    ws.addEventListener("message", (evt) => {
        try { handleMessage(JSON.parse(evt.data)); }
        catch (e) { console.warn("Bad msg", evt.data, e); }
    });
}

function handleMessage(msg){
    if(msg.event === "state"){
        const d = msg.data || {};
        if(d.dirs) updateDirs(d.dirs);
        if(d.track) applyProgressState(d.track);
    } else if (msg.event === "rds") {
        const rt = (msg.data?.rt) ?? "";
        document.getElementById("rds-text").textContent = rt ?? "";
    } else if(msg.event === "playlist") {
        playlist = msg.data || [];
        renderPlaylist();
    } else if(msg.event === "new_track"){
        applyTrackState(msg.data);
        ws.send(JSON.stringify({action:"get_toplay"}));
        ws.send(JSON.stringify({action:"skipc"}));
        ws.send(JSON.stringify({action:"skipi"}));
    } else if(msg.event === "progress") applyProgressState(msg.data);
    else if(msg.event === "toplay") {
        Queue = msg.data.data || [];
        renderQueue();
    } else if(msg.event === "request_dir") applySubdir(msg.data || {})
    else if(msg.event === "skipc") {
        skipCount = msg.data?.data ?? 0;
        document.getElementById("skpn-count").textContent = skipCount;
        renderPlaylist();
        renderQueue();
    } else if(msg.event === "skipi") {
        skipped_idx = msg.data?.data ?? skipped_idx;
        renderPlaylist();
    }
}

function applyTrackState(payload) {
    const track = payload.track || {};
    const next = payload.next_track || {};
    currentTrackPath = track.path;
    currentTrackIndex = payload.index;
    document.getElementById("now-track").textContent = `${String(currentTrackIndex).padStart(indexDigits,'0')}: ` + (track.official ? "(official) " : "(unofficial) ") + track.path.replace(basePath, "").slice(1);;
    document.getElementById("next-track").textContent = (next.official ? "(official) " : "(unofficial) ") + next.path.replace(basePath, "").slice(1);
    renderPlaylist();
}

function applyProgressState(payload) {
    const track = payload.track || {};
    const next_track = payload.next_track || {};
    const elapsed = Number(payload.elapsed || 0);
    const total = Number(payload.total || payload.real_total || 1) || 1;
    const realtotal = Number(payload.real_total || payload.total || 1) || 1;
    const percent = Math.max(0, Math.min(100, (elapsed/realtotal)*100));
    document.getElementById("prog-fill").style.width = percent + "%";
    document.getElementById("time-label").textContent = formatTime(elapsed) + " / " + formatTime(total) + ` (${formatTime(total-elapsed)})`;
    currentTrackIndex = payload.index;
    if(track.path){
        currentTrackPath = track.path;
        document.getElementById("now-track").textContent = `${String(currentTrackIndex).padStart(indexDigits,'0')}: ` + (track.official ? "(official) " : "(unofficial) ") + track.path.replace(basePath, "").slice(1);
    } if(next_track.path) document.getElementById("next-track").textContent = `${next_track.official ? "(official)" : "(unofficial)"} ${next_track.path.replace(basePath, "").slice(1)}`;
}

function applySubdir(payload) {
    if(payload.dir !== selectedDir) return;
    const dirsBox = document.getElementById("subdir-box");
    dirsBox.innerHTML = "Loading...";
    try {
        subbasePath = payload.base || "";
        const files = payload.files || [];
        dirsBox.innerHTML = "";
        files.sort().forEach(f => {
            const node = document.createElement("div");
            node.className = "item";
            node.textContent = f;
            node.addEventListener("click", () => {
                if(node.classList.contains("selected")) { node.classList.remove("selected"); selectedSubFile = null; return; }
                Array.from(dirsBox.children).forEach(c=>c.classList.remove("selected"));
                Array.from(document.getElementById("playlist-ul").children).forEach(c => c.classList.remove("selected"));
                node.classList.add("selected"); selectedSubFile = f;
            });
            dirsBox.appendChild(node);
        });
    } catch(e) { dirsBox.innerHTML = "Error fetching dirs: "+e.message; }
}

function formatTime(s){
    s = Number(s||0);
    const h = Math.floor(s/3600), m = Math.floor((s%3600)/60), sec = Math.floor(s%60);
    if(h != 0) return [h,m,sec].map(x => String(x).padStart(2,'0')).join(":");
    else return [m,sec].map(x => String(x).padStart(2,'0')).join(":");
}

function renderPlaylist() {
    const ul = document.getElementById("playlist-ul");
    ul.innerHTML = "";
    let currentIndex = null;
    indexDigits = playlist.length.toString().length
    playlist.forEach((t, i) => {
        const li = document.createElement("li");
        const path = t.path || "<no path>";
        const official = t.official || false;
        const displayPath = (official ? "(official) " : "(unofficial) ") + path.replace(basePath, "").slice(1);
        li.dataset.path = path;
        li.dataset.idx = i;
        li.addEventListener("click", () => { selectPlaylistItem(i, li); });
        if (path === currentTrackPath && i === currentTrackIndex) { li.classList.add("current"); currentIndex = i; }
        else if (i === currentTrackIndex) { li.classList.add("pointer"); currentIndex = i - 1; }
        if(currentIndex !== null && Queue.length === 0 && i > currentIndex && i <= currentIndex + skipCount) li.style.textDecoration = "line-through";
        li.textContent = ` ${String(i).padStart(indexDigits,'0')}: `;
        li.textContent = (i === currentTrackIndex ? "▶ " : "  ") + li.textContent + displayPath;
        ul.appendChild(li);
        if(skipped_idx.includes(i)) li.style.textDecoration = "line-through";
    });
    if(currentIndex !== null){
        const el = ul.children[currentIndex];
        if(el) el.scrollIntoView({block:'center', behavior: 'smooth'});
    } updateControls();
}

function renderQueue() {
    const ul = document.getElementById("queue-ul");
    ul.innerHTML = "";
    Queue.forEach((element, i) => {
        const li = document.createElement("li");
        li.textContent = element.replace(basePath, "").slice(1);
        if(i < skipCount) li.style.textDecoration = "line-through";
        ul.appendChild(li);
    });
    updateControls()
}

function selectPlaylistItem(i, el){
    if(el.classList.contains("selected")) { el.classList.remove("selected"); selectedPlaylistIndex = null; return; }
    const ul = document.getElementById("playlist-ul");
    Array.from(ul.children).forEach(c => c.classList.remove("selected"));
    Array.from(document.getElementById("dirs-box").children).forEach(c => c.classList.remove("selected"));
    Array.from(document.getElementById("subdir-box").children).forEach(c => c.classList.remove("selected"));
    el.classList.add("selected");
    selectedPlaylistIndex = i;
    updateControls()
}

async function updateDirs(payload){
    const dirsBox = document.getElementById("dirs-box");
    dirsBox.innerHTML = "Loading...";
    try {
        basePath = payload.base || "";
        const files = payload.files || [];
        const dirs = payload.dirs || [];
        dirsBox.innerHTML = "";
        dirs.sort().forEach(f => {
            if(!f.startsWith(".")) {
                const node = document.createElement("div");
                node.className = "item";
                node.textContent = f;
                node.addEventListener("click", () => onDirClicked(f, node));
                dirsBox.appendChild(node);
            }
        });
        files.sort().forEach(f => {
            if(!f.startsWith(".")) {
                const node = document.createElement("div");
                node.className = "item";
                node.textContent = f;
                node.addEventListener("click", () => {
                    if(node.classList.contains("selected")) { node.classList.remove("selected"); selectedDir = null; selectedSubFile = null; return; }
                    Array.from(dirsBox.children).forEach(c=>c.classList.remove("selected"));
                    Array.from(document.getElementById("playlist-ul").children).forEach(c => c.classList.remove("selected"));
                    Array.from(document.getElementById("subdir-box").children).forEach(c => c.classList.remove("selected"));
                    node.classList.add("selected");
                    selectedDir = null; selectedSubFile = null;
                    document.getElementById("subdir-box").innerHTML = "";
                });
                node.dataset.type = "file";
                dirsBox.appendChild(node);
            }
        });
    } catch(e) { dirsBox.innerHTML = "Error fetching dirs: "+e.message; }
}

function onDirClicked(name, node){
    if(node.classList.contains("selected")) {
        node.classList.remove("selected"); selectedDir = null; selectedSubFile = null;
        document.getElementById("subdir-box").innerHTML = ""; return;
    }
    Array.from(document.getElementById("dirs-box").children).forEach(c => c.classList.remove("selected"));
    Array.from(document.getElementById("playlist-ul").children).forEach(c => c.classList.remove("selected"));
    node.classList.add("selected");
    selectedDir = name; selectedSubFile = null;
    ws.send(JSON.stringify({action:"request_dir", what: selectedDir}))
}

document.getElementById("skip-btn").addEventListener("click", () => ws.send(JSON.stringify({action:"skip"})));
document.getElementById("skpn-inc").addEventListener("click", () => ws.send(JSON.stringify({action:"skipc", add: 1})));
document.getElementById("skpn-dec").addEventListener("click", () => ws.send(JSON.stringify({action:"skipc", remove: -1})));
document.getElementById("jingle-btn").addEventListener("click", () => ws.send(JSON.stringify({action:"jingle"})));
document.getElementById("jingle-btn").addEventListener("contextmenu", (e) => {
    e.preventDefault();
    ws.send(JSON.stringify({action:"jingle", top: true}));
});
document.getElementById("clear-btn").addEventListener("click", () => ws.send(JSON.stringify({action:"clear_toplay"})));

document.getElementById("skipidx-btn").addEventListener("click", () => {
    if (selectedPlaylistIndex == null) return;
    const action = skipped_idx.includes(selectedPlaylistIndex)
        ? { action: "skipi", remove: selectedPlaylistIndex }
        : { action: "skipi", add: selectedPlaylistIndex };
    ws.send(JSON.stringify(action));
});

function addSelectedFileToQueue(top) {
    let fullPath = null;
    let success = false;
    if (selectedPlaylistIndex != null) {
        const selected = playlist[selectedPlaylistIndex];
        const path = (selected.official ? "" : "!") + selected.path;
        ws.send(JSON.stringify({ action: "add_to_toplay", songs: [path], top: top }));
        success = true;
    } else if (selectedSubFile && selectedDir) fullPath = subbasePath.replace(/\/$/, '') + '/' + selectedSubFile;
    else {
        const dirEls = document.getElementById("dirs-box").children;
        const selectedItem = Array.from(dirEls).find(el => el.classList.contains("selected"));
        if (selectedItem && selectedItem.dataset.type === "file") fullPath = basePath.replace(/\/$/, '') + '/' + selectedItem.textContent;
    }
    if (fullPath) { ws.send(JSON.stringify({ action: "add_to_toplay", songs: [fullPath], top: top })); success = true; }
    Array.from(document.getElementById("playlist-ul").children).forEach(c => c.classList.remove("selected"));
    Array.from(document.getElementById("dirs-box").children).forEach(c => c.classList.remove("selected"));
    Array.from(document.getElementById("subdir-box").children).forEach(c => c.classList.remove("selected"));
    selectedPlaylistIndex = null; selectedSubFile = null;
    return success;
}

document.getElementById("add-to-queue-btn").addEventListener("click", () => addSelectedFileToQueue(false));
document.getElementById("add-to-queue2-btn").addEventListener("click", () => addSelectedFileToQueue(true));

function updateControls() {
    document.getElementById("clear-btn").disabled = Queue.length === 0;

    const btn = document.getElementById("skipidx-btn");
    if (selectedPlaylistIndex == null) {
        btn.textContent = "⏭+ Skip idx";
        btn.disabled = true;
        btn.classList.remove("activated");
    } else if (skipped_idx.includes(selectedPlaylistIndex)) {
        btn.textContent = "✓ Unskip idx";
        btn.disabled = false;
        btn.classList.add("activated");
    } else {
        btn.textContent = "⏭+ Skip idx";
        btn.disabled = false;
        btn.classList.remove("activated");
    }
}

document.addEventListener("keydown", e => {
    if (e.target.tagName === "INPUT") return;
    if (e.key === "Enter" && addSelectedFileToQueue(e.shiftKey)) e.preventDefault();
    else if (e.key === "s") ws.send(JSON.stringify({action:"skip"}));
    else if (e.key === "n") ws.send(JSON.stringify({action:"skipc", add: 1}));
    else if (e.key === "m") ws.send(JSON.stringify({action:"skipc", remove: -1}));
    else if (e.key.toLowerCase() === "j") ws.send(JSON.stringify({action:"jingle", top: e.shiftKey}));
});

let whepReader = null;
let whepAudio = null;
let whepConnected = false;

function whepLog(msg, type = 'info') {
    const el = document.getElementById('whep-log');
    const line = document.createElement('div');
    line.className = 'wlog-' + type;
    const ts = new Date().toLocaleTimeString("pl-PL");
    line.textContent = `[${ts}] ${msg}`;
    el.appendChild(line);
    el.scrollTop = el.scrollHeight;
    // Keep log short
    while (el.children.length > 30) el.removeChild(el.firstChild);
}

function whepSetDot(state) {
    const dot = document.getElementById('whep-dot');
    dot.className = 'whep-status-dot' + (state !== 'idle' ? ' ' + state : '');
    const btn = document.getElementById('whep-btn');
    if (state === 'connected' || state === 'connecting') {
        btn.textContent = '⏹ Disconnect';
        btn.classList.add('activated');
    } else {
        btn.textContent = '▶ Connect';
        btn.classList.remove('activated');
    }
}

function whepSetVol(v) {
    document.getElementById('whep-vol-out').textContent = (Math.round(v * 1000) / 10).toFixed(1) + '%';
    if (whepAudio) whepAudio.volume = parseFloat(v);
}

function whepToggle() {
    if (whepConnected) { whepDisconnect(); return; }
    whepConnect();
}

function whepDisconnect() {
    whepConnected = false;

    if (whepReader) {
        try { whepReader.stop(); } catch(e){}
        whepReader = null;
    }

    if (whepAudio) {
        whepAudio.pause();
        whepAudio.srcObject = null;
        whepAudio = null;
    }

    whepSetDot('idle');
    whepLog('Disconnected');
}

async function whepConnect() {
    const url = document.getElementById('whep-url-input').value.trim();
    if (!url) return;

    whepSetDot('connecting');
    whepLog('Starting MediaMTX reader…');

    try {
        whepReader = new MediaMTXWebRTCReader({
            url: url,

            onTrack: (evt) => {
                if(evt.track.kind !== "audio") return;
                whepLog('Track received, starting playback', 'ok');

                whepAudio = new Audio();
                whepAudio.srcObject = evt.streams[0];
                whepAudio.volume = parseFloat(document.getElementById('whep-vol').value);

                whepAudio.play().then(() => {
                    whepLog('Audio playing', 'ok');
                    whepConnected = true;
                    whepSetDot('connected');
                }).catch(() => {
                    whepLog('Autoplay blocked — click anywhere', 'err');
                    document.addEventListener('click', () => whepAudio?.play(), { once: true });
                });
            },

            onError: (err) => {
                whepLog('Error: ' + err, 'err');
                whepDisconnect();
                whepSetDot('error');
            },

            onStateChange: (state) => {
                whepLog('State: ' + state);
                if (state === 'closed') whepDisconnect();
            }
        });

        whepLog('Reader started, waiting for media…');

    } catch (err) {
        whepLog('Error: ' + err.message, 'err');
        whepDisconnect();
        whepSetDot('error');
    }
}

// Start
initLayout();
setTimeout(connectWs, 100);