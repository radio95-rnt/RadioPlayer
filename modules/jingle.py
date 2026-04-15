"""
Jingle genarator module

Takes an file argument to initialize, which is the absolute path to the jingle file

Reacts to the 'no_jingle' argument, for global usage it does not add jingles to the playlist, and for file usage it does not add the jingle after the file
"""

import random

from modules import BaseIMCModule, InterModuleCommunication

from . import PlaylistModifierModule, Track, Path, PlayerModule

def get_jingles():
    master: Path | None = None
    jingles: list[Path] = []
    for file in Path("/home/user/mixes/.playlist/jingle").iterdir():
        if not (file.is_file() and file.exists()): continue
        name, _ = file.name.rsplit('.', 1)
        if name.lower() == "master":
            master = file
            continue
        jingles.append(file)
    if not master: master = jingles.pop(0)
    return master, jingles

def chance(one_in_n): return random.randint(1, one_in_n) == 1

class Module(PlaylistModifierModule):
    def modify(self, global_args: dict, playlist: list[Track]) -> list[Track] | None:
        if int(global_args.get("no_jingle", 0)) != 0: return None

        primary, secondary = get_jingles()

        out: list[Track] = []
        last_jingiel = True
        for track in playlist:
            if not last_jingiel and chance(3) and (track.args is None or int(track.args.get("no_jingle", 0)) == 0):
                out.append(Track(track.path, 0, track.fade_in, True, track.args))
                jingle = primary
                if secondary and chance(2): jingle = random.choice(secondary)
                out.append(Track(jingle, 0, 0, False, {}))
                last_jingiel = True
                continue
            out.append(Track(track.path, track.fade_out, track.fade_in, True, track.args,focus_time_offset=-track.fade_out))
            last_jingiel = False
        return out

class Module2(PlayerModule):
    def imc(self, imc: InterModuleCommunication) -> None:
        super().imc(imc)
        imc.register(self, "jingle")
    def imc_data(self, source: BaseIMCModule, source_name: str | None, data: bool, broadcast: bool) -> object:
        if broadcast: return
        jingle, secondary = get_jingles()
        if secondary and chance(2): jingle = random.choice(secondary)
        return self._imc.send(self, "activemod", {"action": "add_to_toplay", "songs": [f"!{jingle}"], "top": bool(data)})

module = Module2()
playlistmod = Module(), 2
