import random

from . import PlaylistModifierModule, Track

class Module(PlaylistModifierModule):
    def modify(self, global_args: dict, playlist: list[Track]):
        if int(global_args.get("no_shuffle", 0)) == 0: random.shuffle(playlist)
        return playlist

playlistmod = (Module(), 0)