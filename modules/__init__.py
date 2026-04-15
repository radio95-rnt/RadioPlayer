import log95, abc
from collections.abc import Sequence
from subprocess import Popen
from dataclasses import dataclass
from pathlib import Path
import tinytag

@dataclass
class Track:
    path: Path
    fade_out: float
    fade_in: float
    official: bool
    args: dict[str, str] | None
    offset: float = 0.0
    focus_time_offset: float = 0.0 # Offset according to the duration

@dataclass
class Process:
    process: Popen
    track: Track
    started_at: float
    duration: float

class ABC_ProcessManager(abc.ABC):
    @abc.abstractmethod
    def play(self, track: Track) -> Process: ...
    @abc.abstractmethod
    def anything_playing(self) -> bool: ...
    @abc.abstractmethod
    def stop_all(self, timeout: float | None = None) -> None: ...
    @abc.abstractmethod
    def wait_all(self, timeout: float | None = None) -> None: ...
class BaseIMCModule:
    """This is not a module to be used but rather a placeholder IMC api to be used in other modules"""
    def imc(self, imc: 'InterModuleCommunication') -> None:
        """Receive an IMC object"""
        self._imc = imc
    def imc_data(self, source: 'BaseIMCModule', source_name: str | None, data: object, broadcast: bool) -> object: """React to IMC data"""

class ProcmanCommunicator(BaseIMCModule):
    def __init__(self, procman: ABC_ProcessManager) -> None: 
        self.procman = procman
        self.tinytag = tinytag.TinyTag()
    def imc(self, imc: 'InterModuleCommunication') -> None:
        super().imc(imc)
        self._imc.register(self, "procman")
    def imc_data(self, source: BaseIMCModule, source_name: str | None, data: object, broadcast: bool) -> object:
        if broadcast: return
        # if isinstance(data, str) and data.lower().strip() == "raw": return self.procman
        if isinstance(data, dict):
            if (op := data.get("op")) is None: return

            if int(op) == 0: return {"op": 0, "arg": "pong"}
            elif int(op) == 1:
                if arg := data.get("arg"): return {"op": 1, "arg": self.tinytag.get(arg, tags=False).duration}
                else: return
            elif int(op) == 2:
                self.procman.stop_all(data.get("timeout", None))
                return {"op": 2}
            elif int(op) == 3: raise NotImplementedError("This feature was removed.")
            elif int(op) == 4:
                return {"op": 4, "arg": self.procman.anything_playing()}
            elif int(op) == 5:
                if arg := data.get("arg"): return {"op": 5, "arg": self.procman.play(arg)}
                else: return

class PlayerModule(BaseIMCModule):
    """Simple passive observer, this allows you to send the current track the your RDS encoder, or to your website"""
    def on_new_playlist(self, playlist: list[Track], global_args: dict[str, str]) -> None: 
        """This is called every new playlist"""
    def on_new_track(self, index: int, track: Track, next_track: Track | None) -> None:
        """Called on every track including the ones added by the active modifier, you can check for that comparing the playlists[index] and the track"""
    def progress(self, index: int, track: Track, elapsed: float, total: float, real_total: float) -> None:
        """
        Real total and total differ in that, total is how much the track lasts, but real_total will be for how long we will focus on it (crossfade)
        Runs at a frequency around 1 Hz (depending on other plugins it can be rarer, but never any faster)
        Please don't put any blocking or code that takes time
        """
    def shutdown(self): """Ran while shutting down"""
class PlaylistModifierModule:
    """Playlist modifier, this type of module allows you to shuffle, or put jingles into your playlist"""
    def modify(self, global_args: dict, playlist: list[Track]) -> list[Track] | None:
        """global_args are playlist global args (see radioPlayer_playlist_file.txt)"""
        return playlist
    # No IMC, as we only run on new playlists
class PlaylistAdvisor(BaseIMCModule):
    """Only one of a playlist advisor can be loaded. This module picks the playlist file to play, this can be a scheduler or just a static file"""
    def advise(self, arguments: str | None) -> Path | None:
        """Arguments are the arguments passed to the program on startup"""
        return Path("/path/to/playlist.txt")
    def new_playlist(self) -> bool:
        """Whether to play a new playlist, if this is True, then the player will refresh and fetch a new playlist, calling advise"""
        return False
class ActiveModifier(BaseIMCModule):
    """This changes the next song to be played live, which means that this picks the next song, not the playlist, but this is affected by the playlist"""
    def arguments(self, arguments: str | None) -> None: """Called at start up with the program arguments"""
    def play(self, index: int, track: Track | None, next_track: Track | None) -> tuple[tuple[Track | None, Track | None], bool | None]:
        """
        Returns a tuple, in the first case where a is the track and b is a bool, b corresponds to whether to extend the playlist, set to true when adding content instead of replacing it
        When None, None is returned then that is treated as a skip, meaning the core will skip this song
        The second track object is the next track, which is optional which is also only used for metadata and will not be taken in as data to play
        """
        return (track, None), False
    def on_new_playlist(self, playlist: list[Track], global_args: dict[str, str]) -> None: """Same behaviour as the basic module function"""
class InterModuleCommunication:
    def __init__(self, modules: Sequence[BaseIMCModule | None]) -> None:
        self.modules = modules
        self.names_modules: dict[str, BaseIMCModule] = {}
        [module.imc(self) for module in modules if module]
    def broadcast(self, source: BaseIMCModule, data: object) -> None:
        """Send data to all modules, other than ourself"""
        source_name = next((k for k, v in self.names_modules.items() if v is source), None)
        for module in [f for f in self.modules if (f is not source) and f]: module.imc_data(source, source_name, data, True)
    def register(self, module: BaseIMCModule, name: str) -> bool:
        """Register our module with a name, so we can be sent data via the send function"""
        if name in self.names_modules.keys(): return False
        self.names_modules[name] = module
        return True
    def send(self, source: BaseIMCModule, name: str, data: object, aggressive: bool = True) -> object:
        """Sends the data to a named module, and return its response"""
        if not name in self.names_modules.keys(): 
            if aggressive: raise ModuleNotFoundError("No such module")
            return None
        
        return self.names_modules[name].imc_data(source, next((k for k, v in self.names_modules.items() if v is source), None), data, False)

class PlaylistParser:
    def __init__(self) -> None: pass
    def parse(self, playlist_path: Path) -> tuple[dict[str, str], list[tuple[list[str], dict[str, str]]]]:
        """
        This should return the following information:
        global arguments,
        list of entries:
            a entry is just a tuple of a list of strings (file paths)
            and a dictionary of str:str consistent of the arguments which affect the files given
        """
        return {}, []
    
# This is free and unencumbered software released into the public domain.

# Anyone is free to copy, modify, publish, use, compile, sell, or
# distribute this software, either in source code form or as a compiled
# binary, for any purpose, commercial or non-commercial, and by any
# means.

# In jurisdictions that recognize copyright laws, the author or authors
# of this software dedicate any and all copyright interest in the
# software to the public domain. We make this dedication for the benefit
# of the public at large and to the detriment of our heirs and
# successors. We intend this dedication to be an overt act of
# relinquishment in perpetuity of all present and future rights to this
# software under copyright law.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
# IN NO EVENT SHALL THE AUTHORS BE LIABLE FOR ANY CLAIM, DAMAGES OR
# OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE,
# ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR
# OTHER DEALINGS IN THE SOFTWARE.

# For more information, please refer to <https://unlicense.org>