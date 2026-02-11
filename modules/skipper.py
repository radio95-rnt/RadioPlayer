from . import PlayerModule, log95, Track
import os

_log_out: log95.TextIO
assert _log_out # pyright: ignore[reportUnboundVariable]
logger = log95.log95("Skipper", output=_log_out)

class Module(PlayerModule):
    def __init__(self) -> None: self.playlist = []
    def on_new_playlist(self, playlist: list[Track], global_args: dict[str, str]): self.playlist = [str(t.path.absolute()) for t in playlist]
    def progress(self, index: int, track: Track, elapsed: float, total: float, real_total: float) -> None:
        if os.path.exists("/tmp/radioPlayer_skip"):
            self._imc.send(self, "procman", {"op": 2}) # Ask procman to kill every track playing (usually there is one, unless we are in the default 5 seconds of the crossfade)
            os.remove("/tmp/radioPlayer_skip")
    def on_new_track(self, index: int, track: Track, next_track: Track | None):
        if next_track: logger.info("Next up:", next_track.path.name)

module = Module()
