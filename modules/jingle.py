"""
Jingle genarator module

Takes an file argument to initialize, which is the absolute path to the jingle file

Reacts to the 'no_jingle' argument, for global usage it does not add jingles to the playlist, and for file usage it does not add the jingle after the file
"""

import random, log95

logger = log95.log95("JINGLE-GEN")

class PlaylistModifierModule:
    def modify(self, global_args: dict, playlist: list[tuple[str, bool, bool, bool, dict]]):
        return playlist

class Module(PlaylistModifierModule):
    def __init__(self, file: str) -> None:
        logger.info("Generating jingles with the following random state:", repr(random.getstate()))
        self.file = file
    def modify(self, global_args: dict, playlist: list[tuple[str, bool, bool, bool, dict]]):
        if int(global_args.get("no_jingle", 0)): return playlist
        out: list[tuple[str, bool, bool, bool, dict]] = []
        last_jingiel = True
        for (track, _, _, _, args) in playlist:
            if not last_jingiel and random.choice([False, True, False, False]) and self.file and int(args.get("no_jingle", 0)) == 0:
                out.append((track, True, False, True, args))
                out.append((self.file, False, False, False, {}))
                last_jingiel = True
            else:
                out.append((track, True, True, True, args))
                last_jingiel = False
        del last_jingiel

playlistmod = (Module("/home/user/Jingiel.mp3"), 1)