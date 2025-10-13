class PlayerModule:
    def on_new_playlist(self, playlist: list[tuple[str, bool, bool, bool, dict]]):
        pass
    def on_new_track(self, index: int, track: str, to_fade_in: bool, to_fade_out: bool, official: bool):
        pass

class Module(PlayerModule):
    def __init__(self) -> None:
        self.playlist = []
    def on_new_playlist(self, playlist: list[tuple[str, bool, bool, bool, dict]]):
        self.playlist = [t[0] for t in playlist]
    def on_new_track(self, index: int, track: str, to_fade_in: bool, to_fade_out: bool, official: bool):
        if track != self.playlist[index]:
            # discrepancy, which means that the playing file was modified by the active modifier
            # we are playing a file that was not determined in the playlist, that means it was chosen by the active modifier and made up on the fly
            lines = self.playlist[:index] + [self.playlist[index]] + [f"> {track}"] + self.playlist[index+1:]
        else: lines = self.playlist[:index] + [f"> {self.playlist[index]}"] + self.playlist[index+1:]
        with open("/tmp/radioPlayer_playlist", "w") as f:
            for line in lines: 
                try: f.write(line + "\n")
                except UnicodeEncodeError:
                    print(line.encode('utf-8', errors='ignore').decode('utf-8'))
                    raise

module = Module()