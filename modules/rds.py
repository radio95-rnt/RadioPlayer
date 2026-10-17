from modules import InterModuleCommunication

from . import PlayerModule, log95, Track
import socket, struct

import rds_codec
UECP_ADDRESS = 0
DEBUG = False

def crc16_ccitt(data: bytes) -> int:
    crc = 0xFFFF

    for byte in data:
        crc = ((crc >> 8) | (crc << 8)) & 0xFFFF
        crc ^= byte
        crc ^= (crc & 0xFF) >> 4
        crc ^= (crc << 8) << 4 & 0xFFFF
        crc ^= ((crc & 0xFF) << 4) << 1
        crc &= 0xFFFF

    return crc ^ 0xFFFF

def encode_uecp(sequence: int, message: bytes, address: int = UECP_ADDRESS) -> bytes:
    def stuff(x: bytes):
        # Normally they do some for byte in bytes - if byte is fd append fd 0 else append byte, bullshit
        # but this works just as well, is shorter and faster
        return x.replace(b"\xfd", b"\xfd\x00").replace(b"\xfe", b"\xfd\x01").replace(b"\xff", b"\xfd\x02")
    out = struct.pack(">H2B", address, sequence, len(message))
    out += message[:255]
    out += struct.pack(">H", crc16_ccitt(out)) # this crc is "up-to-this-point"
    return b"\xfe" + stuff(out) + b"\xff"

def encapsulate_ascii(data: str):
    bdata = data.encode()
    return b"\x2d" + bytes([len(bdata)+2]) + b"95" + bdata
def set_rt(data: bytes):
    return b"\x0a\0\0" + bytes([len(data)+1, (5 << 1) | 1]) + data


name_table_path = "/mnt/mixes/.playlist/name_table.txt"

rds_base = "ON AIR: {} - {}"
rds_default_artist = "radio95"

udp_host = ("127.0.0.1", 5000)

logger_level = log95.log95Levels.DEBUG if DEBUG else log95.log95Levels.CRITICAL_ERROR
_log_out: log95.TextIO
assert _log_out # pyright: ignore[reportUnboundVariable]
logger = log95.log95("RDS", logger_level, output=_log_out)

uecp_sequence = 1

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
    global uecp_sequence
    name_table = load_dict_from_custom_format(name_table_path)
    try:
        name = name_table[track_name]
        has_name = True
    except KeyError:
        has_name = False
        name = track_name.rsplit(".", 1)[0]

#    name = re.sub(r'^\s*\d+\s*[-.]?\s*', '', name)

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

#    title = re.sub(r'\s*[\(\[][^\(\)\[\]]*[\)\]]', '', title) # there might be junk

    prt = rds_base.format(artist, title).encode("radiodatasystem", "replace")
    title = title.encode("radiodatasystem", "replace")
    artist = artist.encode("radiodatasystem", "replace")

    rtp = []
    def do_title():
        rtp.append(1) # type 2
        rtp.append(prt.find(title)) # start 2
        rtp.append(len(title) - 1) # len 2
    def do_artist():
        rtp.append(4) # type 1
        rtp.append(prt.find(artist)) # start 1
        rtp.append(len(artist) - 1) # len 1
    if len(artist) > len(title):
        do_artist()
        do_title()
    else:
        #len(artist) < len(title)
        do_title()
        do_artist()

    rtp = [j_size if i_rt > j_size else i_rt for i_rt,j_size in zip(rtp, [255,0x3f,0x3f,255,0x3f,0x1f])]

    rtp_str = ','.join(list(map(str, rtp)))

    prt = prt[:64]

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as f:
            f.settimeout(1.0)
            uecp_message = set_rt(prt) + encapsulate_ascii(f"RTP={rtp_str}")

            data = encode_uecp(uecp_sequence, uecp_message)
            uecp_sequence += 1
            if uecp_sequence > 0xff: uecp_sequence = 1

            f.sendto(data, udp_host)
            logger.debug("Sending", str(data))
    except Exception as e: logger.error(f"Error updating RDS: {e}")

    return prt.decode("radiodatasystem", "ignore"), rtp_str

class Module(PlayerModule):
    def on_new_track(self, index: int, track: Track, next_track: Track | None):
        if track.official:
            rds_rt, rds_rtp = update_rds(track.path.name)
            self._imc.send(self, "web", {"rt": rds_rt, "rtp": rds_rtp}, False)
            logger.info(f"RT set to '{rds_rt}'")
            logger.debug(f"{rds_rtp=}")
    def imc(self, imc: InterModuleCommunication) -> None: 
        self._imc = imc
        imc.register(self, "rds")

module = Module()

# This is free and unencumbered software released into the public domain.

# Anyone is free to copy, modify, publish, use, compile, sell, or
# distribute this software, either in source code form or as a compiled
# binary, for any purpose, commercial or non-commercial, and by any
# means.

# In jurisdictions that recognize copyright laws, the author or authors
# of this software dedicate any and all copyright interest in the
# software to the public domain. We make this dedication for the benefit
# of the public at large and to the detriment of our heirs and
# successors. We intend this dedication to be an overt act of
# relinquishment in perpetuity of all present and future rights to this
# software under copyright law.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
# IN NO EVENT SHALL THE AUTHORS BE LIABLE FOR ANY CLAIM, DAMAGES OR
# OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE,
# ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR
# OTHER DEALINGS IN THE SOFTWARE.

# For more information, please refer to <https://unlicense.org>
