#!/usr/bin/env python3
DEBUG = False
import time, datetime
import os, subprocess
import sys, signal, threading, glob
import re, unidecode
import random
import socket
from dataclasses import dataclass
import log95, copy

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

def write_playlist(tracks: list, i: int):
    lines = tracks[:i] + [f"> {tracks[i]}"] + tracks[i+1:]
    with open("/tmp/radioPlayer_playlist", "w") as f:
        for line in lines: 
            try: f.write(line + "\n")
            except UnicodeEncodeError:
                print(line.encode('utf-8', errors='ignore').decode('utf-8'))
                raise

MORNING_START = 5
MORNING_END = 11
DAY_START = 11
DAY_END = 19
LATE_NIGHT_START = 0
LATE_NIGHT_END = 5

JINGIEL_FILE = "/home/user/Jingiel.mp3"

playlist_dir = "/home/user/playlists"
name_table_path = "/home/user/mixes/name_table.txt"

rds_base = "Gramy: {} - {}"
rds_default_artist = "radio95"
rds_default_name = "Program Godzinny"

udp_host = ("127.0.0.1", 5000)

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
            for process in self.processes:
                if process.process.poll() is not None: self.processes.remove(process)
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
                process.process.wait(timeout)
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

def load_dict_from_custom_format(file_path: str) -> dict[str, str]:
    try:
        result_dict = {}
        with open(file_path, 'r') as file:
            for line in file:
                if line.strip() == "" or line.startswith(";"): continue
                key, value = line.split(':', 1)
                result_dict[key.strip()] = value.strip()
        return result_dict
    except FileNotFoundError:
        logger.error(f"{name_table_path} does not exist, or could not be accesed")
        return {}

def process_for_rds(track_name: str):
    name_table = load_dict_from_custom_format(name_table_path)
    try:
        name = name_table[track_name]
        has_name = True
    except KeyError:
        has_name = False
        name = track_name.rsplit(".", 1)[0]
    
    name = re.sub(r'^\s*\d+\s*[-.]?\s*', '', name)

    if " - " in name:
        count = name.count(" - ")
        while count != 1: # youtube reuploads, to avoid things like ilikedick123 - Micheal Jackson - Smooth Criminal
            name = name.split(" - ", 1)[1]
            count = name.count(" - ")
        artist = name.split(" - ", 1)[0]
        title = name.split(" - ", 1)[1]
    else:
        artist = rds_default_artist
        title = name
        if not has_name: logger.warning(f"File does not have a alias in the name table ({track_name})")
    
    title = re.sub(r'\s*[\(\[][^\(\)\[\]]*[\)\]]', '', title) # there might be junk
    
    prt = rds_base.format(artist, title)
    rtp = [4] # type 1
    rtp.append(prt.find(artist)) # start 1
    rtp.append(len(artist)) # len 1
    rtp.append(1) # type 2
    rtp.append(prt.find(title)) # start 2
    rtp.append(len(title) - 1) # len 2
    return prt, ','.join(list(map(str, rtp)))

def update_rds(prt: str, rtp: str):
    try:        
        f = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        f.settimeout(1.0)
        f.sendto(f"TEXT={prt}\r\nRTP={rtp}\r\n".encode(), udp_host)
        f.close()
    except Exception as e: logger.error(f"Error updating RDS: {e}")

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
    last_modified_time = Time.get_playlist_modification_time(playlist_path)
    
    try:
        global_args, parsed = parse_playlistfile(playlist_path)
    except Exception:
        logger.info(f"Exception while parsing playlist, retrying in 15 seconds...")
        time.sleep(15)
        return
    lines_args = copy.deepcopy(parsed)
    lines = []
    for (lns, args) in lines_args:
        lns: list[str]
        args: dict[str, str]

        for i in range(int(args.get("multiplier", 1))): lines.extend(lns)
    
    cross_fade = int(global_args.get("crossfade", 5))
    if int(global_args.get("no_shuffle", 0)) == 0: random.shuffle(lines)
    
    playlist: list[tuple[str, bool, bool, bool]] = [] # name, fade in, fade out, official
    last_jingiel = True
    for line in lines:
        if not last_jingiel and random.choice([False, True, False, False]) and JINGIEL_FILE:
            playlist.append((line, True, False, True))
            playlist.append((JINGIEL_FILE, False, False, False))
            last_jingiel = True
        else:
            playlist.append((line, True, True, True))
            last_jingiel = False
    del last_jingiel

    return_pending = False
    
    for i, (track, to_fade_in, to_fade_out, official) in enumerate(playlist):
        if return_pending:
            logger.info("Return reached, next song will reload the playlist.")
            procman.wait_all()
            return
        elif exit_pending:
            logger.info("Quit received, waiting for song end.")
            procman.wait_all()
            exit()
        elif reload_pending:
            logger.info("Reload requested, restarting with new arguments after song ending")
            procman.wait_all()
            return "reload"
        track_path = os.path.abspath(os.path.expanduser(track))
        track_name = os.path.basename(track_path)
        write_playlist([t[0] for t in playlist], i)

        current_modified_time = Time.get_playlist_modification_time(playlist_path)
        if current_modified_time > last_modified_time:
            logger.info(f"Playlist {playlist_path} has been modified, reloading...")
            return_pending = True
            continue

        return_pending = check_if_playlist_modifed(playlist_path, custom_playlist)
        if return_pending and not procman.anything_playing(): continue

        logger.info(f"Now playing: {track_name}")
        if official:
            rds_rt, rds_rtp = process_for_rds(track_name)
            update_rds(rds_rt, rds_rtp)
            logger.info(f"RT set to '{rds_rt}' (RTP: {rds_rtp})")
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
