import multiprocessing, os
from queue import Empty
import json
import threading, uuid, time
import asyncio
import websockets
from websockets import ServerConnection, Request, Response, Headers

from . import Track, PlayerModule, Path

MAIN_PATH_DIR = Path("/home/user/mixes")

async def ws_handler(websocket: ServerConnection, shared_data: dict, imc_q: multiprocessing.Queue):
    try:
        initial = {
            "playlist": json.loads(shared_data.get("playlist", "[]")),
            "track": json.loads(shared_data.get("track", "{}")),
            "progress": json.loads(shared_data.get("progress", "{}")),
            "dirs": {"files": [i.name for i in list(MAIN_PATH_DIR.iterdir()) if i.is_file()], "dirs": [i.name for i in list(MAIN_PATH_DIR.iterdir()) if i.is_dir()], "base": str(MAIN_PATH_DIR)}
        }
    except Exception: initial = {"playlist": [], "track": {}, "progress": {}}
    await websocket.send(json.dumps({"event": "state", "data": initial}))

    async for raw in websocket:
        try: msg: dict = json.loads(raw)
        except Exception:
            await websocket.send(json.dumps({"error": "invalid json"}))
            continue

        action = msg.get("action")
        if action == "skip":
            imc_q.put({"name": "procman", "data": {"op": 2}})
            await websocket.send(json.dumps({"status": "ok", "action": "skip_requested"}))
        elif action == "add_to_toplay":
            songs = msg.get("songs")
            if not isinstance(songs, list): await websocket.send(json.dumps({"error": "songs must be a list"}))
            else:
                imc_q.put({"name": "activemod", "data": {"action": "add_to_toplay", "songs": songs}})
                await websocket.send(json.dumps({"status": "ok", "message": f"{len(songs)} song(s) queued"}))
        elif action == "get_toplay":
            # replicate the previous behavior: send request to activemod and wait for keyed response
            key = str(uuid.uuid4())
            imc_q.put({"name": "activemod", "data": {"action": "get_toplay"}, "key": key})
            # wait up to 2 seconds for shared_data[key] to appear
            start = time.monotonic()
            result = None
            while time.monotonic() - start < 2:
                if key in shared_data:
                    result = shared_data.pop(key)
                    break
                await asyncio.sleep(0.05)
            if result is None: await websocket.send(json.dumps({"error": "timeout", "code": 504}))
            else: await websocket.send(json.dumps({"status": "ok", "response": result, "event": "toplay"}))
        elif action == "request_state":
            # supports requesting specific parts if provided
            what = msg.get("what", "")
            try:
                if what == "playlist": payload = json.loads(shared_data.get("playlist", "[]"))
                elif what == "track": payload = json.loads(shared_data.get("track", "{}"))
                elif what == "progress": payload = json.loads(shared_data.get("progress", "{}"))
                elif what == "dirs": payload = {"files": [i.name for i in list(MAIN_PATH_DIR.iterdir()) if i.is_file()], "dirs": [i.name for i in list(MAIN_PATH_DIR.iterdir()) if i.is_dir()], "base": str(MAIN_PATH_DIR)}
                else:
                    payload = {
                        "playlist": json.loads(shared_data.get("playlist", "[]")),
                        "track": json.loads(shared_data.get("track", "{}")),
                        "progress": json.loads(shared_data.get("progress", "{}")),
                        "dirs": {"files": [i.name for i in list(MAIN_PATH_DIR.iterdir()) if i.is_file()], "dirs": [i.name for i in list(MAIN_PATH_DIR.iterdir()) if i.is_dir()], "base": str(MAIN_PATH_DIR)}
                    }
            except Exception: payload = {}
            await websocket.send(json.dumps({"event": "state", "data": payload}))
        elif action == "request_dir":
            what: str = msg.get("what", "")
            try:
                dir = Path(MAIN_PATH_DIR, what).resolve()
                payload = {"files": [i.name for i in list(dir.iterdir()) if i.is_file()], "base": str(dir), "dir": dir.name}
            except Exception: payload = {}
            await websocket.send(json.dumps({"event": "request_dir", "data": payload}))
        else: await websocket.send(json.dumps({"error": "unknown action"}))

async def broadcast_worker(ws_q: multiprocessing.Queue, clients: set):
    """
    Reads messages from ws_q (a blocking multiprocessing.Queue) using run_in_executor
    and broadcasts them to all connected clients.
    """
    loop = asyncio.get_event_loop()
    while True:
        try: msg = await asyncio.wait_for(loop.run_in_executor(None, ws_q.get), 1.0)
        except asyncio.TimeoutError: continue
        if msg is None: break
        payload = json.dumps(msg)
        if clients:
            await asyncio.gather(
                *[_safe_send(ws, payload, clients) for ws in list(clients)],
                return_exceptions=True
            )


async def _safe_send(ws, payload: str, clients: set):
    try: await ws.send(payload)
    except Exception:
        try: clients.discard(ws)
        except Exception: pass

def websocket_server_process(shared_data: dict, imc_q: multiprocessing.Queue, ws_q: multiprocessing.Queue):
    """
    Entrypoint for the separate process that runs the asyncio-based websocket server.
    """
    # create the asyncio loop and run server
    async def runner():
        clients = set()

        async def handler_wrapper(websocket: ServerConnection):
            # register client
            clients.add(websocket)
            try: await ws_handler(websocket, shared_data, imc_q)
            finally:
                await websocket.close(1001, "")
                clients.discard(websocket)
        async def process_request(websocket: ServerConnection, request: Request):
            if request.path == "/web.html" and (file := Path(__file__, "..", "web.html").resolve()).exists():
                data = file.read_bytes()
                return Response(
                    200,
                    "OK",
                    Headers([("Content-Type", "text/html"), ("Content-Length", f"{len(data)}")]),
                    data
                )
            if not "upgrade" in request.headers.get("Connection", "").lower():
                return Response(
                    426,
                    "Upgrade Required",
                    Headers([("Connection", "Upgrade"), ("Upgrade", "websocket")]),
                    b"WebSocket upgrade required\n"
                )

        server = await websockets.serve(handler_wrapper, "0.0.0.0", 3001, server_header="RadioPlayer ws plugin", process_request=process_request)
        broadcaster = asyncio.create_task(broadcast_worker(ws_q, clients))
        await broadcaster
        await server.wait_closed()

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try: loop.run_until_complete(runner())
    except (KeyboardInterrupt, SystemExit): pass
    finally: loop.close()

class Module(PlayerModule):
    def __init__(self):
        self.manager = multiprocessing.Manager()
        self.data = self.manager.dict()
        self.imc_q = multiprocessing.Queue()
        self.ws_q = multiprocessing.Queue()

        self.data["playlist"] = "[]"
        self.data["track"] = "{}"
        self.data["progress"] = "{}"

        self.ipc_thread_running = True
        self.ipc_thread = threading.Thread(target=self._ipc_worker, daemon=True)
        self.ipc_thread.start()

        self.ws_process = multiprocessing.Process(target=websocket_server_process, args=(self.data, self.imc_q, self.ws_q), daemon=False)
        self.ws_process.start()
        if os.name == "posix":
            try: os.setpgid(self.ws_process.pid, self.ws_process.pid)
            except Exception: pass

    def _ipc_worker(self):
        """
        Listens for messages placed in imc_q by websocket process or other modules,
        forwards them to the main IPC layer and stores keyed responses into shared dict.
        """
        while self.ipc_thread_running:
            try:
                message: dict | None = self.imc_q.get(timeout=0.5)
                if message is None: break
                out = self._imc.send(self, message["name"], message["data"])
                if key := message.get("key", None): self.data[key] = out
            except Empty: continue
            except Exception: pass

    def on_new_playlist(self, playlist: list[Track], global_args: dict[str, str]) -> None:
        # TODO: add global args to data
        api_data = []
        for track in playlist:
            api_data.append({
                "path": str(track.path),
                "fade_out": track.fade_out,
                "fade_in": track.fade_in,
                "official": track.official,
                "args": track.args,
                "offset": track.offset,
                "focus_time_offset": track.focus_time_offset
            })
        self.data["playlist"] = json.dumps(api_data)
        try: self.ws_q.put({"event": "playlist", "data": api_data})
        except Exception: pass

    def on_new_track(self, index: int, track: Track, next_track: Track | None) -> None:
        track_data = {"path": str(track.path), "fade_out": track.fade_out, "fade_in": track.fade_in, "official": track.official, "args": track.args, "offset": track.offset, "focus_time_offset": track.focus_time_offset}
        if next_track: next_track_data = {"path": str(next_track.path), "fade_out": next_track.fade_out, "fade_in": next_track.fade_in, "official": next_track.official, "args": next_track.args, "offset": next_track.offset, "focus_time_offset": track.focus_time_offset}
        else: next_track_data = None
        payload = {"index": index, "track": track_data, "next_track": next_track_data}
        self.data["track"] = json.dumps(payload)
        try: self.ws_q.put({"event": "new_track", "data": payload})
        except Exception: pass

    def progress(self, index: int, track: Track, elapsed: float, total: float, real_total: float) -> None:
        track_data = {"path": str(track.path), "fade_out": track.fade_out, "fade_in": track.fade_in, "official": track.official, "args": track.args, "offset": track.offset, "focus_time_offset": track.focus_time_offset}
        payload = {"index": index, "track": track_data, "elapsed": elapsed, "total": total, "real_total": real_total}
        self.data["progress"] = json.dumps(payload)
        try: self.ws_q.put({"event": "progress", "data": payload})
        except Exception: pass

    def shutdown(self):
        self.ipc_thread_running = False

        try: self.imc_q.put(None, block=False)
        except: pass

        try: self.ws_q.put(None, block=False)
        except: pass

        self.ipc_thread.join(timeout=2)
        self.ws_process.join(timeout=5)

        if self.ws_process.is_alive():
            self.ws_process.terminate()
            self.ws_process.join(timeout=2)

        if self.ws_process.is_alive():
            self.ws_process.kill()
            self.ws_process.join(timeout=1)

module = Module()
