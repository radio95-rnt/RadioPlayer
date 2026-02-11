import glob
from . import log95, Path, PlaylistParser

_log_out: log95.TextIO
class PlaintextParser(PlaylistParser):
    def __init__(self): self.logger = log95.log95("PARSER", output=_log_out)

    def _check_for_imports(self, path: Path, seen=None) -> list[str]:
        if seen is None: seen = set()
        if not path.exists():
            self.logger.error(f"Playlist not found: {path.name}")
            raise Exception("Playlist doesn't exist")
        lines = [line.strip() for line in path.read_text().splitlines() if line.strip()]

        out = []
        for line in lines:
            if line.startswith("@"):
                target = Path(line.removeprefix("@"))
                if target not in seen:
                    if not target.exists():
                        self.logger.error(f"Target {target.name} of {path.name} does not exist")
                        continue
                    seen.add(target)
                    out.extend(self._check_for_imports(target, seen))
            else: out.append(line)
        return out

    def parse(self, playlist_path: Path) -> tuple[dict[str, str], list[tuple[list[str], dict[str, str]]]]:
        lines = self._check_for_imports(playlist_path)
        out = []
        global_arguments = {}
        for line in lines:
            arguments = {}
            line = line.strip()
            if not line or line.startswith(";") or line.startswith("#"): continue
            if "|" in line:
                if line.startswith("|"): # No file name, we're defining global arguments
                    args = line.removeprefix("|").split(";")
                    for arg in args:
                        if "=" in arg:
                            key, val = arg.split("=", 1)
                            arguments[key] = val
                        else:
                            arguments[arg] = True
                else:
                    line, args = line.split("|", 1)
                    args = args.split(";")
                    for arg in args:
                        if "=" in arg:
                            key, val = arg.split("=", 1)
                            arguments[key] = val
                        else:
                            arguments[arg] = True
            out.append(([f for f in glob.glob(line) if Path(f).is_file()], arguments))
        return global_arguments, out

parser = PlaintextParser()