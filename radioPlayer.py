#!/usr/bin/env python3
import os, socket
import random
import subprocess
import time, datetime
import sys, signal
import threading
import re, unidecode
from dataclasses import dataclass
from datetime import datetime
import log95

MORNING_START = 6
MORNING_END = 10
DAY_START = 10
DAY_END = 20
LATE_NIGHT_START = 0
LATE_NIGHT_END = 6

CROSSFADE_DURATION = 3  # seconds

playlist_dir = "/home/user/playlists"
name_table_path = "/home/user/mixes/name_table.txt"

rds_base = "Gramy: {} - {}"
rds_default_artist = "radio95"
rds_default_name = "Program Godzinny"

udp_host = ("127.0.0.1", 5000)

logger = log95.log95("radioPlayer")

exit_pending = False
intr_time = 0

class Time:
    @staticmethod
    def get_day_hour(): return datetime.now().strftime('%A').lower(), datetime.now().hour
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
    def play(self, track_path: str, fade_in: bool=False, fade_out: bool=False) -> Process:
        cmd = ['ffplay', '-nodisp', '-hide_banner', '-autoexit', '-loglevel', 'quiet']
        duration = self._get_audio_duration(track_path)
        if not duration: raise Exception("Failed to get file duration, does it actually exit?", track_path)

        filters = []
        if fade_in: filters.append(f"afade=t=in:st=0:d={CROSSFADE_DURATION}")
        if fade_out: filters.append(f"afade=t=out:st={duration-CROSSFADE_DURATION}:d={CROSSFADE_DURATION}")
        if filters: cmd.extend(['-af', ",".join(filters)])

        cmd.append(track_path)

        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        pr = Process(proc, track_path, time.time(), duration)
        with self.lock: self.processes.append(pr)
        return pr
    def anything_playing(self) -> bool:
        with self.lock:
            for process in self.processes[:]:
                if process.process.poll() is not None: self.processes.remove(process)
            return bool(self.processes)
    def stop_all(self, timeout: float | None = 2) -> bool:
        success = True
        with self.lock:
            for process in self.processes:
                process.process.terminate()
                try: process.process.wait(timeout)
                except: 
                    success = False
                    continue
                self.processes.remove(process)
        return success
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
        procman.stop_all(None)

signal.signal(signal.SIGINT, handle_sigint)

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

def update_rds(track_name: str):
    try:
        name_table = load_dict_from_custom_format(name_table_path)
        try:
            name = name_table[track_name]
            has_name = True
        except KeyError as e:
            has_name = False
            name = track_name.rsplit(".", 1)[0]
        
        name = re.sub(r'^\s*\d+\s*[-.]?\s*', '', name) # get rid of a 

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

        title = unidecode.unidecode(title)
        artist = unidecode.unidecode(artist)
        
        title = re.sub(r'\s*[\(\[][^\(\)\[\]]*[\)\]]', '', title) # there might be junk

        prt = rds_base.format(artist, title)

        f = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        f.settimeout(1.0)
        f.sendto(f"TEXT={prt}\r\n".encode(), udp_host)
        logger.info("RT set to", prt)

        rtp = [4] # type 1
        rtp.append(prt.find(artist)) # start 1
        rtp.append(len(artist)) # len 1
        rtp.append(1) # type 2
        rtp.append(prt.find(title)) # start 2
        rtp.append(len(title)) # len 2

        f.sendto(f"RTP={','.join(list(map(str, rtp)))}\r\n".encode(), udp_host)
        f.close()
    except Exception as e: logger.error(f"Error updating RDS: {e}")

def load_playlist(playlist_path):
    try:
        with open(playlist_path, 'r') as f: return [line.strip() for line in f.readlines() if line.strip()]
    except FileNotFoundError:
        logger.error(f"Playlist not found: {playlist_path}")
        return []

def get_newest_track(tracks):
    if not tracks: return None

    newest_track = None
    newest_time = 0

    for track in tracks:
        track_path = os.path.abspath(os.path.expanduser(track))
        try:
            mod_time = os.path.getmtime(track_path)
            if mod_time > newest_time:
                newest_time = mod_time
                newest_track = track
        except OSError: continue

    return newest_track

def check_control_files():
    global exit_pending
    """Check for control files and return action to take"""
    if exit_pending:
        exit_pending = False
        return "quit"
    
    if can_delete_file("/tmp/radioPlayer_reload"):
        os.remove("/tmp/radioPlayer_reload")
        return "reload"

    return None

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

def play_playlist(playlist_path, custom_playlist: bool=False, play_newest_first=False, do_shuffle=True):
    last_modified_time = Time.get_playlist_modification_time(playlist_path)
    tracks = load_playlist(playlist_path)
    if not tracks:
        logger.info(f"No tracks found in {playlist_path}, checking again in 15 seconds...")
        time.sleep(15)
        return

    if do_shuffle: random.seed()

    start_index = 0

    # Normal playlist preparation
    if play_newest_first:
        newest_track = get_newest_track(tracks)
        if newest_track:
            logger.info(f"Playing newest track first: {os.path.basename(newest_track)}")
            tracks.remove(newest_track)
            if do_shuffle: random.shuffle(tracks)
            tracks.insert(0, newest_track)
    else:
        if do_shuffle: random.shuffle(tracks)

    return_pending = False

    for i, track in enumerate(tracks[start_index:], start_index):
        if return_pending:
            logger.info("Return reached, next song will reload the playlist.")
            procman.wait_all()
            return
        action = check_control_files()
        if action == "quit":
            logger.info("Quit received, waiting for song end.")
            procman.wait_all()
            exit()
        elif action == "reload":
            logger.info("Reload requested, restarting with new arguments...")
            procman.wait_all()
            return "reload"
        track_path = os.path.abspath(os.path.expanduser(track))
        track_name = os.path.basename(track_path)

        current_modified_time = Time.get_playlist_modification_time(playlist_path)
        if current_modified_time > last_modified_time:
            logger.info(f"Playlist {playlist_path} has been modified, reloading...")
            return_pending = True
            continue

        return_pending = check_if_playlist_modifed(playlist_path, custom_playlist)
        if return_pending and not procman.anything_playing(): continue

        logger.info(f"Now playing: {track_name}")
        update_rds(track_name)
        
        pr = procman.play(track_path, True, True)
        time.sleep(pr.duration - CROSSFADE_DURATION)

def can_delete_file(filepath):
    if not os.path.isfile(filepath): return False
    directory = os.path.dirname(os.path.abspath(filepath)) or '.'
    return os.access(directory, os.W_OK | os.X_OK)

def parse_arguments():
    """Parse command line arguments and return configuration"""
    arg = sys.argv[1] if len(sys.argv) > 1 else None
    play_newest_first = False
    do_shuffle = True
    pre_track_path = None
    selected_list = None

    if arg:
        if arg.lower() == "-h":
            print("Control files:")
            print("    Note: All of these files are one-time only, after they have been acked by the player they will be deleted")
            print("   /tmp/radioPlayer_reload        -   Reload arguments from /tmp/radioPlayer_arg")
            print("   /tmp/radioPlayer_arg           -   Contains arguments to use")
            print()
            print("Arguments:")
            print("    n                        -    Play newest song first")
            print("    list:playlist;options    -    Play custom playlist with options")
            print("    /path/to/file            -    Play specific file first")
            print()
            print("Crossfade: 5-second crossfade is automatically applied between tracks")
            exit(0)

    if can_delete_file("/tmp/radioPlayer_arg"):
        with open("/tmp/radioPlayer_arg", "r") as f: arg = f.read().strip()
        os.remove("/tmp/radioPlayer_arg")

    if arg:
        if arg.lower() == "n":
            play_newest_first = True
            logger.info("Newest song will be played first")
        elif arg.startswith("list:"):
            selected_list = arg.removeprefix("list:")
            logger.info(f"The list {selected_list.split(';')[0]} will be played instead of the daily section lists.")
            for option in selected_list.split(";"):
                if option == "n": play_newest_first = True
                elif option == "ns": do_shuffle = False
            selected_list = selected_list.split(";")[0]
        elif os.path.isfile(arg):
            pre_track_path = arg
            logger.info(f"Will play requested song first: {arg}")
        else: logger.error(f"Invalid argument or file not found: {arg}")

    return play_newest_first, do_shuffle, pre_track_path, selected_list

def main():
    try:
        while True:
            play_newest_first, do_shuffle, pre_track_path, selected_list = parse_arguments()

            if pre_track_path:
                track_name = os.path.basename(pre_track_path)
                logger.info(f"Now playing: {track_name}")
                update_rds(track_name)
                procman.play(pre_track_path).process.wait()

                action = check_control_files()
                if action == "quit":
                    exit()
                elif action == "reload":
                    logger.info("Reload requested, restarting with new arguments...")
                    continue  # Restart the main loop

            play_loop = True
            while play_loop:
                if selected_list:
                    logger.info("Playing custom list")
                    result = play_playlist(selected_list, True, play_newest_first, do_shuffle)
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
                    result = play_playlist(day_playlist, False, play_newest_first, do_shuffle)
                elif MORNING_START <= current_hour < MORNING_END:
                    logger.info(f"Playing {current_day} morning playlist...")
                    result = play_playlist(morning_playlist, False, play_newest_first, do_shuffle)
                elif LATE_NIGHT_START <= current_hour < LATE_NIGHT_END:
                    logger.info(f"Playing {current_day} late_night playlist...")
                    result = play_playlist(late_night_playlist, False, play_newest_first, do_shuffle)
                else:
                    logger.info(f"Playing {current_day} night playlist...")
                    result = play_playlist(night_playlist, False, play_newest_first, do_shuffle)

                action = check_control_files()
                if action == "quit": exit()
                elif action == "reload":
                    logger.info("Reload requested, restarting with new arguments...")
                    result = "reload"

                if result == "reload":  play_loop = False

    except KeyboardInterrupt:
        logger.info("Player stopped by user")
        procman.stop_all()
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        procman.stop_all()
        raise
    finally: procman.stop_all()

if __name__ == '__main__': main()
