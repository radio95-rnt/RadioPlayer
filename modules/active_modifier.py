from . import ActiveModifier, log95, Track, InterModuleCommunication
import os, glob, datetime

from .advisor import MORNING_START, DAY_END

logger = log95.log95("AC-MOD")

class Module(ActiveModifier):
    def __init__(self) -> None:
        self.playlist = None
        self.originals = []
        self.last_track = None
        self.limit_tracks = True
    def on_new_playlist(self, playlist: list[Track]):
        self.playlist = playlist

        if not self._imc: return
        self.limit_tracks = bool(self._imc.send(self, "advisor", None))
    def play(self, index: int, track: Track):
        if not self.playlist: return track
        if not os.path.exists("/tmp/radioPlayer_toplay"): open("/tmp/radioPlayer_toplay", "a").close()
        with open("/tmp/radioPlayer_toplay", "r") as f: songs = [s.strip() for s in f.readlines() if s.strip()]

        songs[:] = [f for s in songs for f in glob.glob(s) if os.path.isfile(f)] # expand glob

        if len(songs):
            song = songs.pop(0)

            if self.last_track:
                last_track_to_fade_out = self.last_track.fade_out
            else:
                if (index - 1) >= 0:
                    last_track_to_fade_out = self.playlist[index - 1].fade_out
                else: last_track_to_fade_out = False
            
            if len(songs) != 0:
                next_track_to_fade_in = True
            else:
                if index + 1 < len(self.playlist):
                    next_track_to_fade_in = self.playlist[index + 1].fade_in
                else:
                    next_track_to_fade_in = True

            if not self.originals or self.originals[-1] != track: self.originals.append(track)

            with open("/tmp/radioPlayer_toplay", "w") as f: 
                f.write('\n'.join(songs))
                f.write("\n")

            logger.info(f"Playing {song} instead, as instructed by toplay")

            self.last_track = Track(song, next_track_to_fade_in, last_track_to_fade_out, True, {})
            return self.last_track, True
        elif len(self.originals): self.last_track = self.originals.pop(0)
        else: self.last_track = track

        if self.limit_tracks:
            last_track_duration = self._imc.send(self, "procman", {"op": 1, "arg": self.last_track.path})
            assert isinstance(last_track_duration, dict)
            last_track_duration = last_track_duration.get("arg")

            if last_track_duration and last_track_duration > 5*60:
                now = datetime.datetime.now()
                future = datetime.datetime.fromtimestamp(now.timestamp() + last_track_duration)
                if now.hour < MORNING_START and future.hour > MORNING_START:
                    logger.warning("Skipping track as it bleeds into the morning")
                    return None, None
                elif now.hour < DAY_END and future.hour > DAY_END:
                    logger.warning("Skipping track as it bleeds into the night")
                    return None, None
                elif future.day > now.day: # late night goes mid day, as it starts at midnight
                    logger.warning("Skipping track as it the next day")
                    return None, None

        return self.last_track, False

activemod = Module()