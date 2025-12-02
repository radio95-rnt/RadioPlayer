from . import PlayerModule, Track, Path

def format_time(seconds) -> str:
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"

class Module(PlayerModule):
    def progress(self, index: int, track: Track, elapsed: float, total: float, real_total: float) -> None:
        if track.official:
            data = f"{track.path.name}: {format_time(elapsed)} / {format_time(total)}\n"
            Path("/tmp/radioPlayer_progress").write_text(data)

module = Module()