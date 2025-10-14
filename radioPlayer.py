#!/usr/bin/env python3
DEBUG = False
import time
import os, subprocess, importlib.util
import sys, signal, threading, glob
import unidecode
from dataclasses import dataclass
import log95
from pathlib import Path

class PlayerModule:
    """
    Simple passive observer, this allows you to send the current track the your RDS encoder, or to your website
    """
    def on_new_playlist(self, playlist: list[tuple[str, bool, bool, bool, dict[str, str]]]): 
        """Tuple consists of the track path, to fade out, fade in, official, and args"""
        pass
    def on_new_track(self, index: int, track: str, to_fade_in: bool, to_fade_out: bool, official: bool): pass
class PlaylistModifierModule:
    """
    Playlist modifier, this type of module allows you to shuffle, or put jingles into your playlist
    """
    def modify(self, global_args: dict, playlist: list[tuple[str, bool, bool, bool, dict[str, str]]]): return playlist
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
class ActiveModifier:
    """
    This changes the next song to be played live, which means that this picks the next song, not the playlist, but this is affected by the playlist
    """
    def play(self, index:int, track: tuple[str, bool, bool, bool, dict[str, str]]): return track
    def on_new_playlist(self, playlist: list[tuple[str, bool, bool, bool, dict[str, str]]]): pass

simple_modules: list[PlayerModule] = []
playlist_modifier_modules: list[PlaylistModifierModule] = []
playlist_advisor: PlaylistAdvisor | None = None
active_modifier: ActiveModifier | None = None

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

logger_level = log95.log95Levels.DEBUG if DEBUG else log95.log95Levels.CRITICAL_ERROR
logger = log95.log95("radioPlayer", logger_level)

exit_pending = False
intr_time = 0

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

signal.signal(signal.SIGINT, handle_sigint)

def load_filelines(path):
    try:
        with open(path, 'r') as f: return [unidecode.unidecode(line.strip()) for line in f.readlines() if unidecode.unidecode(line.strip())]
    except FileNotFoundError:
        logger.error(f"Playlist not found: {path}")
        return []

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

def play_playlist(playlist_path):
    if not playlist_advisor: raise Exception("No playlist advisor")

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
    if active_modifier: active_modifier.on_new_playlist(playlist)

    return_pending = False

    cross_fade = int(global_args.get("crossfade", 5))

    max_iterator = len(playlist)
    i = 0
    
    while i < max_iterator:
        if exit_pending:
            logger.info("Quit received, waiting for song end.")
            procman.wait_all()
            exit()
        elif return_pending:
            logger.info("Return reached, next song will reload the playlist.")
            procman.wait_all()
            return
        
        old_track_tuple = playlist[i]
        if active_modifier: 
            track_tuple = active_modifier.play(i, old_track_tuple)
            modified = True
            logger.debug(repr(old_track_tuple), repr(track_tuple), repr(old_track_tuple != track_tuple))
            if old_track_tuple != track_tuple: 
                max_iterator += 1
                modified = True
        else: modified = False
        track, to_fade_in, to_fade_out, official, args = track_tuple

        track_path = os.path.abspath(os.path.expanduser(track))
        for module in simple_modules: module.on_new_track(i, track_path, to_fade_in, to_fade_out, official)
        track_name = os.path.basename(track_path)

        refresh = playlist_advisor.new_playlist()

        if refresh == 1:
            logger.info("Reloading now...")
            return_pending = True
            continue
        elif refresh == 2:
            return_pending = True
            if not procman.anything_playing(): continue

        logger.info(f"Now playing: {track_name}")
        if modified:
            if (i + 1) < len(playlist): logger.info(f"Next up: {os.path.basename(playlist[i+1][0])}")
        else:
            logger.info(f"Next up: {os.path.basename(playlist[i][0])}")
        
        pr = procman.play(track_path, to_fade_in, to_fade_out)

        ttw = pr.duration
        if to_fade_out: ttw -= cross_fade

        if official: print_wait(ttw, 1, pr.duration, f"{track_name}: ")
        else: time.sleep(ttw)
        if not modified: i += 1

def main():
    global playlist_advisor, active_modifier
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
            elif md := getattr(module, "advisor", None):
                if playlist_advisor: raise Exception("Multiple playlist advisors")
                playlist_advisor = md
            elif md := getattr(module, "activemod", None):
                if active_modifier: raise Exception("Multiple active modifiers")
                active_modifier = md
    
    if not playlist_advisor: 
        logger.critical_error("Playlist advisor was not found")
        exit(1)
    
    try:
        arg = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else None
        while True:
            play_playlist(playlist_advisor.advise(arg))
            if exit_pending: exit()
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        procman.stop_all()
        raise
    finally: procman.stop_all()
