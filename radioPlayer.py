#!/usr/bin/env python3
DEBUG = False
import time, datetime
import os, subprocess, importlib.util
import sys, signal, threading, glob
import unidecode
from dataclasses import dataclass
import log95
from pathlib import Path

class PlayerModule:
    def on_new_playlist(self, playlist: list[tuple[str, bool, bool, bool, dict]]):
        pass
    def on_new_track(self, index: int, track: str, to_fade_in: bool, to_fade_out: bool, official: bool):
        pass
class PlaylistModifierModule:
    def modify(self, global_args: dict, playlist: list[tuple[str, bool, bool, bool, dict]]):
        return playlist

simple_modules: list[PlayerModule] = []
playlist_modifier_modules: list[PlaylistModifierModule] = []

SCRIPT_DIR = Path(__file__).resolve().parent
MODULES_DIR = SCRIPT_DIR / "modules"
MODULES_DIR = MODULES_DIR.resolve()

def print_wait(ttw: float, frequency: float, duration: float=-1, prefix: str="", bias: float = 0):
    interval = 1.0 / frequency
    elapsed = 0.0
    if duration == -1: duration = ttw
    
    def format_time(seconds):
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    
    try:
        while elapsed < ttw:
            print(f"{prefix}{format_time(elapsed+bias)} / {format_time(duration)}", end="\r", flush=True)
            time.sleep(interval)
            elapsed += interval
    except Exception:
        print()
        raise
    
    print(f"{prefix}{format_time(ttw+bias)} / {format_time(duration)}")

MORNING_START = 5
MORNING_END = 11
DAY_START = 11
DAY_END = 19
LATE_NIGHT_START = 0
LATE_NIGHT_END = 5

playlist_dir = "/home/user/playlists"

logger_level = log95.log95Levels.DEBUG if DEBUG else log95.log95Levels.CRITICAL_ERROR
logger = log95.log95("radioPlayer", logger_level)

exit_pending = False
reload_pending = False
intr_time = 0

class Time:
    @staticmethod
    def get_day_hour(): return datetime.datetime.now().strftime('%A').lower(), datetime.datetime.now().hour
    @staticmethod
    def get_playlist_modification_time(playlist_path):
        try: return os.path.getmtime(playlist_path)
        except OSError: return 0

@dataclass
class Process:
    process: subprocess.Popen
    track: str
    started_at: float
    duration: float

class ProcessManager:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.processes: list[Process] = []
    def _get_audio_duration(self, file_path):
        result = subprocess.run(['ffprobe', '-v', 'quiet', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', file_path], capture_output=True, text=True)
        if result.returncode == 0: return float(result.stdout.strip())
        return None
    def play(self, track_path: str, fade_in: bool=False, fade_out: bool=False, fade_time: int = 5) -> Process:
        cmd = ['ffplay', '-nodisp', '-hide_banner', '-autoexit', '-loglevel', 'quiet']
        duration = self._get_audio_duration(track_path)
        if not duration: raise Exception("Failed to get file duration, does it actually exit?", track_path)

        filters = []
        if fade_in: filters.append(f"afade=t=in:st=0:d={fade_time}")
        if fade_out: filters.append(f"afade=t=out:st={duration-fade_time}:d={fade_time}")
        if filters: cmd.extend(['-af', ",".join(filters)])

        cmd.append(track_path)

        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        pr = Process(proc, track_path, time.time(), duration)
        with self.lock: self.processes.append(pr)
        return pr
    def anything_playing(self) -> bool:
        with self.lock:
            self.processes = [p for p in self.processes if p.process.poll() is None]
            return bool(self.processes)
    def stop_all(self, timeout: float | None = None) -> None:
        with self.lock:
            for process in self.processes:
                process.process.terminate()
                try: process.process.wait(timeout)
                except: process.process.kill()
                self.processes.remove(process)
    def wait_all(self, timeout: float | None = None) -> None:
        with self.lock:
            for process in self.processes:
                try: process.process.wait(timeout)
                except: process.process.terminate()
                self.processes.remove(process)

procman = ProcessManager()

def handle_sigint(signum, frame):
    global exit_pending, intr_time
    logger.info("Received SIGINT")
    if (time.time() - intr_time) > 10:
        intr_time = time.time()
        logger.info("Will quit on song end.")
        exit_pending = True
        return
    else:
        logger.warning("Force-Quit pending")
        procman.stop_all()
        exit(0)

def handle_sighup(signum, frame):
    global reload_pending
    reload_pending = True

signal.signal(signal.SIGINT, handle_sigint)
signal.signal(signal.SIGHUP, handle_sighup) # type: ignore

def load_filelines(path):
    try:
        with open(path, 'r') as f: return [unidecode.unidecode(line.strip()) for line in f.readlines() if unidecode.unidecode(line.strip())]
    except FileNotFoundError:
        logger.error(f"Playlist not found: {path}")
        return []

def check_if_playlist_modifed(playlist_path: str, custom_playlist: bool = False):
    current_day, current_hour = Time.get_day_hour()
    morning_playlist_path = os.path.join(playlist_dir, current_day, 'morning')
    day_playlist_path = os.path.join(playlist_dir, current_day, 'day')
    night_playlist_path = os.path.join(playlist_dir, current_day, 'night')
    late_night_playlist_path = os.path.join(playlist_dir, current_day, 'late_night')

    if DAY_START <= current_hour < DAY_END and not custom_playlist:
        if playlist_path != day_playlist_path:
            logger.info("Time changed to day hours, switching playlist...")
            return True
    elif MORNING_START <= current_hour < MORNING_END and not custom_playlist:
        if playlist_path != morning_playlist_path:
            logger.info("Time changed to morning hours, switching playlist...")
            return True
    elif LATE_NIGHT_START <= current_hour < LATE_NIGHT_END and not custom_playlist:
        if playlist_path != late_night_playlist_path:
            logger.info("Time changed to late night hours, switching playlist...")
            return True
    else:
        if playlist_path != night_playlist_path and not custom_playlist:
            logger.info("Time changed to night hours, switching playlist...")
            return True

def parse_playlistfile(playlist_path: str):
    parser_log = log95.log95("PARSER", logger_level)

    parser_log.debug("Reading", playlist_path)
    lines = load_filelines(playlist_path)
    def check_for_imports(lines: list[str], seen=None) -> list[str]:
        nonlocal parser_log
        if seen is None: seen = set()
        out = []
        for line in lines:
            if line.startswith("@"):
                target = line.removeprefix("@")
                if target not in seen:
                    parser_log.debug("Importing", target)
                    seen.add(target)
                    sub_lines = load_filelines(target)
                    out.extend(check_for_imports(sub_lines, seen))
            else: out.append(line)
        return out
    lines = check_for_imports(lines) # First, import everything

    out = []
    global_arguments = {}
    for line in lines:
        arguments = {}
        if line.startswith(";") or not line.strip(): continue
        if "|" in line:
            if line.startswith("|"): # No file name, we're defining global arguments
                args = line.removeprefix("|").split(";")
                for arg in args:
                    key, val = arg.split("=", 1)
                    global_arguments[key] = val
            else:
                line, args = line.split("|", 1)
                args = args.split(";")
                for arg in args:
                    key, val = arg.split("=", 1)
                    arguments[key] = val
        parser_log.debug("Line:", line, "| Global Args:", repr(global_arguments), "| Local args:", repr(arguments))
        out.append(([f for f in glob.glob(line) if os.path.isfile(f)], arguments))
    return global_arguments, out

def play_playlist(playlist_path, custom_playlist: bool=False):
    procman.stop_all(1)
    last_modified_time = Time.get_playlist_modification_time(playlist_path)
    
    try:
        global_args, parsed = parse_playlistfile(playlist_path)
    except Exception:
        logger.info(f"Exception while parsing playlist, retrying in 15 seconds...")
        time.sleep(15)
        return

    playlist: list[tuple[str, bool, bool, bool, dict]] = [] # name, fade in, fade out, official, args
    for (lns, args) in parsed:
        lns: list[str]
        args: dict[str, str]
        for line in lns: playlist.append((line, True, True, True, args)) # simple entry, just to convert to a format taken by the modules

    for module in playlist_modifier_modules: playlist = module.modify(global_args, playlist)

    for module in simple_modules: module.on_new_playlist(playlist)

    return_pending = False

    cross_fade = int(global_args.get("crossfade", 5))
    
    for i, (track, to_fade_in, to_fade_out, official, args) in enumerate(playlist):
        if exit_pending:
            logger.info("Quit received, waiting for song end.")
            procman.wait_all(cross_fade)
            exit()
        elif reload_pending:
            logger.info("Reload requested, restarting with new arguments after song ending")
            procman.wait_all(cross_fade)
            return "reload"
        elif return_pending:
            logger.info("Return reached, next song will reload the playlist.")
            procman.wait_all(cross_fade)
            return
        track_path = os.path.abspath(os.path.expanduser(track))
        for module in simple_modules: module.on_new_track(i, track_path, to_fade_in, to_fade_out, official)
        track_name = os.path.basename(track_path)

        current_modified_time = Time.get_playlist_modification_time(playlist_path)
        if current_modified_time > last_modified_time:
            logger.info(f"Playlist {playlist_path} has been modified, reloading...")
            return_pending = True
            continue

        return_pending = check_if_playlist_modifed(playlist_path, custom_playlist)
        if return_pending and not procman.anything_playing(): continue

        logger.info(f"Now playing: {track_name}")
        if (i + 1) < len(playlist): logger.info(f"Next up: {os.path.basename(playlist[i+1][0])}")
        
        pr = procman.play(track_path, to_fade_in, to_fade_out)
        ttw = pr.duration
        if to_fade_out: ttw -= cross_fade
        if official: print_wait(ttw, 1, pr.duration, f"{track_name}: ")
        else: time.sleep(ttw)

def can_delete_file(filepath):
    if not os.path.isfile(filepath): return False
    directory = os.path.dirname(os.path.abspath(filepath)) or '.'
    return os.access(directory, os.W_OK | os.X_OK)

def parse_arguments():
    """Parse command line arguments and return configuration"""
    arg = sys.argv[1] if len(sys.argv) > 1 else None
    selected_list = None

    if arg:
        if arg.lower() == "-h":
            print("Control files:")
            print("    Note: All of these files are one-time only, after they have been acked by the player they will be deleted")
            print("   /tmp/radioPlayer_arg           -   Contains arguments to use")
            print()
            print("Arguments:")
            print("    list:playlist;options    -    Play custom playlist with options")
            print()
            exit(0)

    if can_delete_file("/tmp/radioPlayer_arg"):
        with open("/tmp/radioPlayer_arg", "r") as f: arg = f.read().strip()
        os.remove("/tmp/radioPlayer_arg")

    if arg:
        if arg.startswith("list:"):
            selected_list = arg.removeprefix("list:")
            logger.info(f"The list {selected_list.split(';')[0]} will be played instead of the daily section lists.")
        else: logger.error(f"Invalid argument or file not found: {arg}")

    return selected_list

def main():
    for filename in os.listdir(MODULES_DIR):
        if filename.endswith(".py") and filename != "__init__.py":
            module_name = filename[:-3]
            module_path = MODULES_DIR / filename
            
            # Load module from file path directly
            spec = importlib.util.spec_from_file_location(module_name, module_path)
            if not spec: continue
            module = importlib.util.module_from_spec(spec)
            if not spec.loader: continue
            spec.loader.exec_module(module)
            
            if md := getattr(module, "module", None):
                simple_modules.append(md)
            elif md := getattr(module, "playlistmod", None):
                if isinstance(md, tuple):
                    md, index = md
                    playlist_modifier_modules.insert(index, md)
                else: playlist_modifier_modules.append(md)
    
    try:
        while True:
            selected_list = parse_arguments()

            play_loop = True
            while play_loop:
                if selected_list:
                    logger.info("Playing custom list")
                    result = play_playlist(selected_list, True)
                    if result == "reload": play_loop = False
                    continue

                current_day, current_hour = Time.get_day_hour()

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
                    result = play_playlist(day_playlist, False)
                elif MORNING_START <= current_hour < MORNING_END:
                    logger.info(f"Playing {current_day} morning playlist...")
                    result = play_playlist(morning_playlist, False)
                elif LATE_NIGHT_START <= current_hour < LATE_NIGHT_END:
                    logger.info(f"Playing {current_day} late_night playlist...")
                    result = play_playlist(late_night_playlist, False)
                else:
                    logger.info(f"Playing {current_day} night playlist...")
                    result = play_playlist(night_playlist, False)

                if exit_pending: exit()
                elif reload_pending:
                    logger.info("Reload requested, restarting with new arguments...")
                    result = "reload"

                if result == "reload": play_loop = False
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        procman.stop_all()
        raise
    finally: procman.stop_all()
