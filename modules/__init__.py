class PlayerModule:
    """
    Simple passive observer, this allows you to send the current track the your RDS encoder, or to your website
    """
    def on_new_playlist(self, playlist: list[tuple[str, bool, bool, bool, dict[str, str]]]):
        """Tuple consists of the track path, to fade out, fade in, official, and args"""
        pass
    def on_new_track(self, index: int, track: str, to_fade_in: bool, to_fade_out: bool, official: bool): pass
class PlaylistModifierModule:
    """
    Playlist modifier, this type of module allows you to shuffle, or put jingles into your playlist
    """
    def modify(self, global_args: dict, playlist: list[tuple[str, bool, bool, bool, dict[str, str]]]): return playlist
class PlaylistAdvisor:
    """
    Only one of a playlist advisor can be loaded. This module picks the playlist file to play, this can be a scheduler or just a static file
    """
    def advise(self, arguments: str | None) -> str: return "/path/to/playlist.txt"
    def new_playlist(self) -> int:
        """
        Whether to play a new playlist, if this is 1, then the player will refresh, if this is two then the player will refresh quietly
        """
        return 0
class ActiveModifier:
    """
    This changes the next song to be played live, which means that this picks the next song, not the playlist, but this is affected by the playlist
    """
    def play(self, index:int, track: tuple[str, bool, bool, bool, dict[str, str]]) -> tuple[tuple[str, bool, bool, bool, dict[str, str]], bool] | tuple[None, None]: return track, False
    def on_new_playlist(self, playlist: list[tuple[str, bool, bool, bool, dict[str, str]]]): pass