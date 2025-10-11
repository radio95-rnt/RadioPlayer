import random

JINGIEL_FILE = "/home/user/Jingiel.mp3"

class PlaylistModifierModule:
    def modify(self, global_args: dict, playlist: list[tuple[str, bool, bool, bool, dict]]):
        return playlist

class Module(PlaylistModifierModule):
    def modify(self, global_args: dict, playlist: list[tuple[str, bool, bool, bool, dict]]):
        if int(global_args.get("no_jingle", 0)): return playlist
        out: list[tuple[str, bool, bool, bool, dict]] = []
        last_jingiel = True
        for (track, _, _, _, args) in playlist:
            if not last_jingiel and random.choice([False, True, False, False]) and JINGIEL_FILE and int(args.get("no_jingle", 0)) == 0:
                out.append((track, True, False, True, args))
                out.append((JINGIEL_FILE, False, False, False, args))
                last_jingiel = True
            else:
                out.append((track, True, True, True, args))
                last_jingiel = False
        del last_jingiel

playlistmod = (Module(), 1)