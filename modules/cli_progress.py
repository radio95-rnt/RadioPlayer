from . import PlayerModule, Track
import os

def format_time(seconds) -> str:
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"

class Module(PlayerModule):
    def progress(self, index: int, track: Track, elapsed: float, total: float, real_total: float) -> None:
        if track.official: 
            print(f"{os.path.basename(track.path)}: {format_time(elapsed)} / {format_time(total)}", end="\r", flush=True)
        if os.path.exists("/tmp/radioPlayer_skip"):
            self._imc.send(self, "procman", {"op": 2})

module = Module()