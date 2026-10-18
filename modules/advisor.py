MORNING_START = 5
MORNING_END = 10
DAY_START = 10
DAY_END = 19
LATE_NIGHT_START = 0
LATE_NIGHT_END = 5

from . import BaseIMCModule, InterModuleCommunication, PlaylistAdvisor, log95, Path
import os, datetime

from typing import TextIO
_log_out: TextIO

assert _log_out # pyright: ignore[reportUnboundVariable]
logger = log95.log95("ADVISOR", output=_log_out)

playlist_dir = Path("/mnt/mixes/.playlist")

class Time:
    @staticmethod
    def get_playlist_modification_time(playlist_path) -> float:
        try: return os.path.getmtime(playlist_path)
        except OSError: return 0

MONTHS = ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec")

def get_day_dir(now: datetime.datetime) -> tuple[Path, str]:
    """
    Returns (directory, label) for today.
    Uses playlist_dir/mon/DD if that folder exists, otherwise playlist_dir/weekday.
    """
    # Fixed month names instead of strftime('%b'), so it doesn't depend on the system locale
    special_label = f"{MONTHS[now.month - 1]}/{now.day:02d}"
    special = Path(playlist_dir, MONTHS[now.month - 1], f"{now.day:02d}")
    if special.is_dir(): return special.absolute(), special_label

    weekday = now.strftime('%A').lower()
    return Path(playlist_dir, weekday).absolute(), weekday

def check_if_playlist_modifed(playlist_path: Path) -> bool:
    time = datetime.datetime.now()
    current_hour = time.hour
    day_dir, _ = get_day_dir(time)

    if DAY_START <= current_hour < DAY_END:
        name, label = "day", "day"
    elif MORNING_START <= current_hour < MORNING_END:
        name, label = "morning", "morning"
    elif LATE_NIGHT_START <= current_hour < LATE_NIGHT_END:
        name, label = "late_night", "late night"
    else:
        name, label = "night", "night"

    if playlist_path != Path(day_dir, name).absolute():
        logger.info(f"Time changed to {label} hours, switching playlist...")
        return True
    return False

class Module(PlaylistAdvisor):
    def __init__(self) -> None:
        self.last_mod_time = 0
        self.last_playlist = None

        self.custom_playlist = None
        self.custom_playlist_path = Path("/tmp/radioPlayer_list")
        self.custom_playlist_last_mod = 0
    def advise(self, arguments: str | None) -> Path:
        if self.custom_playlist: return self.custom_playlist

        if self.custom_playlist_path.exists():
            self.last_playlist = self.custom_playlist_path
            self.custom_playlist = self.last_playlist
            self.custom_playlist_last_mod = Time.get_playlist_modification_time(self.custom_playlist)
            return self.custom_playlist
        elif self.custom_playlist: self.custom_playlist = None

        time = datetime.datetime.now()
        current_hour = time.hour
        day_dir, current_day = get_day_dir(time)

        morning_playlist = Path(day_dir, "morning").absolute()
        day_playlist = Path(day_dir, "day").absolute()
        night_playlist = Path(day_dir, "night").absolute()
        late_night_playlist = Path(day_dir, "late_night").absolute()

        if not day_dir.exists():
            logger.info(f"Creating directory: {day_dir}")
            day_dir.mkdir(exist_ok=True)

        for playlist_path in [morning_playlist, day_playlist, night_playlist, late_night_playlist]:
            if not playlist_path.exists():
                logger.info(f"Creating empty playlist: {playlist_path}")
                playlist_path.touch()

        if DAY_START <= current_hour < DAY_END:
            logger.info(f"Playing {current_day} day playlist...")
            self.last_mod_time = Time.get_playlist_modification_time(day_playlist)
            self.last_playlist = day_playlist
        elif MORNING_START <= current_hour < MORNING_END:
            logger.info(f"Playing {current_day} morning playlist...")
            self.last_mod_time = Time.get_playlist_modification_time(morning_playlist)
            self.last_playlist = morning_playlist
        elif LATE_NIGHT_START <= current_hour < LATE_NIGHT_END:
            logger.info(f"Playing {current_day} late night playlist...")
            self.last_mod_time = Time.get_playlist_modification_time(late_night_playlist)
            self.last_playlist = late_night_playlist
        else:
            logger.info(f"Playing {current_day} night playlist...")
            self.last_mod_time = Time.get_playlist_modification_time(night_playlist)
            self.last_playlist = night_playlist
        if self._imc: self._imc.send(self, "web", {"playlist": str(self.last_playlist)}, False)
        return self.last_playlist
    def new_playlist(self) -> bool:
        if self.custom_playlist and self.custom_playlist_path.exists():
            if Time.get_playlist_modification_time(self.custom_playlist) > self.custom_playlist_last_mod:
                logger.info("Custom playlist changed on disc, reloading...")
                self.custom_playlist = None
                return True
            return False
        elif self.custom_playlist_path.exists(): return True

        if not self.last_playlist: return True

        reload_state = (playlist_dir / "reload")
        if reload_state.exists():
            reload_state.unlink(True)
            return True

        if check_if_playlist_modifed(self.last_playlist): return True
        if Time.get_playlist_modification_time(self.last_playlist) > self.last_mod_time:
            logger.info("Playlist changed on disc, reloading...")
            return True
        return False
    def imc(self, imc: InterModuleCommunication) -> None:
        self._imc = imc
        imc.register(self, "advisor")
    def imc_data(self, source: BaseIMCModule, source_name: str | None, data: object, broadcast: bool):
        if broadcast: return
        return (self.custom_playlist, MORNING_START, DAY_END)

advisor = Module()

# This is free and unencumbered software released into the public domain.

# Anyone is free to copy, modify, publish, use, compile, sell, or
# distribute this software, either in source code form or as a compiled
# binary, for any purpose, commercial or non-commercial, and by any
# means.

# In jurisdictions that recognize copyright laws, the author or authors
# of this software dedicate any and all copyright interest in the
# software to the public domain. We make this dedication for the benefit
# of the public at large and to the detriment of our heirs and
# successors. We intend this dedication to be an overt act of
# relinquishment in perpetuity of all present and future rights to this
# software under copyright law.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
# IN NO EVENT SHALL THE AUTHORS BE LIABLE FOR ANY CLAIM, DAMAGES OR
# OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE,
# ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR
# OTHER DEALINGS IN THE SOFTWARE.

# For more information, please refer to <https://unlicense.org>
