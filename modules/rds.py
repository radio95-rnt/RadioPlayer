from modules import InterModuleCommunication

from . import PlayerModule, log95, Track
import socket

# https://github.com/chrko/python-uecp
import uecp.frame
import uecp.commands

@uecp.commands.UECPCommand.register_type
class ASCII(uecp.commands.UECPCommand):
    ELEMENT_CODE = 0x2D
    @classmethod
    def create_from(cls, data: bytes | list[int]): raise NotImplementedError()
    def __init__(self, data: bytes) -> None: self.data = data
    def encode(self) -> list[int]:
        return [
            self.ELEMENT_CODE,
            2+len(self.data)] + list(b"95") + list(self.data)

DEBUG = False

name_table_path = "/home/user/mixes/name_table.txt"

rds_base = "ON AIR: {} - {}"
rds_default_artist = "radio95"

udp_host = ("127.0.0.1", 5000)

logger_level = log95.log95Levels.DEBUG if DEBUG else log95.log95Levels.CRITICAL_ERROR
_log_out: log95.TextIO
assert _log_out # pyright: ignore[reportUnboundVariable]
logger = log95.log95("RDS", logger_level, output=_log_out)

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

    prt = rds_base.format(artist, title)[:64]
    rtp = []
    rtp.append(1) # type 2
    rtp.append(prt.find(title)) # start 2
    rtp.append(len(title) - 1) # len 2
    rtp.append(4) # type 1
    rtp.append(prt.find(artist)) # start 1
    rtp.append(len(artist) - 1) # len 1

    rtp = [j_size if i_rt > j_size else i_rt for i_rt,j_size in zip(rtp, [255,0x3f,0x3f,255,0x3f,0x1f])]

    rtp = ','.join(list(map(str, rtp)))

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as f:
            f.settimeout(1.0)
            uecp_frame = uecp.frame.UECPFrame()
            if 0 < len(prt) < 61: prt += "\r" # makes the warning go away
            uecp_frame.add_command(uecp.commands.RadioTextSetCommand(prt, 4, True))
            uecp_frame.add_command(ASCII(f"RTP={rtp}".encode()))

            data = uecp_frame.encode()
            f.sendto(data, udp_host)
            logger.debug("Sending", str(data))
    except Exception as e: logger.error(f"Error updating RDS: {e}")

    return prt, rtp

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