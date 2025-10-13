class PlaylistAdvisor:
    """
    Only one of a playlist advisor can be loaded. This module picks the playlist file to play, this can be a scheduler or just a static file
    """
    def advise(self, arguments: str | None) -> str: return "/path/to/playlist.txt"
    def new_playlist(self) -> int:
        """
        Whether to play a new playlist, if this is 1, then the player will refresh, if this is two then the player will refresh quietly
        """
        return 0

import os, datetime, log95

logger = log95.log95("ADVISOR")

MORNING_START = 5
MORNING_END = 11
DAY_START = 11
DAY_END = 19
LATE_NIGHT_START = 0
LATE_NIGHT_END = 5

playlist_dir = "/home/user/playlists"

class Time:
    @staticmethod
    def get_playlist_modification_time(playlist_path):
        try: return os.path.getmtime(playlist_path)
        except OSError: return 0

def check_if_playlist_modifed(playlist_path: str):
    current_day, current_hour = datetime.datetime.now().strftime('%A').lower(), datetime.datetime.now().hour
    morning_playlist_path = os.path.join(playlist_dir, current_day, 'morning')
    day_playlist_path = os.path.join(playlist_dir, current_day, 'day')
    night_playlist_path = os.path.join(playlist_dir, current_day, 'night')
    late_night_playlist_path = os.path.join(playlist_dir, current_day, 'late_night')

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

class Module(PlaylistAdvisor):
    def __init__(self) -> None:
        self.last_mod_time = 0
        self.last_playlist = None
        self.custom_playlist = None
    def advise(self, arguments: str | None) -> str:
        if self.custom_playlist: return self.custom_playlist
        if arguments and arguments.startswith("list:"):
            self.custom_playlist = arguments.removeprefix("list:")
            logger.info(f"The list {arguments.split(';')[0]} will be played instead of the daily section lists.")
            return self.custom_playlist
        current_day, current_hour = datetime.datetime.now().strftime('%A').lower(), datetime.datetime.now().hour

        morning_playlist = os.path.join(playlist_dir, current_day, 'morning')
        day_playlist = os.path.join(playlist_dir, current_day, 'day')
        night_playlist = os.path.join(playlist_dir, current_day, 'night')
        late_night_playlist = os.path.join(playlist_dir, current_day, 'late_night')

        morning_dir = os.path.dirname(morning_playlist)
        day_dir = os.path.dirname(day_playlist)
        night_dir = os.path.dirname(night_playlist)
        late_night_dir = os.path.dirname(late_night_playlist)

        for dir_path in [morning_dir, day_dir, night_dir, late_night_dir]:
            if not os.path.exists(dir_path):
                logger.info(f"Creating directory: {dir_path}")
                os.makedirs(dir_path, exist_ok=True)

        for playlist_path in [morning_playlist, day_playlist, night_playlist, late_night_playlist]:
            if not os.path.exists(playlist_path):
                logger.info(f"Creating empty playlist: {playlist_path}")
                with open(playlist_path, 'w'): pass

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
    def new_playlist(self) -> int:
        if self.custom_playlist: return 0
        if not self.last_playlist: return 1
        time_change = check_if_playlist_modifed(self.last_playlist)
        if time_change:  return 2
        mod_time = Time.get_playlist_modification_time(self.last_playlist)
        if mod_time > self.last_mod_time:
            logger.info("Playlist changed on disc, reloading...")
            return 1
        return 0

advisor = Module()