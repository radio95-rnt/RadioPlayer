import random, log95

logger = log95.log95("SHUFFLER")

class PlaylistModifierModule:
    def modify(self, global_args: dict, playlist: list[tuple[str, bool, bool, bool, dict]]):
        return playlist

class Module(PlaylistModifierModule):
    def __init__(self) -> None:
        logger.info("Shuffling with the following random state:", repr(random.getstate()))
    def modify(self, global_args: dict, playlist: list[tuple[str, bool, bool, bool, dict]]):
        if int(global_args.get("no_shuffle", 0)) == 0:
            random.shuffle(playlist)
        return playlist

playlistmod = (Module(), 0)