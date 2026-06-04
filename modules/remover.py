from . import PlaylistModifierModule, Track, PlayerModule
from pathlib import Path
import datetime

PLAYED_FILE = Path("/home/user/mixes/.playlist/played.txt")

played_tracks: set[Path] = set()

def get_day():
    t = datetime.datetime.now()
    return t.day + (t.month * 100)

def load_played():
    if not PLAYED_FILE.exists():
        return
    lines = PLAYED_FILE.read_text().splitlines()
    if not lines:
        return
    try:
        saved_day = int(lines[0])
    except ValueError:
        return
    if saved_day != get_day():
        return  # Different day, discard
    for line in lines[1:]:
        if line:
            played_tracks.add(Path(line))

def save_played():
    PLAYED_FILE.parent.mkdir(parents=True, exist_ok=True)
    lines = [str(get_day())] + [str(p) for p in played_tracks]
    PLAYED_FILE.write_text("\n".join(lines))

load_played()

class Module(PlaylistModifierModule):
    def modify(self, global_args: dict, playlist: list[Track]) -> list[Track] | None:
        lines = PLAYED_FILE.read_text().splitlines() if PLAYED_FILE.exists() else []
        saved_day = int(lines[0]) if lines else None
        if saved_day != get_day():
            played_tracks.clear()
            save_played()
            return playlist

        output = []
        for track in playlist:
            if track.path in played_tracks: continue
            output.append(track)
        if len(output) < (len(playlist) / 4): return playlist
        return output

class Module2(PlayerModule):
    def on_new_track(self, index: int, track: Track, next_track: Track | None) -> None:
        played_tracks.add(track.path)
        save_played()

playlistmod = Module(), 3
module = Module2()

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