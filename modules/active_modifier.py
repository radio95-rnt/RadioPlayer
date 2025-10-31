from modules import InterModuleCommunication
from . import ActiveModifier, log95, Track
import os
import subprocess
import datetime

from .advisor import MORNING_START, DAY_END

def get_audio_duration(file_path):
    result = subprocess.run(['ffprobe', '-v', 'quiet', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', file_path], capture_output=True, text=True)
    if result.returncode == 0: return float(result.stdout.strip())
    return None

logger = log95.log95("AC-MOD")

class Module(ActiveModifier):
    def __init__(self) -> None:
        self.playlist = None
        self.originals = []
        self.last_track = None
        self.limit_tracks = True
        self.imc_class = None
    def on_new_playlist(self, playlist: list[Track]):
        self.playlist = playlist

        if not self.imc_class: return
        self.limit_tracks = bool(self.imc_class.send(self, "advisor", None))
    def play(self, index: int, track: Track):
        if not self.playlist: return track
        if not os.path.exists("/tmp/radioPlayer_toplay"): open("/tmp/radioPlayer_toplay", "a").close()
        with open("/tmp/radioPlayer_toplay", "r") as f: songs = [s.strip() for s in f.readlines() if s.strip()]
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
                f.write("\n") # extra

            logger.info(f"Playing {song} instead, as instructed by toplay")

            self.last_track = Track(song, next_track_to_fade_in, last_track_to_fade_out, True, {})
            return self.last_track, True
        elif len(self.originals): self.last_track = self.originals.pop(0)
        else: self.last_track = track

        if self.limit_tracks:
            last_track_duration = get_audio_duration(self.last_track.path)
            if last_track_duration and last_track_duration > 5*60:
                now = datetime.datetime.now()
                timestamp = now.timestamp() + last_track_duration
                future = datetime.datetime.fromtimestamp(timestamp)
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
    
    def imc(self, imc: InterModuleCommunication):
        self.imc_class = imc

activemod = Module()