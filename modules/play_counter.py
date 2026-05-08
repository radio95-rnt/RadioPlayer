from . import log95, PlayerModule, Track, Path
_log_out: log95.TextIO
assert _log_out # pyright: ignore[reportUnboundVariable]

def load_dict_from_custom_format(file_path: str | Path) -> dict[str, str]:
    try:
        result_dict = {}
        with open(file_path, 'r') as file:
            for line in file:
                if line.strip() == "" or line.startswith(";"): continue
                key, value = line.split(':', 1)
                result_dict[key.strip()] = value.strip()
        return result_dict
    except FileNotFoundError: return {}

class Module(PlayerModule):
    def __init__(self) -> None:
        self.logger = log95.log95("PlayCnt", output=_log_out) # That sounds bad...
        self.file = Path("/home/user/mixes/.playlist/count.txt").resolve()
        self.counts: dict[str, int] = {}
        loaded = load_dict_from_custom_format(self.file)
        for k, v in loaded.items():
            try: self.counts[k] = int(v)
            except ValueError:
                self.logger.warning(f"Invalid count for {k}: {v}, resetting to 0")
                self.counts[k] = 0
    def _save_counts(self) -> None:
        try:
            temp_file = self.file.with_suffix('.tmp')
            with open(temp_file, 'w') as f:
                for k, v in sorted(self.counts.items()):
                    if Path(k).exists(): f.write(f"{k}:{v}\n")
            temp_file.replace(self.file)
        except Exception as e: self.logger.error(f"Failed to write play counts: {e}")
    def on_new_track(self, index: int, track: Track, next_track: Track | None) -> None:
        self.counts[track.path.as_posix()] = self.counts.get(track.path.as_posix(), 0) + 1
        self._save_counts()
    def shutdown(self): self._save_counts()

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