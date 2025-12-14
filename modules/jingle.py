"""
Jingle genarator module

Takes an file argument to initialize, which is the absolute path to the jingle file

Reacts to the 'no_jingle' argument, for global usage it does not add jingles to the playlist, and for file usage it does not add the jingle after the file
"""

import random

from modules import BaseIMCModule, InterModuleCommunication

from . import PlaylistModifierModule, Track, Path, PlayerModule

class Module(PlaylistModifierModule):
    def __init__(self, primary: Path, secondary: list[Path] | None = None) -> None:
        if secondary is None: secondary = []
        self.primary = primary.absolute()
        assert primary.exists()
        self.secondary = [f.absolute() for f in secondary if f.exists()]
    def modify(self, global_args: dict, playlist: list[Track]) -> list[Track] | None:
        if int(global_args.get("no_jingle", 0)) != 0 or not self.primary: return None
        out: list[Track] = []
        last_jingiel = True
        crossfade = float(global_args.get("crossfade", 5.0))
        for track in playlist:
            if not last_jingiel and (random.randint(1,3) == 1) and (track.args is None or int(track.args.get("no_jingle", 0)) == 0):
                out.append(Track(track.path, crossfade, 0, True, track.args, focus_time_offset=-crossfade))
                jingle = self.primary
                if self.secondary and (random.randint(1,3) == 1): jingle = random.choice(self.secondary)
                out.append(Track(jingle, 0, 0, False, {}))
                last_jingiel = True
                continue
            out.append(Track(track.path, crossfade, crossfade, True, track.args,focus_time_offset=-crossfade))
            last_jingiel = False
        return out
    
class Module2(PlayerModule):
    def __init__(self, primary: Path, secondary: list[Path] | None = None) -> None:
        if secondary is None: secondary = []
        self.primary = primary.absolute()
        assert primary.exists()
        self.secondary = [f.absolute() for f in secondary if f.exists()]
    def imc(self, imc: InterModuleCommunication) -> None:
        super().imc(imc)
        self._imc.register(self, "jingle")
    def imc_data(self, source: BaseIMCModule, source_name: str | None, data: object, broadcast: bool) -> object:
        if broadcast: return
        jingle = self.primary
        if self.secondary and (random.randint(1,3) == 1): jingle = random.choice(self.secondary)
        return self._imc.send(self, "activemod", {"action": "add_to_toplay", "songs": [jingle]})

options = Path("/home/user/Jingiel.mp3"), [Path("/home/user/jing2.opus"), Path("Jing3.opus")]
module = Module2(*options)
playlistmod = (Module(*options), 1)