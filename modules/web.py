import multiprocessing
import json
import threading
from functools import partial
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn
from . import Track, PlayerModule

class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    """Handle requests in a separate thread."""

class APIHandler(BaseHTTPRequestHandler):
    def __init__(self, data, imc_q, *args, **kwargs):
        self.data = data
        self.imc_q = imc_q
        super().__init__(*args, **kwargs)

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()

        if self.path == "/api/playlist": rdata = json.loads(self.data.get("playlist", "[]"))
        elif self.path == "/api/track": rdata = json.loads(self.data.get("track", "{}"))
        else: rdata = {"error": "not found"}

        self.wfile.write(json.dumps(rdata).encode('utf-8'))

    def do_POST(self):
        response = {"error": "not found"}
        code = 404

        if self.path == "/api/skip":
            self.imc_q.put({"name": "procman", "data": {"op": 2}})
            response = {"status": "ok", "action": "skip requested"}
            code = 200
        elif self.path == "/api/put":
            try:                
                body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                
                songs = body.get("songs")
                if songs is None or not isinstance(songs, list): raise ValueError("Request body must be a JSON object with a 'songs' key containing a list of strings.")

                self.imc_q.put({"name": "activemod", "data": {"action": "add_to_toplay", "songs": songs}})
                
                response = {"status": "ok", "message": f"{len(songs)} song(s) were added to the high-priority queue."}
                code = 200
            except json.JSONDecodeError:
                response = {"error": "Invalid JSON in request body."}
                code = 400
            except (ValueError, KeyError, TypeError) as e:
                response = {"error": f"Invalid request format: {e}"}
                code = 400
            except Exception as e:
                response = {"error": f"An unexpected server error occurred: {e}"}
                code = 500

        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(response).encode('utf-8'))
    def send_response(self, code, message=None):
        self.send_response_only(code, message)
        self.send_header('Server', self.version_string())
        self.send_header('Date', self.date_time_string())

def web_server_process(data, imc_q):
    ThreadingHTTPServer(("0.0.0.0", 3001), partial(APIHandler, data, imc_q)).serve_forever()

class Module(PlayerModule):
    def __init__(self):
        self.manager = multiprocessing.Manager()
        self.data = self.manager.dict()
        self.imc_q = self.manager.Queue()

        self.data["playlist"] = "[]"
        self.data["track"] = "{}"

        self.ipc_thread_running = True
        self.ipc_thread = threading.Thread(target=self._ipc_worker, daemon=True)
        self.ipc_thread.start()

        self.web_process = multiprocessing.Process(target=web_server_process, args=(self.data, self.imc_q))
        self.web_process.start()

    def _ipc_worker(self):
        while self.ipc_thread_running:
            try:
                message = self.imc_q.get()
                if message is None: break
                self._imc.send(self, message["name"], message["data"])
            except Exception: pass

    def on_new_playlist(self, playlist: list[Track]) -> None:
        api_data = []
        for track in playlist:
            api_data.append({"path": str(track.path), "fade_out": track.fade_out, "fade_in": track.fade_in, "official": track.official, "args": track.args, "offset": track.offset})
        self.data["playlist"] = json.dumps(api_data)

    def on_new_track(self, index: int, track: Track, next_track: Track | None) -> None:
        track_data = {"path": str(track.path), "fade_out": track.fade_out, "fade_in": track.fade_in, "official": track.official, "args": track.args, "offset": track.offset}
        if next_track:
            next_track_data = {"path": str(next_track.path), "fade_out": next_track.fade_out, "fade_in": next_track.fade_in, "official": next_track.official, "args": next_track.args, "offset": next_track.offset}
        else: next_track_data = None
        self.data["track"] = json.dumps({"index": index, "track": track_data, "next_track": next_track_data})

    def shutdown(self):
        self.ipc_thread_running = False
        self.imc_q.put(None)
        self.ipc_thread.join(timeout=2)

        if self.web_process.is_alive():
            self.web_process.terminate()
            self.web_process.join(timeout=2)

        if self.web_process.is_alive(): self.web_process.kill()

module = Module()