import multiprocessing

from . import PlayerModule, Track
from flask import Flask

manager = multiprocessing.Manager()
data = manager.dict()
data_lock = manager.Lock()

app = Flask(__name__)
app.logger.disabled = True

@app.route("/")
def home():
    global data, data_lock
    with data_lock: return repr(data["playlist"])

def web():
    app.run("0.0.0.0", 3001)
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