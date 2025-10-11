from typing import TYPE_CHECKING
if TYPE_CHECKING:
    class PlayerModule:
        def on_new_playlist(self, playlist: list[tuple[str, bool, bool, bool]]):
            pass
        def on_new_track(self, index: int, track: str, to_fade_in: bool, to_fade_out: bool, official: bool):
            pass

class Module(PlayerModule):
    def __init__(self) -> None:
        self.playlist = []
    def on_new_playlist(self, playlist: list[tuple[str, bool, bool, bool]]):
        self.playlist = [t[0] for t in playlist]
    def on_new_track(self, index: int, track: str, to_fade_in: bool, to_fade_out: bool, official: bool):
        lines = self.playlist[:index] + [f"> {self.playlist[index]}"] + self.playlist[index+1:]
        with open("/tmp/radioPlayer_playlist", "w") as f:
            for line in lines: 
                try: f.write(line + "\n")
                except UnicodeEncodeError:
                    print(line.encode('utf-8', errors='ignore').decode('utf-8'))
                    raise

module = Module()