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