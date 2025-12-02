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
        self.logger = log95.log95("PlayCnt", output=_log_out)
        self.file = Path(__file__, "..", "..", "play_counter").resolve()
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
                for k, v in sorted(self.counts.items()): f.write(f"{k}:{v}\n")
            temp_file.replace(self.file)
        except Exception as e: self.logger.error(f"Failed to write play counts: {e}")
    def on_new_track(self, index: int, track: Track, next_track: Track | None) -> None:
        self.counts[track.path.as_posix()] = self.counts.get(track.path.as_posix(), 0) + 1
        self._save_counts()
    def shutdown(self):
        self._save_counts()

module = Module()