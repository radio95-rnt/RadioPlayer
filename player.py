import os
import random
import subprocess
import time
import sys
from datetime import datetime

playlist_dir = '/home/user/playlists'

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
        name_table = load_dict_from_custom_format("/home/user/mixes/name_table.txt")
        try:
            prt = f"Gramy: radio95 - {name_table[track_name]}"
        except KeyError as e:
            print("Unknown", e)
            prt = "Gramy: radio95 - Program Godzinny"

        with open("/home/user/RDS", "w") as f:
            f.write(f"TEXT={prt}\r")

        try:
            with open("/home/user/RDS", "w") as f:
                f.write(f"RTP=4,7,7,1,17,{len(str(name_table[track_name]))-1}\r")
        except KeyError:
            with open("/home/user/RDS", "w") as f:
                f.write(f"RTP=4,7,7,1,17,15\r")
    except Exception as e:
        print(f"Error updating RDS: {e}")

def get_playlist_modification_time(playlist_path):
    """Get the modification time of the playlist file."""
    try:
        return os.path.getmtime(playlist_path)
    except OSError:
        return 0

def load_playlist(playlist_path):
    """Load tracks from playlist file."""
    try:
        with open(playlist_path, 'r') as f:
            tracks = [line.strip() for line in f.readlines() if line.strip()]
        return tracks
    except FileNotFoundError:
        print(f"Warning: Playlist not found: {playlist_path}")
        return []

def get_newest_track(tracks):
    """Find the newest track (most recently modified) from the playlist."""
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
            # Skip files that can't be accessed
            continue
    
    return newest_track

def play_playlist(playlist_path, play_newest_first=False):
    last_modified_time = get_playlist_modification_time(playlist_path)
    tracks = load_playlist(playlist_path)
    if not tracks:
        print(f"No tracks found in {playlist_path}, checking again in 30 seconds...")
        time.sleep(30)
        return

    if play_newest_first:
        newest_track = get_newest_track(tracks)
        if newest_track:
            print(f"Playing newest track first: {os.path.basename(newest_track)}")
            # Remove the newest track from the list
            tracks.remove(newest_track)
            # Shuffle the remaining tracks
            random.shuffle(tracks)
            # Add the newest track back at the beginning
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
        day_playlist_path = os.path.join(playlist_dir, current_day, 'day')
        night_playlist_path = os.path.join(playlist_dir, current_day, 'night')
        late_night_playlist_path = os.path.join(playlist_dir, current_day, 'late_night')

        if 8 <= current_hour < 20:
            if playlist_path != day_playlist_path:
                print("Time changed to day hours, switching playlist...")
                return
        elif 0 <= current_hour < 6:
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

        subprocess.run(['ffplay', '-nodisp', '-stats', '-hide_banner', '-autoexit', track_path])

def main():
    # Check if the "n" argument was provided
    play_newest_first = len(sys.argv) > 1 and sys.argv[1].lower() == "n"
    
    if play_newest_first:
        print("Newest song will be played first")

    while True:
        current_hour = get_current_hour()
        current_day = get_current_day()

        day_playlist = os.path.join(playlist_dir, current_day, 'day')
        night_playlist = os.path.join(playlist_dir, current_day, 'night')
        late_night_playlist = os.path.join(playlist_dir, current_day, 'late_night')

        day_dir = os.path.dirname(day_playlist)
        night_dir = os.path.dirname(night_playlist)
        late_night_dir = os.path.dirname(late_night_playlist)

        if not os.path.exists(day_dir):
            print(f"Creating directory: {day_dir}")
            os.makedirs(day_dir, exist_ok=True)

        if not os.path.exists(night_dir):
            print(f"Creating directory: {night_dir}")
            os.makedirs(night_dir, exist_ok=True)

        if not os.path.exists(late_night_dir):
            print(f"Creating directory: {late_night_dir}")
            os.makedirs(late_night_dir, exist_ok=True)

        for playlist_path in [day_playlist, night_playlist, late_night_playlist]:
            if not os.path.exists(playlist_path):
                print(f"Creating empty playlist: {playlist_path}")
                with open(playlist_path, 'w') as f:
                    pass

        if 8 <= current_hour < 20:
            print(f"Playing {current_day} day playlist...")
            play_playlist(day_playlist, play_newest_first)
        elif 0 <= current_hour < 6:
            print(f"Playing {current_day} late_night playlist...")
            play_playlist(late_night_playlist, play_newest_first)
        else:
            print(f"Playing {current_day} night playlist...")
            play_playlist(night_playlist, play_newest_first)


if __name__ == '__main__':
    main()
