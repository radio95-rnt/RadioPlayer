import multiprocessing, json

from . import PlayerModule, Track
from http.server import HTTPServer, BaseHTTPRequestHandler

manager = multiprocessing.Manager()
data = manager.dict()
data_lock = manager.Lock()
imc_q = manager.Queue()

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        global data
        if self.path == "/api/playlist":
            rdata = str(data["playlist"]).encode()
        elif self.path == "/api/track":
            rdata = str(data["track"]).encode()
        else: rdata = b"?"
        self.send_response(200)
        self.send_header("Content-Length", str(len(rdata)))
        self.end_headers()
        self.wfile.write(rdata)
    def send_response(self, code, message=None):
        self.send_response_only(code, message)
        self.send_header('Server', self.version_string())
        self.send_header('Date', self.date_time_string())
    def do_POST(self):
        global imc_q
        if self.path == "/api/skip": imc_q.put({"name": "procman", "data": {"op": 2}})
        self.send_response(200)
        self.end_headers()

def web(): HTTPServer(("0.0.0.0", 3001), Handler).serve_forever()
p = multiprocessing.Process(target=web)

class Module(PlayerModule):
    def on_new_playlist(self, playlist: list[Track]) -> None:
        global data, data_lock
        with data_lock: 
            api_data = []
            for track in playlist: api_data.append({"path": str(track.path), "fade_out": track.fade_out, "fade_in": track.fade_in, "official": track.official, "args": track.args, "offset": track.offset})
            data["playlist"] = json.dumps(api_data)
    def on_new_track(self, index: int, track: Track, next_track: Track | None) -> None:
        global data, data_lock
        with data_lock: 
            track_data = {"path": str(track.path), "fade_out": track.fade_out, "fade_in": track.fade_in, "official": track.official, "args": track.args, "offset": track.offset}
            if next_track: next_track_data = {"path": str(next_track.path), "fade_out": next_track.fade_out, "fade_in": next_track.fade_in, "official": next_track.official, "args": next_track.args, "offset": next_track.offset}
            else: next_track_data = None
            data["track"] = json.dumps({"index": index, "track": track_data, "next_track": next_track_data})
    def progress(self, index: int, track: Track, elapsed: float, total: float, real_total: float) -> None:
        try: data = imc_q.get(False)
        except Exception: return

        self._imc.send(self, data["name"], data["data"])
    def shutdown(self):
        global p
        p.terminate()
        p.join(1)
        p.kill()

module = Module()
p.start()