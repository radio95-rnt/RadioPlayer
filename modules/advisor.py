from modules import ActiveModifier, InterModuleCommunication, PlayerModule
from . import PlaylistAdvisor, log95, Path
import os, datetime

from typing import TextIO
_log_file: TextIO

assert _log_file # pyright: ignore[reportUnboundVariable]
logger = log95.log95("ADVISOR", output=_log_file)

MORNING_START = 5
MORNING_END = 10
DAY_START = 10
DAY_END = 18
LATE_NIGHT_START = 0
LATE_NIGHT_END = 5

playlist_dir = Path("/home/user/playlists")

class Time:
    @staticmethod
    def get_playlist_modification_time(playlist_path) -> float:
        try: return os.path.getmtime(playlist_path)
        except OSError: return 0

def check_if_playlist_modifed(playlist_path: Path) -> bool:
    current_day, current_hour = datetime.datetime.now().strftime('%A').lower(), datetime.datetime.now().hour
    morning_playlist_path = Path(playlist_dir, current_day, "morning").absolute()
    day_playlist_path = Path(playlist_dir, current_day, "day").absolute()
    night_playlist_path = Path(playlist_dir, current_day, "night").absolute()
    late_night_playlist_path = Path(playlist_dir, current_day, "late_night").absolute()

    if DAY_START <= current_hour < DAY_END:
        if playlist_path != day_playlist_path:
            logger.info("Time changed to day hours, switching playlist...")
            return True
    elif MORNING_START <= current_hour < MORNING_END:
        if playlist_path != morning_playlist_path:
            logger.info("Time changed to morning hours, switching playlist...")
            return True
    elif LATE_NIGHT_START <= current_hour < LATE_NIGHT_END:
        if playlist_path != late_night_playlist_path:
            logger.info("Time changed to late night hours, switching playlist...")
            return True
    else:
        if playlist_path != night_playlist_path:
            logger.info("Time changed to night hours, switching playlist...")
            return True
    return False

class Module(PlaylistAdvisor):
    def __init__(self) -> None:
        self.last_mod_time = 0
        self.last_playlist = None
        self.class_imc = None
        self.custom_playlist = None
        self.custom_playlist_path = Path("/tmp/radioPlayer_list")
    def advise(self, arguments: str | None) -> Path:
        if self.custom_playlist: return self.custom_playlist

        if self.custom_playlist_path.exists():
            self.last_playlist = self.custom_playlist_path
            self.custom_playlist = self.last_playlist
            return self.custom_playlist
        elif self.custom_playlist: self.custom_playlist = None
        
        current_day, current_hour = datetime.datetime.now().strftime('%A').lower(), datetime.datetime.now().hour

        morning_playlist = Path(playlist_dir, current_day, "morning").absolute()
        day_playlist = Path(playlist_dir, current_day, "day").absolute()
        night_playlist = Path(playlist_dir, current_day, "night").absolute()
        late_night_playlist = Path(playlist_dir, current_day, "late_night").absolute()

        morning_dir = morning_playlist.parent
        day_dir = day_playlist.parent
        night_dir = night_playlist.parent
        late_night_dir = late_night_playlist.parent

        for dir_path in [morning_dir, day_dir, night_dir, late_night_dir]:
            if not dir_path.exists():
                logger.info(f"Creating directory: {dir_path}")
                dir_path.mkdir(exist_ok=True)

        for playlist_path in [morning_playlist, day_playlist, night_playlist, late_night_playlist]:
            if not playlist_path.exists():
                logger.info(f"Creating empty playlist: {playlist_path}")
                playlist_path.touch()

        if DAY_START <= current_hour < DAY_END:
            logger.info(f"Playing {current_day} day playlist...")
            self.last_mod_time = Time.get_playlist_modification_time(day_playlist)
            self.last_playlist = day_playlist
            return day_playlist
        elif MORNING_START <= current_hour < MORNING_END:
            logger.info(f"Playing {current_day} morning playlist...")
            self.last_mod_time = Time.get_playlist_modification_time(morning_playlist)
            self.last_playlist = morning_playlist
            return morning_playlist
        elif LATE_NIGHT_START <= current_hour < LATE_NIGHT_END:
            logger.info(f"Playing {current_day} late_night playlist...")
            self.last_mod_time = Time.get_playlist_modification_time(late_night_playlist)
            self.last_playlist = late_night_playlist
            return late_night_playlist
        else:
            logger.info(f"Playing {current_day} night playlist...")
            self.last_mod_time = Time.get_playlist_modification_time(night_playlist)
            self.last_playlist = night_playlist
            return night_playlist
    def new_playlist(self) -> bool:
        if self.custom_playlist and self.custom_playlist_path.exists(): return False
        if not self.last_playlist: return True
        if check_if_playlist_modifed(self.last_playlist): return True
        mod_time = Time.get_playlist_modification_time(self.last_playlist)
        if mod_time > self.last_mod_time:
            logger.info("Playlist changed on disc, reloading...")
            return True
        return False
    def imc(self, imc: InterModuleCommunication) -> None:
        self.class_imc = imc
        imc.register(self, "advisor")
    def imc_data(self, source: PlayerModule | ActiveModifier | PlaylistAdvisor, source_name: str | None, data: object, broadcast: bool):
        return self.custom_playlist

advisor = Module()