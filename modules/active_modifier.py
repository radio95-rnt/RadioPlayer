from . import ActiveModifier, log95, Track, Path
import os, glob, datetime

from typing import TextIO
_log_out: TextIO

assert _log_out # pyright: ignore[reportUnboundVariable]
logger = log95.log95("AC-MOD", output=_log_out)

class Module(ActiveModifier):
    def __init__(self) -> None:
        self.playlist = None
        self.originals = []
        self.last_track = None
        self.limit_tracks = False
        self.morning_start = self.day_end = 0
    def on_new_playlist(self, playlist: list[Track]):
        self.playlist = playlist

        if not self._imc: return
        self.limit_tracks, self.morning_start, self.day_end = self._imc.send(self, "advisor", None) # pyright: ignore[reportGeneralTypeIssues]
        self.limit_tracks = not bool(self.limit_tracks)
    def play(self, index: int, track: Track, next_track: Track | None):
        if not self.playlist: return (track, next_track), False
        if not os.path.exists("/tmp/radioPlayer_toplay"): open("/tmp/radioPlayer_toplay", "a").close()
        with open("/tmp/radioPlayer_toplay", "r") as f: songs = [s.strip() for s in f.readlines() if s.strip()]

        songs[:] = [f for s in songs for f in glob.glob(s) if os.path.isfile(f)] # expand glob

        def get_song(pop: bool = True):
            nonlocal songs
            if pop: song = songs.pop(0)
            else: song = songs[0]
            official = True
            if song.startswith("!"):
                song = song[1:]
                official = False
            
            return Path(song).absolute(), official

        if len(songs):
            song, official = get_song()

            if self.last_track: last_track_to_fade_out = self.last_track.fade_out
            else:
                if (index - 1) >= 0: last_track_to_fade_out = self.playlist[index - 1].fade_out
                else: last_track_to_fade_out = False
            
            if len(songs) != 0: next_track_to_fade_in = True
            else:
                if index + 1 < len(self.playlist) and next_track: next_track_to_fade_in = next_track.fade_in
                elif not next_track: next_track_to_fade_in = False
                else: next_track_to_fade_in = True

            if not self.originals or self.originals[-1] != track: self.originals.append(track)

            with open("/tmp/radioPlayer_toplay", "w") as f: 
                f.write('\n'.join(songs))
                f.write("\n")

            logger.info(f"Playing {song.name} instead, as instructed by toplay")

            if len(songs):
                # There are more tracks on the temp list
                new_song, new_official = get_song(False)
                self.last_track = Track(song, new_official, last_track_to_fade_out, official, {})
                next_track = Track(new_song, new_official if len(songs) else next_track_to_fade_in, new_official, new_official, {})
            else:
                self.last_track = Track(song, next_track_to_fade_in, last_track_to_fade_out, official, {})
                next_track = track
            return (self.last_track, next_track), True
        elif len(self.originals): 
            self.last_track = self.originals.pop(0)
            if len(self.originals): next_track = self.originals[0]
        else: self.last_track = track

        if self.limit_tracks:
            last_track_duration = self._imc.send(self, "procman", {"op": 1, "arg": self.last_track.path})
            assert isinstance(last_track_duration, dict)
            last_track_duration = last_track_duration.get("arg")

            if last_track_duration and last_track_duration > 5*60:
                now = datetime.datetime.now()
                future = datetime.datetime.fromtimestamp(now.timestamp() + last_track_duration)
                if now.hour < self.morning_start and future.hour > self.morning_start:
                    logger.warning("Skipping track as it bleeds into the morning")
                    return (None, None), None
                elif now.hour < self.day_end and future.hour > self.day_end:
                    logger.warning("Skipping track as it bleeds into the night")
                    return (None, None), None
                elif future.day > now.day: # late night goes mid day, as it starts at midnight
                    logger.warning("Skipping track as it the next day")
                    return (None, None), None
                logger.info("Track ends at", repr(future))
        return (self.last_track, next_track), False

activemod = Module()