import glob as glob_module
from . import log95, Path, PlaylistParser

_log_out: log95.TextIO

def _parse_args(text: str) -> dict[str, str]:
    args = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith(";") or line.startswith("#"): continue
        if "=" in line:
            key, val = line.split("=", 1)
            args[key.strip()] = val.strip()
        else:
            args[line] = True
    return args

class FSDBParser(PlaylistParser):
    def __init__(self, ref_dir: Path) -> None:
        self.logger = log95.log95("FSDB", output=_log_out)
        self.ref_dir = ref_dir.resolve().absolute()

    def parse(self, playlist_path: Path) -> tuple[dict[str, str], list[tuple[list[str], dict[str, str]]]]:
        if not playlist_path.is_dir():
            self.logger.error(f"Playlist path is not a directory: {playlist_path}")
            raise Exception("Playlist directory doesn't exist")

        global_args = {}
        if (global_args_file := playlist_path / ".args.txt").exists():
            global_args = _parse_args(global_args_file.read_text())

        out = []
        for entry in sorted(playlist_path.iterdir()):
            if entry.name.startswith("."): continue

            if entry.is_file():
                real = self.ref_dir / entry.name
                files = [f for f in glob_module.glob(str(real)) if Path(f).is_file()]
                if not files:
                    self.logger.warning(f"No match in ref_dir for: {entry.name}")
                    continue
                args = _parse_args(entry.read_text()) if entry.stat().st_size > 0 else {}
                out.append((files, args))
            elif entry.is_dir():
                real_dir = self.ref_dir / entry.name
                if not real_dir.is_dir():
                    self.logger.warning(f"No matching directory in ref_dir for: {entry.name}")
                    continue
                files = [f for f in glob_module.glob(str(real_dir / "**"), recursive=True) if Path(f).is_file()]
                if not files:
                    self.logger.warning(f"No files found under ref_dir for group: {entry.name}")
                    continue
                args = _parse_args((entry / ".args.txt").read_text()) if (entry / ".args.txt").exists() else {}
                out.append((files, args))

        return global_args, out

parser = FSDBParser(Path("/home/user/mixes"))

# Claude wrote it and agreed to unlicense this

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