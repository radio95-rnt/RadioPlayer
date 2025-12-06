import multiprocessing

from . import PlayerModule, Track
from http.server import HTTPServer, BaseHTTPRequestHandler

manager = multiprocessing.Manager()
data = manager.dict()
data_lock = manager.Lock()

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        global data
        if self.path == "/":
            rdata = repr(data["playlist"]).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(rdata)

def web():
    HTTPServer(("0.0.0.0", 3001), Handler).serve_forever()
p = multiprocessing.Process(target=web)

class Module(PlayerModule):
    def on_new_playlist(self, playlist: list[Track]) -> None:
        global data, data_lock
        with data_lock: data["playlist"] = playlist
    def shutdown(self):
        global p
        p.terminate()
        p.join()

module = Module()
p.start()