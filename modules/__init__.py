import log95
from collections.abc import Sequence
from subprocess import Popen
from dataclasses import dataclass
from pathlib import Path

@dataclass
class Track:
    path: Path
    fade_out: bool
    fade_in: bool
    official: bool
    args: dict[str, str] | None
    offset: float = 0.0

@dataclass
class Process:
    process: Popen
    track: Track
    started_at: float
    duration: float

class Skeleton_ProcessManager:
    processes: list[Process]
    def _get_audio_duration(self, file_path): ...
    def play(self, track: Track, fade_in_time: int=0, fade_out_time: int=0) -> Process: ...
    def anything_playing(self) -> bool: ...
    def stop_all(self, timeout: float | None = None) -> None: ...
    def wait_all(self, timeout: float | None = None) -> None: ...
class BaseIMCModule:
    """
    This is not a module to be used but rather a placeholder IMC api to be used in other modules
    """
    def imc(self, imc: 'InterModuleCommunication') -> None:
        """
        Receive an IMC object
        """
        self._imc = imc
    def imc_data(self, source: 'BaseIMCModule', source_name: str | None, data: object, broadcast: bool) -> object:
        """
        React to IMC data
        """
        return None

class ProcmanCommunicator(BaseIMCModule):
    def __init__(self, procman: Skeleton_ProcessManager) -> None: self.procman = procman
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
                if arg := data.get("arg"): return {"op": 1, "arg": self.procman._get_audio_duration(arg)}
                else: return
            elif int(op) == 2:
                self.procman.stop_all(data.get("timeout", None))
                return {"op": 2}
            elif int(op) == 3:
                return {"op": 3, "arg": self.procman.processes}
            elif int(op) == 4:
                return {"op": 4, "arg": self.procman.anything_playing()}
            elif int(op) == 5:
                if arg := data.get("arg"): return {"op": 5, "arg": self.procman.play(arg, data.get("fade_in_time", data.get("fade_time", 5)), data.get("fade_out_time", data.get("fade_time", 5)))}
                else: return

class PlayerModule(BaseIMCModule):
    """
    Simple passive observer, this allows you to send the current track the your RDS encoder, or to your website
    """
    def on_new_playlist(self, playlist: list[Track]) -> None:
        """This is called every new playlist"""
        pass
    def on_new_track(self, index: int, track: Track, next_track: Track | None) -> None:
        """
        Called on every track including the ones added by the active modifier, you can check for that comparing the playlists[index] and the track
        """
        pass
    def progress(self, index: int, track: Track, elapsed: float, total: float, real_total: float) -> None:
        """
        Real total and total differ in that, total is how much the track lasts, but real_total will be for how long we will focus on it (crossfade)
        Runs at a frequency around 1 Hz
        Please don't put any blocking or code that takes time
        """
        pass
    def shutdown(self):
        """
        Ran while shutting down
        """
        pass
class PlaylistModifierModule:
    """
    Playlist modifier, this type of module allows you to shuffle, or put jingles into your playlist
    """
    def modify(self, global_args: dict, playlist: list[Track]) -> list[Track] | None:
        """
        global_args are playlist global args (see radioPlayer_playlist_file.txt)
        """
        return playlist
    # No IMC, as we only run on new playlists
class PlaylistAdvisor(BaseIMCModule):
    """
    Only one of a playlist advisor can be loaded. This module picks the playlist file to play, this can be a scheduler or just a static file
    """
    def advise(self, arguments: str | None) -> Path | None:
        """
        Arguments are the arguments passed to the program on startup
        """
        return Path("/path/to/playlist.txt")
    def new_playlist(self) -> bool:
        """
        Whether to play a new playlist, if this is True, then the player will refresh and fetch a new playlist, calling advise
        """
        return False
class ActiveModifier(BaseIMCModule):
    """
    This changes the next song to be played live, which means that this picks the next song, not the playlist, but this is affected by the playlist
    """
    def arguments(self, arguments: str | None) -> None:
        """
        Called at start up with the program arguments
        """
        pass
    def play(self, index: int, track: Track | None, next_track: Track | None) -> tuple[tuple[Track | None, Track | None], bool | None]:
        """
        Returns a tuple, in the first case where a is the track and b is a bool, b corresponds to whether to extend the playlist, set to true when adding content instead of replacing it
        When None, None is returned then that is treated as a skip, meaning the core will skip this song
        The second track object is the next track, which is optional which is also only used for metadata and will not be taken in as data to play
        """
        return (track, None), False
    def on_new_playlist(self, playlist: list[Track]) -> None:
        """
        Same behaviour as the basic module function
        """
        pass
class InterModuleCommunication:
    def __init__(self, modules: Sequence[BaseIMCModule | None]) -> None:
        self.modules = modules
        self.names_modules: dict[str, BaseIMCModule] = {}
        [module.imc(self) for module in modules if module]
    def broadcast(self, source: BaseIMCModule, data: object) -> None:
        """
        Send data to all modules, other than ourself
        """
        source_name = next((k for k, v in self.names_modules.items() if v is source), None)
        for module in [f for f in self.modules if (f is not source) and f]: module.imc_data(source, source_name, data, True)
    def register(self, module: BaseIMCModule, name: str) -> bool:
        """
        Register our module with a name, so we can be sent data via the send function
        """
        if name in self.names_modules.keys(): return False
        self.names_modules[name] = module
        return True
    def send(self, source: BaseIMCModule, name: str, data: object) -> object:
        """
        Sends the data to a named module, and return its response
        """
        if not name in self.names_modules.keys(): raise Exception("No such module")
        return self.names_modules[name].imc_data(source, next((k for k, v in self.names_modules.items() if v is source), None), data, False)