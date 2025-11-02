"""
Jingle genarator module

Takes an file argument to initialize, which is the absolute path to the jingle file

Reacts to the 'no_jingle' argument, for global usage it does not add jingles to the playlist, and for file usage it does not add the jingle after the file
"""

import random

from . import PlaylistModifierModule, Track

class Module(PlaylistModifierModule):
    def __init__(self, file: str) -> None:
        self.file = file
    def modify(self, global_args: dict, playlist: list[Track]) -> list[Track] | None:
        if int(global_args.get("no_jingle", 0)): return None
        out: list[Track] = []
        last_jingiel = True
        for track in playlist:
            if not last_jingiel and random.choice([False, True, False, False]) and self.file and (track.args and int(track.args.get("no_jingle", 0)) == 0):
                out.append(Track(track.path, True, False, True, track.args))
                out.append(Track(self.file, False, False, False, {}))
                last_jingiel = True
                continue
            out.append(Track(track.path, True, True, True, track.args))
            last_jingiel = False
        del last_jingiel
        return out

playlistmod = (Module("/home/user/Jingiel.mp3"), 1)