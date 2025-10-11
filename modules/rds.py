class PlayerModule:
    def on_new_playlist(self, playlist: list[tuple[str, bool, bool, bool]]):
        pass
    def on_new_track(self, index: int, track: str, to_fade_in: bool, to_fade_out: bool, official: bool):
        pass

import socket, re, log95, os

name_table_path = "/home/user/mixes/name_table.txt"

rds_base = "Gramy: {} - {}"
rds_default_artist = "radio95"
rds_default_name = "Program Godzinny"

udp_host = ("127.0.0.1", 5000)

logger = log95.log95("RDS-MODULE")

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

    try:        
        f = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        f.settimeout(1.0)
        f.sendto(f"TEXT={prt}\r\nRTP={rtp}\r\n".encode(), udp_host)
        f.close()
    except Exception as e: logger.error(f"Error updating RDS: {e}")

    return prt, ','.join(list(map(str, rtp)))

class Module(PlayerModule):
    def on_new_track(self, index: int, track: str, to_fade_in: bool, to_fade_out: bool, official: bool):
        if official:
            rds_rt, rds_rtp = update_rds(os.path.basename(track))
            logger.info(f"RT set to '{rds_rt}' (RTP: {rds_rtp})")