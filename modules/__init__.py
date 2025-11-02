import log95
from dataclasses import dataclass

@dataclass
class Track:
    path: str
    fade_out: bool
    fade_in: bool
    official: bool
    args: dict[str, str] | None
    offset: float = 0.0

class BaseIMCModule:
    """
    This is not a module to be used but rather a placeholder IMC api to be used in other modules
    """
    def imc(self, imc: 'InterModuleCommunication') -> None:
        """
        Receive an IMC object
        """
        pass
    def imc_data(self, source: 'BaseIMCModule', source_name: str | None, data: object, broadcast: bool) -> object:
        """
        React to IMC data
        """
        return None

class PlayerModule(BaseIMCModule):
    """
    Simple passive observer, this allows you to send the current track the your RDS encoder, or to your website
    """
    def on_new_playlist(self, playlist: list[Track]) -> None:
        """This is called every new playlist"""
        pass
    def on_new_track(self, index: int, track: Track) -> None:
        """
        Called on every track including the ones added by the active modifier, you can check for that comparing the playlists[index] and the track
        """
        pass
    def progress(self, index: int, track: Track, elapsed: float, total: float, real_total: float) -> None:
        """
        Real total and total differ in that, total is how much the track lasts, but real_total will be for how long we will play it for
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
    def advise(self, arguments: str | None) -> str | None:
        """
        Arguments are the arguments passed to the program on startup
        """
        return "/path/to/playlist.txt"
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
    def play(self, index:int, track: Track) -> tuple[Track, bool] | tuple[None, None]:
        """
        Returns a tuple, in the first case where a is the track and b is a bool, b corresponds to whether to extend the playlist, set to true when adding content instead of replacing it
        When None, None is returned then that is treated as a skip, meaning the core will skip this song
        """
        return track, False
    def on_new_playlist(self, playlist: list[Track]) -> None:
        """
        Same behaviour as the basic module function
        """
        pass
class InterModuleCommunication:
    def __init__(self, advisor: PlaylistAdvisor, active_modifier: ActiveModifier | None, simple_modules: list[PlayerModule]) -> None:
        self.advisor = advisor
        self.active_modifier = active_modifier
        self.simple_modules = simple_modules
        self.names_modules: dict[str, BaseIMCModule] = {}
    def broadcast(self, source: BaseIMCModule, data: object) -> None:
        """
        Send data to all modules, other than ourself
        """
        source_name = next((k for k, v in self.names_modules.items() if v is source), None)
        if source is not self.advisor: self.advisor.imc_data(source, source_name, data, True)
        if self.active_modifier and source is not self.active_modifier: self.active_modifier.imc_data(source, source_name, data, True)
        for module in [f for f in self.simple_modules if f is not source]: module.imc_data(source, source_name, data, True)
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
        if not name in self.names_modules.keys(): raise Exception
        return self.names_modules[name].imc_data(source, next((k for k, v in self.names_modules.items() if v is source), None), data, False)