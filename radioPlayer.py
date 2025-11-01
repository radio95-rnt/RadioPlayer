#!/usr/bin/env python3
DEBUG = False
import time
import os, subprocess, importlib.util, types
import sys, signal, threading, glob
import libcache
from pathlib import Path
from modules import *

simple_modules: list[PlayerModule] = []
playlist_modifier_modules: list[PlaylistModifierModule] = []
playlist_advisor: PlaylistAdvisor | None = None
active_modifier: ActiveModifier | None = None

MODULES_PACKAGE = "modules"
MODULES_DIR = (Path(__file__).resolve().parent / MODULES_PACKAGE).resolve()

logger_level = log95.log95Levels.DEBUG if DEBUG else log95.log95Levels.CRITICAL_ERROR
logger = log95.log95("CORE", logger_level)

exit_pending = False
intr_time = 0
exit_lock = threading.Lock()

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
        self.duration_cache = libcache.Cache()
    def _get_audio_duration(self, file_path):
        if result := self.duration_cache.getElement(file_path, False):
            return result
        
        result = subprocess.run(['ffprobe', '-v', 'quiet', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', file_path], capture_output=True, text=True)
        if result.returncode == 0: 
            result = float(result.stdout.strip())
            self.duration_cache.saveElement(file_path, result, (60*60))
            return result
        return None
    def play(self, track_path: str, fade_in: bool=False, fade_out: bool=False, fade_time: int = 5) -> Process:
        cmd = ['ffplay', '-nodisp', '-hide_banner', '-autoexit', '-loglevel', 'quiet']
        duration = self._get_audio_duration(track_path)
        if not duration: raise Exception("Failed to get file duration, does it actually exist?", track_path)

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
                except subprocess.TimeoutExpired: process.process.kill()
            self.processes.clear()
    def wait_all(self, timeout: float | None = None) -> None:
        with self.lock:
            for process in self.processes:
                try: process.process.wait(timeout)
                except subprocess.TimeoutExpired: process.process.terminate()
            self.processes.clear()

procman = ProcessManager()

def handle_sigint(signum, frame):
    global exit_pending, intr_time
    with exit_lock:
        logger.info("Received SIGINT")
        if (time.time() - intr_time) > 5:
            intr_time = time.time()
            logger.info("Will quit on song end.")
            exit_pending = True
        else:
            logger.warning("Force-Quit pending")
            procman.stop_all()
            raise SystemExit

signal.signal(signal.SIGINT, handle_sigint)

def load_filelines(path):
    try:
        with open(path, 'r') as f: return [line.strip() for line in f.readlines() if line.strip()]
    except FileNotFoundError:
        logger.error(f"Playlist not found: {path}")
        return []

def parse_playlistfile(playlist_path: str) -> tuple[dict[str, str], list[tuple[list[str], dict[str, str]]]]:
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

def play_playlist(playlist_path):
    if not playlist_advisor: raise Exception("No playlist advisor")

    try: global_args, parsed = parse_playlistfile(playlist_path)
    except Exception:
        logger.info(f"Exception while parsing playlist, retrying in 15 seconds...")
        time.sleep(15)
        return

    playlist: list[Track] = []
    for (lns, args) in parsed:
        for line in lns: playlist.append(Track(line, True, True, True, args)) # simple entry, just to convert to a format taken by the modules

    for module in playlist_modifier_modules: playlist = module.modify(global_args, playlist)
    for module in simple_modules: module.on_new_playlist(playlist)
    if active_modifier: active_modifier.on_new_playlist(playlist)

    return_pending = False

    cross_fade = int(global_args.get("crossfade", 5))

    max_iterator = len(playlist)
    song_i = i = 0

    while i < max_iterator:
        if exit_pending:
            logger.info("Quit received, waiting for song end.")
            procman.wait_all()
            exit()
        elif return_pending:
            logger.info("Return reached, next song will reload the playlist.")
            procman.wait_all()
            return

        if playlist_advisor.new_playlist():
            logger.info("Reloading now...")
            return_pending = True
            continue

        old_track = playlist[song_i % len(playlist)]
        if active_modifier:
            track, extend = active_modifier.play(song_i, old_track)
            if track is None:
                song_i += 1
                continue
            if extend: max_iterator += 1
        else:
            extend = False
            track = old_track

        track_path = os.path.abspath(os.path.expanduser(track.path))
        track_name = os.path.basename(track_path)

        logger.info(f"Now playing: {track_name}")

        for module in simple_modules: module.on_new_track(song_i, track)

        pr = procman.play(track_path, track.fade_in, track.fade_out, cross_fade)

        ttw = pr.duration
        if track.fade_out: ttw -= cross_fade

        end_time = time.time() + ttw
        loop_start = time.time()  # Outside the loop

        def format_time(seconds):
            hours = int(seconds // 3600)
            minutes = int((seconds % 3600) // 60)
            secs = int(seconds % 60)
            return f"{hours:02d}:{minutes:02d}:{secs:02d}"

        while end_time >= time.time():
            start = time.time()
            # do some module callback

            total_uptime = time.time() - loop_start
            if track.official: print(f"{track_name}: {format_time(total_uptime)} / {format_time(pr.duration)}", end="\r", flush=True)

            elapsed = time.time() - start
            remaining_until_end = end_time - time.time()
            
            if elapsed < 1 and remaining_until_end > 0:
                sleep_duration = min(1 - elapsed, remaining_until_end)
                time.sleep(sleep_duration)

        i += 1
        if not extend: song_i += 1

def main():
    global playlist_advisor, active_modifier
    for filename in os.listdir(MODULES_DIR):
        if filename.endswith(".py") and filename != "__init__.py":
            module_name = filename[:-3]
            module_path = MODULES_DIR / filename
            full_module_name = f"{MODULES_PACKAGE}.{module_name}"

            spec = importlib.util.spec_from_file_location(full_module_name, module_path)
            if not spec: continue
            module = importlib.util.module_from_spec(spec)

            sys.modules[full_module_name] = module

            if MODULES_PACKAGE not in sys.modules:
                parent = types.ModuleType(MODULES_PACKAGE)
                parent.__path__ = [str(MODULES_DIR)]
                parent.__package__ = MODULES_PACKAGE
                sys.modules[MODULES_PACKAGE] = parent

            module.__package__ = MODULES_PACKAGE

            if not spec.loader: continue
            try: spec.loader.exec_module(module)
            except Exception as e:
                logger.error(f"Failed loading {module_name} due to {e}")
                continue

            if md := getattr(module, "module", None):
                if isinstance(md, list): simple_modules.extend(md)
                else: simple_modules.append(md)
            if md := getattr(module, "playlistmod", None):
                if isinstance(md, tuple):
                    md, index = md
                    if isinstance(md, list): playlist_modifier_modules[index:index] = md
                    else: playlist_modifier_modules.insert(index, md)
                elif isinstance(md, list): playlist_modifier_modules.extend(md)
                else: playlist_modifier_modules.append(md)
            if md := getattr(module, "advisor", None):
                if playlist_advisor: raise Exception("Multiple playlist advisors")
                playlist_advisor = md
            if md := getattr(module, "activemod", None):
                if active_modifier: raise Exception("Multiple active modifiers")
                active_modifier = md

    if not playlist_advisor:
        logger.critical_error("Playlist advisor was not found")
        exit(1)

    imc = InterModuleCommunication(playlist_advisor, active_modifier, simple_modules)
    playlist_advisor.imc(imc)
    if active_modifier: active_modifier.imc(imc)
    for module in simple_modules: module.imc(imc)

    try:
        arg = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else None
        if active_modifier: active_modifier.arguments(arg)
        while True:
            if playlist := playlist_advisor.advise(arg):
                logger.info(f"Advisor picked '{playlist}' to play")
                play_playlist(playlist)
            if exit_pending: exit()
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        procman.stop_all()
        raise
    finally: procman.stop_all()
