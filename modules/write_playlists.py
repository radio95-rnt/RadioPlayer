from . import PlayerModule, log95, Track

logger = log95.log95("PlayView")

class Module(PlayerModule):
    def __init__(self) -> None:
        self.playlist = []
    def on_new_playlist(self, playlist: list[Track]):
        self.playlist = [t.path for t in playlist]
    def on_new_track(self, index: int, track: Track):
        if track.path != self.playlist[index]:
            # discrepancy, which means that the playing file was modified by the active modifier
            # we are playing a file that was not determined in the playlist, that means it was chosen by the active modifier and made up on the fly
            lines = self.playlist[:index] + [f"> ({track.path})"] + [self.playlist[index]] + self.playlist[index+1:]
            logger.info("Next up:", self.playlist[index])
        else: 
            lines = self.playlist[:index] + [f"> {self.playlist[index]}"] + self.playlist[index+1:]
            if index + 1 < len(self.playlist): logger.info("Next up:", self.playlist[index+1])
        with open("/tmp/radioPlayer_playlist", "w") as f:
            for line in lines: 
                try: f.write(line + "\n")
                except UnicodeEncodeError:
                    print(line.encode('utf-8', errors='ignore').decode('utf-8'))
                    raise

module = Module()