from . import log95, PlaylistModifierModule, Track, Path

_log_out: log95.TextIO
assert _log_out # pyright: ignore[reportUnboundVariable]

def load_play_counts(file_path: Path) -> dict[str, int]:
    counts = {}
    try:
        with open(file_path, 'r') as file:
            for line in file:
                if line.strip() == "" or line.startswith(";"): continue
                try:
                    key, value = line.split(':', 1)
                    counts[key.strip()] = int(value.strip())
                except ValueError: continue
        return counts
    except FileNotFoundError: return {}

class PopularitySorterModule(PlaylistModifierModule):
    def __init__(self) -> None:
        self.logger = log95.log95("PopSort", output=_log_out)
        self.play_counts_file = Path("/home/user/mixes/.playlist/count.txt")

    def modify(self, global_args: dict, playlist: list[Track]) -> list[Track]:
        self.logger.info("Applying popularity-based sorting to the playlist...")

        play_counts = load_play_counts(self.play_counts_file)
        if not play_counts:
            self.logger.info("Play counter file not found or is empty. No sorting will be applied.")
            return playlist

        sorted_by_play_count = sorted(play_counts.items(), key=lambda item: item[1], reverse=True)

        SORT_LEN = len(playlist) // 3
        top_paths = {path for path, count in sorted_by_play_count[:SORT_LEN]}
        least_top_paths = {path for path, count in sorted_by_play_count[-SORT_LEN:]}
        for a,b in zip(top_paths, least_top_paths):
            a_track = b_track = None
            a_i = b_i = 0
            for a_i, a_track in enumerate(playlist):
                if not a_track.official: continue
                if a_track.path == a: break
            if not a_track: continue
            for b_i, b_track in enumerate(playlist):
                if not b_track.official: continue
                if b_track.path == b: break
            if not b_track: continue
            if a_i < b_i: playlist[a_i], playlist[b_i] = playlist[b_i], playlist[a_i]

        i = 0
        while i < len(playlist) - 1:
            track1 = playlist[i]
            track2 = playlist[i+1]

            if not (track1.official and track2.official):
                i += 2
                continue

            count1 = play_counts.get(track1.path.as_posix(), 0)
            count2 = play_counts.get(track2.path.as_posix(), 0)

            if count1 > count2: 
                playlist[i], playlist[i+1] = track2, track1
            i += 2

        self.logger.info("Popularity sorting complete.")
        return playlist

playlistmod = PopularitySorterModule(), 2

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