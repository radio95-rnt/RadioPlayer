from modules import BaseIMCModule, InterModuleCommunication
from . import ActiveModifier, log95, Track, Path
import os, glob, datetime
from threading import Lock

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
        self.can_limit_tracks = False
        self.morning_start = self.day_end = 0
        self.file_lock = Lock()
        self.crossfade = 5
    def on_new_playlist(self, playlist: list[Track], global_args: dict[str, str]):
        self.playlist = playlist
        self.crossfade = float(global_args.get("crossfade", 5.0))

        if not self._imc: return
        self.limit_tracks, self.morning_start, self.day_end = self._imc.send(self, "advisor", None) # pyright: ignore[reportGeneralTypeIssues]
        self.limit_tracks = not bool(self.limit_tracks)
        if self.limit_tracks: logger.info("Skipping tracks if they bleed into other times.")
        self.can_limit_tracks = self.limit_tracks
    def play(self, index: int, track: Track | None, next_track: Track | None):
        if not track: raise NotImplementedError("This active modifer does not support advisor-less mode")

        if not self.playlist: return (track, next_track), False

        with self.file_lock:
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
 
            if self.last_track: last_track_fade_out = self.last_track.fade_out
            else:
                if (index - 1) >= 0: last_track_fade_out = self.playlist[index - 1].fade_out
                else: last_track_fade_out = 0.0

            if len(songs) != 0: next_track_fade_in = self.crossfade
            else:
                if index + 1 < len(self.playlist) and next_track: next_track_fade_in = next_track.fade_in
                elif not next_track: next_track_fade_in = 0.0
                else: next_track_fade_in = self.crossfade

            if not self.originals or self.originals[-1] != track: self.originals.append(track)

            with self.file_lock:
                with open("/tmp/radioPlayer_toplay", "w") as f:
                    f.write('\n'.join(songs))
                    f.write("\n")

            logger.info(f"Playing {song.name} instead, as instructed by toplay")

            if len(songs):
                # There are more tracks on the temp list
                new_song, new_official = get_song(False)
                self.last_track = Track(song, self.crossfade if new_official else 0, last_track_fade_out, official, {}, focus_time_offset=-self.crossfade if new_official else 0)
                next_track = Track(new_song, self.crossfade if len(songs) else next_track_fade_in, self.crossfade if new_official else 0, new_official, {}, focus_time_offset=-self.crossfade if len(songs) else -next_track_fade_in)
            else:
                self.last_track = Track(song, next_track_fade_in, last_track_fade_out, official, {}, focus_time_offset=-next_track_fade_in)
                next_track = track
            self.limit_tracks = False
            return (self.last_track, next_track), True
        elif len(self.originals):
            self.last_track = self.originals.pop(0)
            if len(self.originals): next_track = self.originals[0]
        else: self.last_track = track
        self.limit_tracks = self.can_limit_tracks

        if self.limit_tracks:
            last_track_duration = self._imc.send(self, "procman", {"op": 1, "arg": self.last_track.path}) # Ask procman for the duration of this file
            assert isinstance(last_track_duration, dict)
            last_track_duration = last_track_duration.get("arg")
            if last_track_duration:
                now = datetime.datetime.now()
                future = datetime.datetime.fromtimestamp(now.timestamp() + last_track_duration)
            if last_track_duration and last_track_duration > 5*60:
                if now.hour < self.morning_start and future.hour >= self.morning_start:
                    logger.warning("Skipping track as it bleeds into the morning")
                    return (None, None), None
                elif now.hour < self.day_end and future.hour >= self.day_end:
                    logger.warning("Skipping track as it bleeds into the night")
                    return (None, None), None
                elif future.day != now.day: # late night goes mid day, as it starts at midnight
                    logger.warning("Skipping track as it the next day")
                    return (None, None), None
                if last_track_duration: logger.info("Track ends at", repr(future))
        return (self.last_track, next_track), False

    def imc(self, imc: InterModuleCommunication) -> None:
        super().imc(imc)
        self._imc.register(self, "activemod")
    def imc_data(self, source: BaseIMCModule, source_name: str | None, data: object, broadcast: bool) -> object:
        if not isinstance(data, dict) or broadcast: return

        if data.get("action") == "add_to_toplay":
            songs_to_add = data.get("songs")
            if isinstance(songs_to_add, list):
                with self.file_lock:
                    with open("/tmp/radioPlayer_toplay", "a") as f:
                        for song_path in songs_to_add: f.write(f"{song_path}\n")
                return {"status": "ok", "message": f"{len(songs_to_add)} songs added."}
        elif data.get("action") == "get_toplay":
            with self.file_lock:
                with open("/tmp/radioPlayer_toplay", "r") as f: return {"status": "ok", "data": [i.strip() for i in f.readlines() if i.strip()]}

activemod = Module()