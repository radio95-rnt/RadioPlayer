#!/usr/bin/env python3
import os
import random
import subprocess
import time, datetime
import sys
from datetime import datetime

MORNING_START = 6
MORNING_END = 10
DAY_START = 10
DAY_END = 20
LATE_NIGHT_START = 0
LATE_NIGHT_END = 6

playlist_dir = "/home/user/playlists"
name_table_dir = "/home/user/mixes/name_table.txt"

rds_base = "Gramy: radio95 - {}"
rds_default_name = "Program Godzinny"
rds_path = "/home/user/RDS"
rds_default_rtp_data = "4,7,7,1,17"

def get_current_hour():
    return datetime.now().hour

def get_current_day():
    return datetime.now().strftime('%A').lower()

def load_dict_from_custom_format(file_path: str) -> dict:
    result_dict = {}
    with open(file_path, 'r') as file:
        for line in file:
            if line.strip() == "":
                continue
            key, value = line.split(':', 1)
            result_dict[key.strip()] = value.strip()
    return result_dict

def update_rds(track_name):
    try:
        name_table = load_dict_from_custom_format(name_table_dir)
        try:
            prt = rds_base.format(name_table[track_name])
        except KeyError as e:
            print("Unknown", e)
            prt = rds_base.format(rds_default_name)

        f = open(rds_path, "w")
        f.write(f"TEXT={prt}\r\n")

        try:
            f.write(f"RTP={rds_default_rtp_data},{len(str(name_table[track_name]))-1}\r\n")
        except KeyError:
            f.write(f"RTP={rds_default_rtp_data},{len(rds_default_name)-1}\r\n")
        f.close()
    except Exception as e:
        print(f"Error updating RDS: {e}")

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
        print(f"Warning: Playlist not found: {playlist_path}")
        return []

def get_newest_track(tracks):
    if not tracks:
        return None
    
    newest_track = None
    newest_time = 0
    
    for track in tracks:
        track_path = os.path.expanduser(track)
        try:
            mod_time = os.path.getmtime(track_path)
            if mod_time > newest_time:
                newest_time = mod_time
                newest_track = track
        except OSError:
            continue
    
    return newest_track

def play_playlist(playlist_path, play_newest_first=False):
    last_modified_time = get_playlist_modification_time(playlist_path)
    tracks = load_playlist(playlist_path)
    if not tracks:
        print(f"No tracks found in {playlist_path}, checking again in 15 seconds...")
        time.sleep(15)
        return

    random.seed()
    if play_newest_first:
        newest_track = get_newest_track(tracks)
        if newest_track:
            print(f"Playing newest track first: {os.path.basename(newest_track)}")
            tracks.remove(newest_track)
            random.shuffle(tracks)
            tracks.insert(0, newest_track)
    else:
        random.shuffle(tracks)

    for track in tracks:
        current_modified_time = get_playlist_modification_time(playlist_path)
        if current_modified_time > last_modified_time:
            print(f"Playlist {playlist_path} has been modified, reloading...")
            return

        current_hour = get_current_hour()
        current_day = get_current_day()
        morning_playlist_path = os.path.join(playlist_dir, current_day, 'morning')
        day_playlist_path = os.path.join(playlist_dir, current_day, 'day')
        night_playlist_path = os.path.join(playlist_dir, current_day, 'night')
        late_night_playlist_path = os.path.join(playlist_dir, current_day, 'late_night')

        if DAY_START <= current_hour < DAY_END:
            if playlist_path != day_playlist_path:
                print("Time changed to day hours, switching playlist...")
                return
        elif MORNING_START <= current_hour < MORNING_END:
            if playlist_path != morning_playlist_path:
                print("Time changed to morning hours, switching playlist...")
                return
        elif LATE_NIGHT_START <= current_hour < LATE_NIGHT_END:
            if playlist_path != late_night_playlist_path:
                print("Time changed to late night hours, switching playlist...")
                return
        else:
            if playlist_path != night_playlist_path:
                print("Time changed to night hours, switching playlist...")
                return

        track_path = os.path.expanduser(track)
        track_name = os.path.basename(track_path)
        print(f"Now playing: {track_name}")
        update_rds(track_name)

        subprocess.run(['ffplay', '-nodisp', '-hide_banner', '-autoexit', '-loglevel', 'quiet', track_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        if can_delete_file("/tmp/radioPlayer_quit"): 
            os.remove("/tmp/radioPlayer_quit")
            exit()

def can_delete_file(filepath):
    if not os.path.isfile(filepath):
        return False
    directory = os.path.dirname(os.path.abspath(filepath)) or '.'
    return os.access(directory, os.W_OK | os.X_OK)

def main():
    arg = sys.argv[1] if len(sys.argv) > 1 else None
    play_newest_first = False
    pre_track_path = None
    
    if can_delete_file("/tmp/radioPlayer_arg"):
        arg = None
        with open("/tmp/radioPlayer_arg", "r") as f:
            arg = f.read()
        if arg == None: exit(95)
        os.remove("/tmp/radioPlayer_arg")

    if arg:
        if arg.lower() == "-h":
            print("/tmp/radioPlayer_quit")
            print("/tmp/radioPlayer_arg")
            exit(95)
        elif arg.lower() == "n":
            play_newest_first = True
            print("Newest song will be played first")
        elif os.path.isfile(arg):
            pre_track_path = arg
            print(f"Will play requested song first: {arg}")
        else:
            print(f"Invalid argument or file not found: {arg}")

    if pre_track_path:
        track_name = os.path.basename(pre_track_path)
        print(f"Now playing: {track_name}")
        update_rds(track_name)
        subprocess.run(['ffplay', '-nodisp', '-hide_banner', '-autoexit', '-loglevel', 'quiet', pre_track_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if can_delete_file("/tmp/radioPlayer_quit"): 
            os.remove("/tmp/radioPlayer_quit")
            exit()

    while True:
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

        if not os.path.exists(morning_dir):
            print(f"Creating directory: {morning_dir}")
            os.makedirs(morning_dir, exist_ok=True)
        if not os.path.exists(day_dir):
            print(f"Creating directory: {day_dir}")
            os.makedirs(day_dir, exist_ok=True)

        if not os.path.exists(night_dir):
            print(f"Creating directory: {night_dir}")
            os.makedirs(night_dir, exist_ok=True)

        if not os.path.exists(late_night_dir):
            print(f"Creating directory: {late_night_dir}")
            os.makedirs(late_night_dir, exist_ok=True)

        for playlist_path in [morning_playlist, day_playlist, night_playlist, late_night_playlist]:
            if not os.path.exists(playlist_path):
                print(f"Creating empty playlist: {playlist_path}")
                with open(playlist_path, 'w') as f:
                    pass

        if DAY_START <= current_hour < DAY_END:
            print(f"Playing {current_day} day playlist...")
            play_playlist(day_playlist, play_newest_first)
        elif MORNING_START <= current_hour < MORNING_END:
            print(f"Playing {current_day} morning playlist...")
            play_playlist(morning_playlist, play_newest_first)
        elif LATE_NIGHT_START <= current_hour < LATE_NIGHT_END:
            print(f"Playing {current_day} late_night playlist...")
            play_playlist(late_night_playlist, play_newest_first)
        else:
            print(f"Playing {current_day} night playlist...")
            play_playlist(night_playlist, play_newest_first)


if __name__ == '__main__':
    main()
