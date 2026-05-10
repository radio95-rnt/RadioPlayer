import multiprocessing, os
from queue import Empty
import json
import threading, uuid, time
import asyncio
import websockets, base64
from websockets import ServerConnection, Request, Response, Headers
import mimetypes
import shutil

def get_content_type(filename: str) -> str:
    mime_type, _ = mimetypes.guess_type(filename, False)
    if mime_type: return mime_type
    return "application/octet-stream"

from modules import InterModuleCommunication

from . import Track, PlayerModule, Path, BaseIMCModule

MAIN_PATH_DIR = Path("/home/user/mixes")

# locks: dict[lock_id, websocket | None]  — managed inside the async runner's scope
# passed into handlers via a shared dict reference

async def ws_handler(websocket: ServerConnection, shared_data: dict, imc_q: multiprocessing.Queue, writer_q: asyncio.Queue, locks: dict, clients: set):
    try:
        initial = {
            "track": json.loads(shared_data.get("track", "{}")),
            "dirs": {"files": [i.name for i in list(MAIN_PATH_DIR.iterdir()) if i.is_file()], "dirs": [i.name for i in list(MAIN_PATH_DIR.iterdir()) if i.is_dir()], "base": str(MAIN_PATH_DIR)},
            "locks": {lid: True for lid, owner in locks.items() if owner is not None},
        }
    except Exception: initial = {"track": {}, "dirs": {}, "locks": {}}
    await websocket.send(json.dumps({"event": "state", "data": initial}))
    await websocket.send(json.dumps({"event": "playlist", "data": json.loads(shared_data.get("playlist", "[]"))}))
    await websocket.send(json.dumps({"event": "rds", "data": json.loads(shared_data.get("rds", "{}"))}))

    async def get_imc(name, data):
        key = str(uuid.uuid4())
        imc_q.put({"name": name, "data": data, "key": key})
        start = time.monotonic()
        while time.monotonic() - start < 1:
            if key in shared_data: return shared_data.pop(key)
            await asyncio.sleep(0.1)
        return None

    async def broadcast(payload: dict):
        msg = json.dumps(payload)
        for ws in list(clients):
            try: await ws.send(msg)
            except Exception: pass

    try:
        async for raw in websocket:
            try: msg: dict = json.loads(raw)
            except Exception:
                await websocket.send(json.dumps({"error": "invalid json"}))
                continue

            action = msg.get("action")
            if action == "skip":
                imc_q.put({"name": "procman", "data": {"op": 2}})
                await websocket.send(json.dumps({"event": "skip"}))
            elif action == "add_to_toplay":
                songs = msg.get("songs")
                at_top = msg.get("top", False)
                if not isinstance(songs, list): await websocket.send(json.dumps({"error": "songs must be a list"}))
                else:
                    imc_q.put({"name": "activemod", "data": {"action": "add_to_toplay", "songs": songs, "top": at_top}})
                    result = await get_imc("activemod", {"action": "get_toplay"})
                    if result is not None:
                        await broadcast({"data": result, "event": "toplay"})
            elif action == "get_toplay":
                result = await get_imc("activemod", {"action": "get_toplay"})
                if result is None: await websocket.send(json.dumps({"error": "timeout", "code": 504}))
                else: await websocket.send(json.dumps({"data": result, "event": "toplay"}))
            elif action == "clear_toplay":
                result = await get_imc("activemod", {"action": "clear_toplay"})
                if result is None: await websocket.send(json.dumps({"error": "timeout", "code": 504}))
                else:
                    await broadcast({"data": result, "event": "toplay"})
            elif action == "skipc" or action == "skipi":
                result = await get_imc("activemod", msg)
                if result is None: await websocket.send(json.dumps({"error": "timeout", "code": 504}))
                else:
                    await broadcast({"data": result, "event": action})
            elif action == "jingle":
                result = await get_imc("jingle", msg.get("top", False))
                if result is None: await websocket.send(json.dumps({"error": "timeout", "code": 504}))
                else:
                    await websocket.send(json.dumps(result))
                    result = await get_imc("activemod", {"action": "get_toplay"})
                    if result is not None:
                        await broadcast({"data": result, "event": "toplay"})
            elif action == "request_dir":
                what: str = msg.get("what", "")
                try:
                    dir = Path(MAIN_PATH_DIR, what).resolve()
                    payload = {"files": [i.name for i in list(dir.iterdir()) if i.is_file()], "base": str(dir), "dir": dir.name}
                except Exception: payload = {}
                await websocket.send(json.dumps({"event": "request_dir", "data": payload}))
            elif action == "fsdb_add":
                name: str | None = msg.get("name")
                try:
                    if not name: raise Exception("name not defined")
                    path = Path(MAIN_PATH_DIR, ".playlist", msg.get("playlist", ""), name)
                    path.touch(exist_ok=True)
                    await websocket.send(json.dumps({"event": "fsdb_add", "ok": True}))
                except Exception as e: await websocket.send(json.dumps({"event": "fsdb_add", "error": str(e)}))
            elif action == "fsdb_add_dir":
                name: str | None = msg.get("name")
                try:
                    if not name: raise Exception("name not defined")
                    path = Path(MAIN_PATH_DIR, ".playlist", msg.get("playlist", ""), name)
                    path.mkdir(parents=True, exist_ok=True)
                    await websocket.send(json.dumps({"event": "fsdb_add_dir", "ok_dir": True}))
                except Exception as e: await websocket.send(json.dumps({"event": "fsdb_add_dir", "error": str(e)}))
            elif action == "fsdb_remove":
                name: str | None = msg.get("name")
                try:
                    if not name: raise Exception("name not defined")
                    path = Path(MAIN_PATH_DIR, ".playlist", msg.get("playlist", ""), name)
                    if path.is_dir(): shutil.rmtree(path)
                    else: path.unlink(missing_ok=True)
                    await websocket.send(json.dumps({"event": "fsdb_remove", "ok": True}))
                except Exception as e: await websocket.send(json.dumps({"event": "fsdb_remove", "error": str(e)}))
            elif action == "fsdb_list":
                try:
                    p = Path(MAIN_PATH_DIR, ".playlist", msg.get("playlist", ""))
                    payload = {
                        "files": [i.name for i in p.iterdir() if i.is_file()],
                        "dirs": [i.name for i in p.iterdir() if i.is_dir()]
                    }
                    await websocket.send(json.dumps({"event": "fsdb_list", "data": payload}))
                except Exception as e: await websocket.send(json.dumps({"event": "fsdb_list", "data": {}, "error": str(e)}))
            elif action == "fm95": await writer_q.put((base64.b64decode(msg.get("data", "")), websocket))
            elif action == "lock":
                lid = msg.get("id")
                if lid is None: await websocket.send(json.dumps({"event": "error", "error": "lock id required"}))
                elif locks.get(lid) not in (None, websocket):
                    # already held by someone else
                    await websocket.send(json.dumps({"event": "lock", "id": lid, "data": True, "error": "already locked"}))
                else:
                    locks[lid] = websocket
                    await broadcast({"event": "lock", "id": lid, "data": True})

            elif action == "unlock":
                lid = msg.get("id")
                if lid is None:
                    await websocket.send(json.dumps({"event": "error", "error": "lock id required"}))
                elif locks.get(lid) is not websocket:
                    # not the owner
                    await websocket.send(json.dumps({"event": "error", "error": "not lock owner"}))
                else:
                    locks[lid] = None
                    await broadcast({"event": "lock", "id": lid, "data": False})

            else: await websocket.send(json.dumps({"event": "error", "error": "unknown action"}))
    finally:
        # release every lock this client held on disconnect
        for lid, owner in list(locks.items()):
            if owner is websocket:
                locks[lid] = None
                await broadcast({"event": "lock", "id": lid, "data": False})


async def broadcast_worker(ws_q: multiprocessing.Queue, clients: set):
    loop = asyncio.get_event_loop()
    while True:
        msg: dict = await loop.run_in_executor(None, ws_q.get)
        if msg is None: break
        payload = json.dumps(msg)
        if clients:
            coros = []
            for ws in list(clients): coros.append(_safe_send(ws, payload, clients, ws_q))
            await asyncio.gather(*coros)

async def _safe_send(ws, payload: str, clients: set, ws_q: multiprocessing.Queue):
    try: await ws.send(payload)
    except Exception:
        try: 
            clients.discard(ws)
            await asyncio.get_event_loop().run_in_executor(None, ws_q.put, {"event": "users", "data": len(clients)})
        except Exception: pass

async def socket_handler(socket: asyncio.StreamReader, writer: asyncio.StreamWriter, writer_q: asyncio.Queue):
    while True:
        qdata, ws = await writer_q.get()
        if not qdata or not ws: break
        try:
            writer.write(qdata)
            await writer.drain()
            data = await socket.read(256)
            if not data:
                await ws.send(json.dumps({"event": "error", "error": "fm95 socket closed"}))
                raise ConnectionResetError("fm95 socket closed")  # ← let reconnect handle it
            await ws.send(json.dumps({"event": "fm95", "data": base64.b64encode(data).decode()}))
        except Exception as e:
            try: await ws.send(json.dumps({"event": "error", "error": str(e)}))
            except Exception: pass
            raise 

def websocket_server_process(shared_data: dict, imc_q: multiprocessing.Queue, ws_q: multiprocessing.Queue):
    async def runner():
        clients: set[ServerConnection] = set()
        locks: dict[int, ServerConnection | None] = {}  # lock_id -> owning websocket or None
        writer_q: asyncio.Queue[tuple[bytes | None, ServerConnection | None]] = asyncio.Queue()

        async def get_socket_connection(retry_delay=2.0):
            while True:
                try:
                    reader, writer = await asyncio.open_unix_connection("/etc/fm95/ctl.socket") # pyright: ignore[reportAttributeAccessIssue]
                    return reader, writer
                except Exception as e:
                    await asyncio.sleep(retry_delay)
        
        async def socket_handler_with_reconnect():
            while True:
                reader, writer = await get_socket_connection()
                try:
                    await socket_handler(reader, writer, writer_q)
                finally:
                    try:
                        writer.close()
                        await writer.wait_closed()
                    except Exception: pass

        async def handler_wrapper(websocket: ServerConnection):
            clients.add(websocket)
            await asyncio.get_event_loop().run_in_executor(None, ws_q.put, {"event": "users", "data": len(clients)})
            try: await ws_handler(websocket, shared_data, imc_q, writer_q, locks, clients)
            finally:
                await websocket.close(1001, "")
                clients.discard(websocket)
                await asyncio.get_event_loop().run_in_executor(None, ws_q.put, {"event": "users", "data": len(clients)})

        async def process_request(websocket: ServerConnection, request: Request):
            if request.path == "/ws":
                if not "upgrade" in request.headers.get("Connection", "").lower():
                    return Response(
                        426,
                        "Upgrade Required",
                        Headers([("Connection", "Upgrade"), ("Upgrade", "websocket")]),
                        b"WebSocket upgrade required\n"
                    )
                return None
            else:
                if request.path == "/" and (file := Path(__file__, "..", "web", "index.html").resolve()).exists():
                    data = file.read_bytes()
                    return Response(200, "OK", Headers([("Content-Type", "text/html; charset=utf-8"), ("Content-Length", f"{len(data)}")]), data)
                elif (file := Path(__file__, "..", "web", request.path.removeprefix("/").strip()).resolve()).exists():
                    data = file.read_bytes()
                    return Response(200, "OK", Headers([("Content-Type", get_content_type(file.name)), ("Content-Length", f"{len(data)}")]), data)
                else:
                    data = b"Not Found\n"
                    return Response(404, "Not Found", Headers([("Content-Length", f"{len(data)}")]), data)

        server = await websockets.serve(handler_wrapper, "0.0.0.0", 3001, server_header="RadioPlayer ws plugin", process_request=process_request)
        broadcaster = asyncio.create_task(broadcast_worker(ws_q, clients))
        sockethand = asyncio.create_task(socket_handler_with_reconnect())
        await broadcaster

        await writer_q.put((None, None))
        await sockethand
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
        self.data["rds"] = "{}"

        self.ipc_thread_running = True
        self.ipc_thread = threading.Thread(target=self._ipc_worker, daemon=True)
        self.ipc_thread.start()

        self.ws_process = multiprocessing.Process(target=websocket_server_process, args=(self.data, self.imc_q, self.ws_q), daemon=False)
        self.ws_process.start()
        if os.name == "posix":
            try: os.setpgid(self.ws_process.pid, self.ws_process.pid)
            except Exception: pass

    def _ipc_worker(self):
        while self.ipc_thread_running:
            try:
                message: dict | None = self.imc_q.get(timeout=0.5)
                if message is None: break
                out = self._imc.send(self, message["name"], message["data"])
                if key := message.get("key", None): self.data[key] = out
            except Empty: continue
            except Exception: pass

    def on_new_playlist(self, playlist: list[Track], global_args: dict[str, str]) -> None:
        api_data = []
        for track in playlist:
            api_data.append({"path": str(track.path), "fade_out": track.fade_out, "fade_in": track.fade_in, "official": track.official, "args": track.args, "offset": track.offset, "focus_time_offset": track.focus_time_offset})
        output_data = {"playlist": api_data, "global_args": global_args}
        self.data["playlist"] = json.dumps(output_data)
        try: self.ws_q.put({"event": "playlist", "data": output_data})
        except Exception: pass

    def on_new_track(self, index: int, track: Track, next_track: Track | None) -> None:
        track_data = {"path": str(track.path), "fade_out": track.fade_out, "fade_in": track.fade_in, "official": track.official, "args": track.args, "offset": track.offset, "focus_time_offset": track.focus_time_offset}
        if next_track: next_track_data = {"path": str(next_track.path), "fade_out": next_track.fade_out, "fade_in": next_track.fade_in, "official": next_track.official, "args": next_track.args, "offset": next_track.offset, "focus_time_offset": next_track.focus_time_offset}
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

    def imc_data(self, source: BaseIMCModule, source_name: str | None, data: object, broadcast: bool) -> object:
        wsdata = {"event": "imc", "data": {"name": source_name, "data": data, "broadcast": broadcast}}
        if source_name == "rds": 
            self.data[source_name] = json.dumps(data)
            wsdata = {"event": "rds", "data": data}
        try: self.ws_q.put(wsdata)
        except Exception: pass

    def imc(self, imc: InterModuleCommunication) -> None:
        self._imc = imc
        imc.register(self, "web")

    def shutdown(self):
        self.ipc_thread_running = False

        try: self.imc_q.put(None)
        except: pass

        try: self.ws_q.put(None)
        except: pass

        self.ipc_thread.join(timeout=1)
        self.ws_process.join(timeout=1)

        self.imc_q.close()
        self.ws_q.close()

        if self.ws_process.is_alive():
            self.ws_process.terminate()
            self.ws_process.join(timeout=1)

        if self.ws_process.is_alive():
            self.ws_process.kill()
            self.ws_process.join(timeout=1)

        self.imc_q.join_thread()
        self.ws_q.join_thread()

module = Module()

# This is free and unencumbered software released into the public domain.

# Anyone is free to copy, modify, publish, use, compile, sell, or
# distribute this software, either in source code form or as a compiled
# binary, for any purpose, commercial or non-commercial, and by any
# means.

# In jurisdictions that recognize copyright laws, the author or authors
# of this software dedicate any and all copyright interest in the
# software to the public domain. We make this dedication for the benefit
# of the public at large and to the detriment of our heirs and
# successors. We intend this dedication to be an overt act of
# relinquishment in perpetuity of all present and future rights to this
# software under copyright law.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
# IN NO EVENT SHALL THE AUTHORS BE LIABLE FOR ANY CLAIM, DAMAGES OR
# OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE,
# ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR
# OTHER DEALINGS IN THE SOFTWARE.

# For more information, please refer to <https://unlicense.org>