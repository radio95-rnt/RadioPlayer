from ..player_modules import PlayerModule

def write_playlist(tracks: list, i: int):
    lines = tracks[:i] + [f"> {tracks[i]}"] + tracks[i+1:]
    with open("/tmp/radioPlayer_playlist", "w") as f:
        for line in lines: 
            try: f.write(line + "\n")
            except UnicodeEncodeError:
                print(line.encode('utf-8', errors='ignore').decode('utf-8'))
                raise

class Module(PlayerModule):
    def __init__(self) -> None:
        self.playlist = []
    def on_new_playlist(self, playlist: list[str]):
        self.playlist = playlist
    def on_new_track(self, track: str, index: int):
        write_playlist(self.playlist, index)