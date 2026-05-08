from . import ABC_ProcessManager, Process, Track, Popen, tinytag, RejectedTrack
from threading import Lock
import subprocess, time

class ProcessManager(ABC_ProcessManager):
    def __init__(self) -> None:
        self.lock = Lock()
        self.processes: list[Process] = []
        self.tinytag = tinytag.TinyTag()
        
    def play(self, track: Track) -> Process:
        if track.path.suffix not in self.tinytag.SUPPORTED_FILE_EXTENSIONS or not track.path.exists(): raise RejectedTrack
        cmd = ['ffplay', '-nodisp', '-hide_banner', '-autoexit', '-loglevel', 'quiet']

        duration = self.tinytag.get(track.path.absolute(), tags=False).duration
        if not duration: raise Exception("Failed to get file duration for", track.path)
        if track.offset >= duration: track.offset = max(duration - 0.1, 0)
        if track.offset > 0: cmd.extend(['-ss', str(track.offset)])

        filters = []
        if track.fade_in != 0: filters.append(f"afade=t=in:st=0:d={track.fade_in}")
        if track.fade_out != 0: filters.append(f"afade=t=out:st={duration - track.fade_out}:d={track.fade_out}")
        if filters: cmd.extend(['-af', ",".join(filters)])
        cmd.append(str(track.path.absolute()))

        pr = Process(Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True), track, time.monotonic(), duration - track.offset)
        with self.lock: self.processes.append(pr)
        return pr
    def anything_playing(self) -> bool:
        with self.lock:
            alive = []
            for p in self.processes:
                if p.process.poll() is None: alive.append(p)
                else:
                    try: p.process.wait(timeout=0)
                    except subprocess.TimeoutExpired: pass
            self.processes = alive
            return bool(alive)
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
    def test(self) -> bool:
        proc = Popen(["ffplay"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        start = time.monotonic()
        while proc.poll() is None and (time.monotonic() - start) < 1: time.sleep(0.01)

        if proc.poll() is None: proc.kill()
        return proc.poll() not in (None, 127)

procman = ProcessManager()

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
