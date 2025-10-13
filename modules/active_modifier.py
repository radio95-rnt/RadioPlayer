class ActiveModifier:
    """
    This changes the next song to be played live, which means that this picks the next song, not the playlist, but this is affected by the playlist
    """
    """Tuple consists of the track path, to fade out, fade in, official, and args"""
    def play(self, index: int, track: tuple[str, bool, bool, bool, dict[str, str]]): return track, False
    def on_new_playlist(self, playlist: list[tuple[str, bool, bool, bool, dict[str, str]]]): pass

import os, log95

logger = log95.log95("AC-MOD")

class Module(ActiveModifier):
    def __init__(self) -> None:
        self.playlist = None
        self.originals = []
    def on_new_playlist(self, playlist: list[tuple[str, bool, bool, bool, dict[str, str]]]):
        self.playlist = playlist
    def play(self, index: int, track: tuple[str, bool, bool, bool, dict[str, str]]):
        if not self.playlist: return track
        if not os.path.exists("/tmp/radioPlayer_toplay"): open("/tmp/radioPlayer_toplay", "a").close()
        with open("/tmp/radioPlayer_toplay", "r") as f:
            songs = [s.strip() for s in f.readlines() if s.strip()]
        if len(songs):
            song = songs.pop(0)

            if (index - 1) >= 0:
                _, last_track_to_fade_out, _, _, _ = self.playlist[index - 1]
            else: last_track_to_fade_out = False
            
            if index + 1 < len(self.playlist):
                _, _, next_track_to_fade_in, _, _ = self.playlist[index + 1]
            else:
                next_track_to_fade_in = False

            self.originals.append(track)

            with open("/tmp/radioPlayer_toplay", "w") as f: f.write('\n'.join(songs))

            logger.info(f"Playing {song} instead, as instructed by toplay")

            return song, last_track_to_fade_out, next_track_to_fade_in, True, {}
        elif len(self.originals):
            return self.originals.pop(0)
        return track

activemod = Module()