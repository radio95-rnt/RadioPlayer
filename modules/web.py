import multiprocessing, json

from . import PlayerModule, Track
from http.server import HTTPServer, BaseHTTPRequestHandler

manager = multiprocessing.Manager()
data = manager.dict()
data_lock = manager.Lock()

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        global data
        if self.path == "/api/playlist":
            rdata = repr(data["playlist"]).encode()
        elif self.path == "/api/track":
            rdata = repr(data["track"]).encode()
        else: rdata = b"?"
        self.send_response(200)
        self.send_header("Content-Length", str(len(rdata)))
        self.end_headers()
        self.wfile.write(rdata)

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
            if next_track: next_track_data = {"path": str(next_track), "fade_out": next_track.fade_out, "fade_in": next_track.fade_in, "official": next_track.official, "args": next_track.args, "offset": next_track.offset}
            else: next_track_data = None
            data["track"] = json.dumps({"index": index, "track": track_data, "next_track": next_track_data})
    def shutdown(self):
        global p
        p.terminate()
        p.join()

module = Module()
p.start()