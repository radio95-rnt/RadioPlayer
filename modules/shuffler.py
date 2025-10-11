import random

class PlaylistModifierModule:
    def modify(self, global_args: dict, playlist: list[tuple[str, bool, bool, bool, dict]]):
        return playlist

class Module(PlaylistModifierModule):
    def modify(self, global_args: dict, playlist: list[tuple[str, bool, bool, bool, dict]]):
        if int(global_args.get("no_shuffle", 0)) == 0:
            random.shuffle(playlist)
        return playlist

playlistmod = (Module(), 0)