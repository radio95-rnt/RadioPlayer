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

class PlayerModule:
    """
    Simple passive observer, this allows you to send the current track the your RDS encoder, or to your website
    """
    def on_new_playlist(self, playlist: list[Track]):
        """This is called every new playlist"""
        pass
    def on_new_track(self, index: int, track: Track):
        """
        Called on every track including the ones added by the active modifier, you can check for that comparing the playlists[index] and the track
        """
        pass
    def imc(self, imc: 'InterModuleCommunication'):
        """
        Receive an IMC object
        """
        pass
    def imc_data(self, source: 'PlayerModule | ActiveModifier | PlaylistAdvisor', data: object, broadcast: bool) -> object:
        return None
    def progess(self, index: int, track: Track, elapsed: float, total: float):
        pass
class PlaylistModifierModule:
    """
    Playlist modifier, this type of module allows you to shuffle, or put jingles into your playlist
    """
    def modify(self, global_args: dict, playlist: list[Track]):
        """
        global_args are playlist global args (see radioPlayer_playlist_file.txt)
        """
        return playlist
    # No IMC, as we only run on new playlists
class PlaylistAdvisor:
    """
    Only one of a playlist advisor can be loaded. This module picks the playlist file to play, this can be a scheduler or just a static file
    """
    def advise(self, arguments: str | None) -> str:
        """
        Arguments are the arguments passed to the program on startup
        """
        return "/path/to/playlist.txt"
    def new_playlist(self) -> bool:
        """
        Whether to play a new playlist, if this is True, then the player will refresh and fetch a new playlist, calling advise
        """
        return False
    def imc(self, imc: 'InterModuleCommunication'):
        """
        Receive an IMC object
        """
        pass
    def imc_data(self, source: 'PlayerModule | ActiveModifier | PlaylistAdvisor', data: object, broadcast: bool) -> object:
        return None
class ActiveModifier:
    """
    This changes the next song to be played live, which means that this picks the next song, not the playlist, but this is affected by the playlist
    """
    def arguments(self, arguments: str | None):
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
    def on_new_playlist(self, playlist: list[Track]):
        """
        Same behaviour as the basic module function
        """
        pass
    def imc(self, imc: 'InterModuleCommunication'):
        """
        Receive an IMC object
        """
        pass
    def imc_data(self, source: 'PlayerModule | ActiveModifier | PlaylistAdvisor', data: object, broadcast: bool) -> object:
        return None
class InterModuleCommunication:
    def __init__(self, advisor: PlaylistAdvisor, active_modifier: ActiveModifier | None, simple_modules: list[PlayerModule]) -> None:
        self.advisor = advisor
        self.active_modifier = active_modifier
        self.simple_modules = simple_modules
        self.names_modules: dict[str, PlaylistAdvisor | ActiveModifier | PlayerModule] = {}
    def broadcast(self, source: PlaylistAdvisor | ActiveModifier | PlayerModule, data: object) -> None:
        """
        Send data to all modules, other than ourself
        """
        if source is not self.advisor: self.advisor.imc_data(source, data, True)
        if self.active_modifier and source is not self.active_modifier: self.active_modifier.imc_data(source, data, True)
        for module in [f for f in self.simple_modules if f is not source]: module.imc_data(source, data, True)
    def register(self, module: PlaylistAdvisor | ActiveModifier | PlayerModule, name: str):
        if name in self.names_modules.keys(): return False
        self.names_modules[name] = module
        return True
    def send(self, source: PlaylistAdvisor | ActiveModifier | PlayerModule, name: str, data: object) -> object:
        if not name in self.names_modules.keys(): raise Exception
        return self.names_modules[name].imc_data(source, data, False)