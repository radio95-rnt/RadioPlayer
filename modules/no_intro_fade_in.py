from . import PlaylistModifierModule, Track

class Module(PlaylistModifierModule):
    def modify(self, global_args: dict, playlist: list[Track]) -> list[Track] | None:
        playlist[0].fade_in = 0
        return playlist

playlistmod = Module(), -1
