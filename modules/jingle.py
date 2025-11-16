"""
Jingle genarator module

Takes an file argument to initialize, which is the absolute path to the jingle file

Reacts to the 'no_jingle' argument, for global usage it does not add jingles to the playlist, and for file usage it does not add the jingle after the file
"""

import random

from . import PlaylistModifierModule, Track, Path

class Module(PlaylistModifierModule):
    def __init__(self, primary: Path, secondary: list[Path] = []) -> None:
        self.primary = primary.absolute()
        assert primary.exists()
        self.secondary = [f.absolute() for f in secondary if f.exists()]
    def modify(self, global_args: dict, playlist: list[Track]) -> list[Track] | None:
        if int(global_args.get("no_jingle", 0)) != 0 or not self.primary: return None
        out: list[Track] = []
        last_jingiel = True
        for track in playlist:
            if not last_jingiel and (random.randint(1,3) == 1) and (track.args is None or int(track.args.get("no_jingle", 0)) == 0):
                out.append(Track(track.path, True, False, True, track.args))
                jingle = self.primary
                if self.secondary and (random.randint(1,3) == 1): jingle = random.choice(self.secondary) or self.primary
                out.append(Track(jingle, False, False, False, {}))
                last_jingiel = True
                continue
            out.append(Track(track.path, True, True, True, track.args))
            last_jingiel = False
        return out

playlistmod = (Module(Path("/home/user/Jingiel.mp3"), [Path("/home/user/jing2.opus"), Path("Jing3.opus")]), 1)