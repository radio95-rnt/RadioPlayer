import os
from . import PlayerModule, Track

class Module(PlayerModule):
    def __init__(self) -> None:
        self.playlist = []
    def on_new_playlist(self, playlist: list[Track]):
        self.playlist = [t.path.absolute() for t in playlist]
    def on_new_track(self, index: int, track: Track):
        if track.path.absolute().as_posix() != self.playlist[index].as_posix():
            # discrepancy, which means that the playing file was modified by the active modifier
            # we are playing a file that was not determined in the playlist, that means it was chosen by the active modifier and made up on the fly
            next = self.playlist[index]
        else: 
            next = self.playlist[index+1]

        with open(track.path.absolute(), "rb") as f:
            os.posix_fadvise(f.fileno(), 0, 0, os.POSIX_FADV_SEQUENTIAL)
            os.posix_fadvise(f.fileno(), 0, 0, os.POSIX_FADV_NOREUSE)
            os.posix_fadvise(f.fileno(), 0, 0, os.POSIX_FADV_WILLNEED)
        with open(next, "rb") as f:
            os.posix_fadvise(f.fileno(), 0, 0, os.POSIX_FADV_SEQUENTIAL)
            os.posix_fadvise(f.fileno(), 0, 0, os.POSIX_FADV_NOREUSE)
            os.posix_fadvise(f.fileno(), 0, 0, os.POSIX_FADV_WILLNEED)

module = Module()