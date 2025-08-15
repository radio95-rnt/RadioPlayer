#!/usr/bin/env python3
import os, socket
import random
import subprocess
import time, datetime
import sys
import threading
import json
from datetime import datetime
import log95

MORNING_START = 6
MORNING_END = 10
DAY_START = 10
DAY_END = 20
LATE_NIGHT_START = 0
LATE_NIGHT_END = 6

playlist_dir = "/home/user/playlists"
name_table_path = "/home/user/mixes/name_table.txt"
state_file_path = "/tmp/radioPlayer_state.json"

rds_base = "Gramy: radio95 - {}"
rds_default_name = "Program Godzinny"
rds_default_rtp_data = "4,7,7,1,17"

udp_host = ("127.0.0.1", 5000)

logger = log95.log95("radioPlayer")

# Global variables for state tracking
current_state = {
    "current_file": None,
    "start_time": None,
    "duration": None,
    "playlist_path": None,
    "playlist_position": 0
}
state_thread = None
state_lock = threading.Lock()

def get_current_hour():
    return datetime.now().hour

def get_current_day():
    return datetime.now().strftime('%A').lower()

def load_dict_from_custom_format(file_path: str) -> dict:
    try:
        result_dict = {}
        with open(file_path, 'r') as file:
            for line in file:
                if line.strip() == "":
                    continue
                key, value = line.split(':', 1)
                result_dict[key.strip()] = value.strip()
        return result_dict
    except FileNotFoundError:
        logger.error(f"{name_table_path} does not exist, or could not be accesed")
        return {}

def save_state():
    """Save current state to file"""
    try:
        with state_lock:
            with open(state_file_path, 'w') as f:
                json.dump(current_state, f)
    except Exception as e:
        logger.error(f"Error saving state: {e}")

def load_state():
    """Load state from file"""
    global current_state
    try:
        if os.path.exists(state_file_path):
            with open(state_file_path, 'r') as f:
                loaded_state = json.load(f)
                with state_lock:
                    current_state.update(loaded_state)
                logger.info(f"Loaded state: {current_state}")
                return True
    except Exception as e:
        logger.error(f"Error loading state: {e}")
    return False

def clear_state():
    """Clear state file"""
    try:
        if os.path.exists(state_file_path):
            os.remove(state_file_path)
    except Exception as e:
        logger.error(f"Error clearing state: {e}")

def get_audio_duration(file_path):
    """Get duration of audio file using ffprobe"""
    try:
        result = subprocess.run([
            'ffprobe', '-v', 'quiet', '-show_entries', 'format=duration', 
            '-of', 'default=noprint_wrappers=1:nokey=1', file_path
        ], capture_output=True, text=True)
        
        if result.returncode == 0:
            duration = float(result.stdout.strip())
            return duration
    except Exception as e:
        logger.error(f"Error getting duration for {file_path}: {e}")
    return None

def update_current_state(file_path, playlist_path=None, playlist_position=0):
    """Update current state with new file"""
    with state_lock:
        current_state["current_file"] = file_path
        current_state["start_time"] = time.time()
        current_state["duration"] = get_audio_duration(file_path)
        current_state["playlist_path"] = playlist_path
        current_state["playlist_position"] = playlist_position
    save_state()

def clear_current_state():
    """Clear current playing state"""
    with state_lock:
        current_state["current_file"] = None
        current_state["start_time"] = None
        current_state["duration"] = None
    save_state()

def should_resume_from_state(tracks, playlist_path):
    """Check if we should resume from saved state"""
    if not current_state["current_file"] or not current_state["start_time"]:
        return False, tracks, 0
        
    # Check if the saved file is still in the current playlist
    if current_state["current_file"] in tracks and current_state["playlist_path"] == playlist_path:
        elapsed = time.time() - current_state["start_time"]
        
        # Only resume if less than the track duration and less than 10 minutes have passed
        if (current_state["duration"] and elapsed < current_state["duration"] and elapsed < 600):
            # Find position of the current file
            try:
                resume_index = tracks.index(current_state["current_file"])
                logger.info(f"Resuming from {os.path.basename(current_state['current_file'])} at {elapsed:.0f}s")
                return True, tracks, resume_index
            except ValueError:
                pass
    
    return False, tracks, 0

def update_rds(track_name):
    try:
        name_table = load_dict_from_custom_format(name_table_path)
        try:
            prt = rds_base.format(name_table[track_name])
        except KeyError as e:
            logger.warning(f"File does not have a alias in the name table ({e})")
            prt = rds_base.format(rds_default_name)

        f = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        f.settimeout(1.0)
        try:
            f.sendto(f"TEXT={prt}\r\n".encode(), udp_host)
        except socket.timeout:
            logger.error("Could not send TEXT to RDS, timeout.")
            return

        try:
            try:
                f.sendto(f"RTP={rds_default_rtp_data},{len(str(name_table[track_name]))-1}\r\n".encode(), udp_host)
            except KeyError:
                f.sendto(f"RTP={rds_default_rtp_data},{len(rds_default_name)-1}\r\n".encode(), udp_host)
        except socket.timeout:
            logger.error("Could not send TEXT to RDS, timeout.")
            return
        f.close()
    except Exception as e:
        logger.error(f"Error updating RDS: {e}")

def get_playlist_modification_time(playlist_path):
    try:
        return os.path.getmtime(playlist_path)
    except OSError:
        return 0

def load_playlist(playlist_path):
    try:
        with open(playlist_path, 'r') as f:
            tracks = [line.strip() for line in f.readlines() if line.strip()]
        return tracks
    except FileNotFoundError:
        logger.error(f"Playlist not found: {playlist_path}")
        return []

def get_newest_track(tracks):
    if not tracks:
        return None
    
    newest_track = None
    newest_time = 0
    
    for track in tracks:
        track_path = os.path.abspath(os.path.expanduser(track))
        try:
            mod_time = os.path.getmtime(track_path)
            if mod_time > newest_time:
                newest_time = mod_time
                newest_track = track
        except OSError:
            continue
    
    return newest_track

def check_control_files():
    """Check for control files and return action to take"""
    if can_delete_file("/tmp/radioPlayer_quit"):
        os.remove("/tmp/radioPlayer_quit")
        return "quit"
    
    if can_delete_file("/tmp/radioPlayer_reload"):
        os.remove("/tmp/radioPlayer_reload")
        return "reload"
    
    return None

def play_audio_with_resume(track_path, resume_seconds=0):
    """Play audio file, optionally resuming from a specific position"""
    cmd = ['ffplay', '-nodisp', '-hide_banner', '-autoexit', '-loglevel', 'quiet']
    
    if resume_seconds > 0:
        cmd.extend(['-ss', str(resume_seconds)])
    
    cmd.append(track_path)
    
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def play_playlist(playlist_path, custom_playlist: bool=False, play_newest_first=False, do_shuffle=True):
    last_modified_time = get_playlist_modification_time(playlist_path)
    tracks = load_playlist(playlist_path)
    if not tracks:
        logger.info(f"No tracks found in {playlist_path}, checking again in 15 seconds...")
        time.sleep(15)
        return

    if do_shuffle: random.seed()
    
    # Check if we should resume from saved state
    should_resume, tracks, resume_index = should_resume_from_state(tracks, playlist_path)
    start_index = 0
    resume_seconds = 0
    
    if should_resume:
        start_index = resume_index
        with state_lock:
            resume_seconds = time.time() - current_state["start_time"]
    else:
        # Normal playlist preparation
        if play_newest_first:
            newest_track = get_newest_track(tracks)
            if newest_track:
                logger.info(f"Playing newest track first: {os.path.basename(newest_track)}")
                tracks.remove(newest_track)
                if do_shuffle: random.shuffle(tracks)
                tracks.insert(0, newest_track)
        else:
            if do_shuffle:
                random.shuffle(tracks)

    for i, track in enumerate(tracks[start_index:], start_index):
        current_modified_time = get_playlist_modification_time(playlist_path)
        if current_modified_time > last_modified_time:
            logger.info(f"Playlist {playlist_path} has been modified, reloading...")
            clear_current_state()
            return

        current_hour = get_current_hour()
        current_day = get_current_day()
        morning_playlist_path = os.path.join(playlist_dir, current_day, 'morning')
        day_playlist_path = os.path.join(playlist_dir, current_day, 'day')
        night_playlist_path = os.path.join(playlist_dir, current_day, 'night')
        late_night_playlist_path = os.path.join(playlist_dir, current_day, 'late_night')

        if DAY_START <= current_hour < DAY_END and not custom_playlist:
            if playlist_path != day_playlist_path:
                logger.info("Time changed to day hours, switching playlist...")
                clear_current_state()
                return
        elif MORNING_START <= current_hour < MORNING_END and not custom_playlist:
            if playlist_path != morning_playlist_path:
                logger.info("Time changed to morning hours, switching playlist...")
                clear_current_state()
                return
        elif LATE_NIGHT_START <= current_hour < LATE_NIGHT_END and not custom_playlist:
            if playlist_path != late_night_playlist_path:
                logger.info("Time changed to late night hours, switching playlist...")
                clear_current_state()
                return
        else:
            if playlist_path != night_playlist_path and not custom_playlist:
                logger.info("Time changed to night hours, switching playlist...")
                clear_current_state()
                return

        track_path = os.path.abspath(os.path.expanduser(track))
        track_name = os.path.basename(track_path)
        
        # Update state before playing
        update_current_state(track_path, playlist_path, i)
        
        if i == start_index and resume_seconds > 0:
            logger.info(f"Resuming: {track_name} at {resume_seconds:.0f}s")
        else:
            logger.info(f"Now playing: {track_name}")
            resume_seconds = 0
            
        update_rds(track_name)

        play_audio_with_resume(track_path, resume_seconds)
        
        # Clear state after track finishes
        clear_current_state()

        # Check control files after each song
        action = check_control_files()
        if can_delete_file("/tmp/radioPlayer_onplaylist"): action = None
        if action == "quit":
            clear_state()
            exit()
        elif action == "reload":
            logger.info("Reload requested, restarting with new arguments...")
            return "reload"

def can_delete_file(filepath):
    if not os.path.isfile(filepath):
        return False
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
            print("   /tmp/radioPlayer_quit          -   Quit the player")
            print("   /tmp/radioPlayer_reload        -   Reload arguments from /tmp/radioPlayer_arg")
            print("   /tmp/radioPlayer_onplaylist    -   React to quit or reload only when ending a playlist")
            print("   /tmp/radioPlayer_arg           -   Contains arguments to use")
            print()
            print("Arguments:")
            print("    n                        -    Play newest song first")
            print("    list:playlist;options    -    Play custom playlist with options")
            print("    /path/to/file            -    Play specific file first")
            exit(0)
    
    if can_delete_file("/tmp/radioPlayer_arg"):
        with open("/tmp/radioPlayer_arg", "r") as f:
            arg = f.read().strip()
        os.remove("/tmp/radioPlayer_arg")

    if arg:
        if arg.lower() == "n":
            play_newest_first = True
            logger.info("Newest song will be played first")
        elif arg.startswith("list:"):
            selected_list = arg.removeprefix("list:")
            logger.info(f"The list {selected_list.split(';')[0]} will be played instead of the daily section lists.")
            for option in selected_list.split(";"):
                if option == "n":
                    play_newest_first = True
                elif option == "ns":
                    do_shuffle = False
            selected_list = selected_list.split(";")[0]
        elif os.path.isfile(arg):
            pre_track_path = arg
            logger.info(f"Will play requested song first: {arg}")
        else:
            logger.error(f"Invalid argument or file not found: {arg}")

    return arg, play_newest_first, do_shuffle, pre_track_path, selected_list

def main():
    # Load state at startup
    state_loaded = load_state()
    
    while True:  # Main reload loop
        arg, play_newest_first, do_shuffle, pre_track_path, selected_list = parse_arguments()
        
        if pre_track_path:
            track_name = os.path.basename(pre_track_path)
            logger.info(f"Now playing: {track_name}")
            update_current_state(pre_track_path)
            update_rds(track_name)
            subprocess.run(['ffplay', '-nodisp', '-hide_banner', '-autoexit', '-loglevel', 'quiet', pre_track_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            clear_current_state()
            
            action = check_control_files()
            if can_delete_file("/tmp/radioPlayer_onplaylist"): action = None
            if action == "quit":
                clear_state()
                exit()
            elif action == "reload":
                logger.info("Reload requested, restarting with new arguments...")
                continue  # Restart the main loop

        # Check if we should resume from loaded state first
        if state_loaded and current_state.get("current_file") and current_state.get("playlist_path"):
            # Try to resume from the loaded state
            if os.path.exists(current_state["playlist_path"]):
                logger.info(f"Attempting to resume from saved state: {current_state['playlist_path']}")
                result = play_playlist(current_state["playlist_path"], 
                                     current_state["playlist_path"] != os.path.join(playlist_dir, get_current_day(), 'morning') and
                                     current_state["playlist_path"] != os.path.join(playlist_dir, get_current_day(), 'day') and  
                                     current_state["playlist_path"] != os.path.join(playlist_dir, get_current_day(), 'night') and
                                     current_state["playlist_path"] != os.path.join(playlist_dir, get_current_day(), 'late_night'),
                                     play_newest_first, do_shuffle)
                state_loaded = False  # Don't try to resume again
                if result == "reload":
                    continue
            else:
                logger.warning(f"Saved playlist path no longer exists: {current_state['playlist_path']}")
                clear_current_state()
                state_loaded = False

        playlist_loop_active = True
        while playlist_loop_active:
            if selected_list:
                logger.info("Playing custom list")
                result = play_playlist(selected_list, True, play_newest_first, do_shuffle)
                if result == "reload":
                    playlist_loop_active = False  # Break out to reload
                continue
            
            current_hour = get_current_hour()
            current_day = get_current_day()

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
                    with open(playlist_path, 'w') as f:
                        pass

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
            if not can_delete_file("/tmp/radioPlayer_onplaylist"): action = None
            if action == "quit":
                if os.path.exists("/tmp/radioPlayer_onplaylist"):
                    os.remove("/tmp/radioPlayer_onplaylist")
                clear_state()
                exit()
            elif action == "reload":
                if os.path.exists("/tmp/radioPlayer_onplaylist"):
                    os.remove("/tmp/radioPlayer_onplaylist")
                logger.info("Reload requested, restarting with new arguments...")
                result = "reload"
            
            if result == "reload":
                playlist_loop_active = False  # Break out to reload

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Player stopped by user")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        raise