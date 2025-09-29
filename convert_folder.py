import os
import glob

# Base directory where your playlists live
BASE_DIR = os.path.expanduser("~/playlists")
FORMATS = ('.mp3', '.m4a', '.flac', '.wav')

# Collect all playlist files (recursively all subfolders)
playlist_files = glob.glob(os.path.join(BASE_DIR, "*", "*"))

for plist in playlist_files:
    with open(plist, "r") as f:
        lines = [line.strip() for line in f if line.strip()]
    
    dirs = []
    files = []
    for line in lines:
        dir = os.path.basename(os.path.dirname(line))
        if dir not in dirs and dir != "mixes": dirs.append(dir)
        if dir == "mixes": files.append(line)
    with open(plist, "w") as f:
        f.writelines([i + "\n" for i in files])
        for dir in dirs:
            base = f"/home/user/mixes/{dir}/*"
            for format in  FORMATS:
                f.write(base + format + "\n")