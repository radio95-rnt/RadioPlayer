from . import PlayerModule, log95, Track
import os

from typing import TextIO
_log_file: TextIO

assert _log_file # pyright: ignore[reportUnboundVariable]
logger = log95.log95("PlayView", output=_log_file)

class Module(PlayerModule):
    def __init__(self) -> None:
        self.playlist = []
    def on_new_playlist(self, playlist: list[Track]):
        self.playlist = [str(t.path.absolute()) for t in playlist]
    def progress(self, index: int, track: Track, elapsed: float, total: float, real_total: float) -> None:
        if os.path.exists("/tmp/radioPlayer_skip"):
            self._imc.send(self, "procman", {"op": 2})
            os.remove("/tmp/radioPlayer_skip")
    def on_new_track(self, index: int, track: Track, next_track: Track | None):
        if next_track: logger.info("Next up:", next_track.path.name)
        if str(track.path) != self.playlist[index]:
            # discrepancy, which means that the playing file was modified by the active modifier
            # we are playing a file that was not determined in the playlist, that means it was chosen by the active modifier and made up on the fly
            lines = self.playlist[:index] + [f"> ({track.path})"] + [self.playlist[index]] + self.playlist[index+1:]
        else: 
            lines = self.playlist[:index] + [f"> {self.playlist[index]}"] + self.playlist[index+1:]
        with open("/tmp/radioPlayer_playlist", "w") as f:
            for line in lines: 
                try: f.write(line + "\n")
                except UnicodeEncodeError:
                    print(line.encode('utf-8', errors='ignore').decode('utf-8'))
                    raise

module = Module()
