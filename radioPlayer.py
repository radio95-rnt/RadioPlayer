#!/usr/bin/env python3
import time
import os, subprocess, importlib.util, types
import sys, signal, threading, glob
import libcache, traceback
from modules import *

def prefetch(path):
    if os.name != "posix": return
    with open(path, "rb") as f:
        fd = f.fileno()
        os.posix_fadvise(fd, 0, 0, os.POSIX_FADV_SEQUENTIAL)
        os.posix_fadvise(fd, 0, 0, os.POSIX_FADV_NOREUSE)
        os.posix_fadvise(fd, 0, 0, os.POSIX_FADV_WILLNEED)

simple_modules: list[PlayerModule] = []
playlist_modifier_modules: list[PlaylistModifierModule] = []
playlist_advisor: PlaylistAdvisor | None = None
active_modifier: ActiveModifier | None = None

MODULES_PACKAGE = "modules"
MODULES_DIR = Path(__file__, "..", MODULES_PACKAGE).resolve()

log_file_path = Path("/tmp/radioPlayer_log")
if log_file_path.exists(): log_file_path.unlink()
log_file_path.touch()
log_file = open(log_file_path, "w")
logger = log95.log95("CORE", output=log_file)

exit_pending = False
exit_status_code = 0
intr_time = 0
exit_lock = threading.Lock()

class ProcessManager(Skeleton_ProcessManager):
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.processes: list[Process] = []
        self.duration_cache = libcache.Cache([])
    def _get_audio_duration(self, file_path: Path):
        if result := self.duration_cache.getElement(file_path.as_posix(), False): return result

        result = subprocess.run(['ffprobe', '-v', 'quiet', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', str(file_path)], capture_output=True, text=True)
        if result.returncode == 0:
            result = float(result.stdout.strip())
            self.duration_cache.saveElement(file_path.as_posix(), result, (60*60), False, True)
            return result
        return None
    def play(self, track: Track, fade_time: int=5) -> Process:
        cmd = ['ffplay', '-nodisp', '-hide_banner', '-autoexit', '-loglevel', 'quiet']
        assert track.path.exists()

        duration = self._get_audio_duration(track.path.absolute())
        if not duration: raise Exception("Failed to get file duration for", track.path)
        if track.offset >= duration: track.offset = max(duration - 0.1, 0)
        if track.offset > 0: cmd.extend(['-ss', str(track.offset)])

        filters = []
        if track.fade_in: filters.append(f"afade=t=in:st=0:d={fade_time}")
        if track.fade_out: filters.append(f"afade=t=out:st={duration - fade_time - track.offset}:d={fade_time}")
        if filters: cmd.extend(['-af', ",".join(filters)])

        cmd.append(str(track.path.absolute()))

        pr = Process(Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True), track.path.name, time.monotonic(), duration - track.offset)
        with self.lock: self.processes.append(pr)
        return pr
    def anything_playing(self) -> bool:
        with self.lock:
            self.processes = [p for p in self.processes if p.process.poll() is None]
            return bool(self.processes)
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

procman = ProcessManager()

def handle_sigint(signum, frame):
    global exit_pending, intr_time, exit_status_code
    with exit_lock:
        logger.info("Received SIGINT")
        if (time.monotonic() - intr_time) > 5:
            intr_time = time.monotonic()
            logger.info("Will quit on song end.")
            exit_pending = True
            exit_status_code = 130
        else:
            logger.warning("Force-Quit pending")
            procman.stop_all()
            raise SystemExit(130)
signal.signal(signal.SIGINT, handle_sigint)

def load_filelines(path: Path):
    try:
       return [line.strip() for line in path.read_text().splitlines() if line.strip()]
    except FileNotFoundError:
        logger.error(f"Playlist not found: {path.name}")
        return []

def parse_playlistfile(playlist_path: Path) -> tuple[dict[str, str], list[tuple[list[str], dict[str, str]]]]:
    lines = load_filelines(playlist_path)
    def check_for_imports(lines: list[str], seen=None) -> list[str]:
        if seen is None: seen = set()
        out = []
        for line in lines:
            line = line.strip()
            if line.startswith("@"):
                target = Path(line.removeprefix("@"))
                if target not in seen:
                    if not target.exists():
                        logger.error(f"Target {target.name} of {playlist_path.name} does not exist")
                        continue
                    seen.add(target)
                    out.extend(check_for_imports(load_filelines(target), seen))
            else: out.append(line)
        return out
    lines = check_for_imports(lines) # First, import everything

    out = []
    global_arguments = {}
    for line in lines:
        arguments = {}
        line = line.strip()
        if not line or line.startswith(";") or line.startswith("#"): continue
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
        out.append(([f for f in glob.glob(line) if os.path.isfile(f)], arguments))
    return global_arguments, out

def play_playlist(playlist_path: Path, starting_index: int = 0):
    assert playlist_advisor

    try: global_args, parsed = parse_playlistfile(playlist_path)
    except Exception as e:
        logger.info(f"Exception ({e}) while parsing playlist, retrying in 15 seconds...")
        time.sleep(15)
        return

    playlist: list[Track] = []
    [playlist.extend(Track(Path(line).absolute(), True, True, True, args) for line in lns) for (lns, args) in parsed] # i can read this, i think

    for module in playlist_modifier_modules: playlist = module.modify(global_args, playlist) or playlist # id one liner this but the assignement is stopping me

    prefetch(playlist[0].path)

    [mod.on_new_playlist(playlist) for mod in simple_modules + [active_modifier] if mod] # one liner'd everything

    return_pending = False

    cross_fade = int(global_args.get("crossfade", 5))

    max_iterator = len(playlist)
    song_i = i = starting_index

    while i < max_iterator:
        if exit_pending:
            logger.info("Quit received, waiting for song end.")
            procman.wait_all()
            raise SystemExit(exit_status_code)
        elif return_pending:
            logger.info("Return reached, next song will reload the playlist.")
            procman.wait_all()
            return

        if playlist_advisor.new_playlist():
            logger.info("Reloading now...")
            return_pending = True
            continue

        track = playlist[song_i % len(playlist)]
        next_track = playlist[song_i + 1] if song_i + 1 < len(playlist) else None
        if active_modifier:
            (track, next_track), extend = active_modifier.play(song_i, track, next_track)
            if track is None:
                song_i += 1
                continue
            if extend: max_iterator += 1
        else: extend = False

        logger.info(f"Now playing: {track.path.name}")

        for module in simple_modules: module.on_new_track(song_i, track, next_track)

        pr = procman.play(track, cross_fade)

        ttw = pr.duration
        if track.fade_out: ttw -= cross_fade

        end_time = pr.started_at + ttw

        while end_time >= time.monotonic() and pr.process.poll() is None:
            start = time.monotonic()

            [module.progress(song_i, track, time.monotonic() - pr.started_at, pr.duration, ttw) for module in simple_modules if module]

            elapsed = time.monotonic() - start
            remaining_until_end = end_time - time.monotonic()
            if elapsed < 1 and remaining_until_end > 0: time.sleep(min(1 - elapsed, remaining_until_end))

        if next_track: prefetch(next_track.path)
    
        i += 1
        if not extend: song_i += 1

def main():
    logger.info("Core is starting, loading modules")
    global playlist_advisor, active_modifier
    modules: list[tuple] = []
    for file in MODULES_DIR.glob("*"):
        if file.name.endswith(".py") and file.name != "__init__.py":
            module_name = file.name[:-3]
            full_module_name = f"{MODULES_PACKAGE}.{module_name}"

            spec = importlib.util.spec_from_file_location(full_module_name, Path(MODULES_DIR, file))
            if not spec: continue
            module = importlib.util.module_from_spec(spec)

            sys.modules[full_module_name] = module

            if MODULES_PACKAGE not in sys.modules:
                parent = types.ModuleType(MODULES_PACKAGE)
                parent.__path__ = [str(MODULES_DIR)]
                parent.__package__ = MODULES_PACKAGE
                sys.modules[MODULES_PACKAGE] = parent
            module.__package__ = MODULES_PACKAGE

            module._log_file = log_file # type: ignore
            module.__dict__['_log_file'] = log_file
            modules.append((spec, module, module_name))
    
    for (spec, module, module_name) in modules:
        if not spec.loader: continue
        try: spec.loader.exec_module(module)
        except Exception as e:
            traceback.print_exc()
            logger.error(f"Failed loading {module_name} due to {e}")
            continue

        if md := getattr(module, "module", None):
            if isinstance(md, list): simple_modules.extend(md)
            else: simple_modules.append(md)
        if md := getattr(module, "playlistmod", None):
            if isinstance(md, tuple):
                md, index = md
                if isinstance(md, list): playlist_modifier_modules[index:index] = md
                else: playlist_modifier_modules.insert(index, md)
            elif isinstance(md, list): playlist_modifier_modules.extend(md)
            else: playlist_modifier_modules.append(md)
        if md := getattr(module, "advisor", None):
            if playlist_advisor: raise Exception("Multiple playlist advisors")
            playlist_advisor = md
        if md := getattr(module, "activemod", None):
            if active_modifier: raise Exception("Multiple active modifiers")
            active_modifier = md

    if not playlist_advisor:
        logger.critical_error("Playlist advisor was not found")
        raise SystemExit(1)

    InterModuleCommunication(simple_modules + [playlist_advisor, ProcmanCommunicator(procman), active_modifier])

    logger.info("Starting playback.")

    try:
        arg = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else None
        if active_modifier: active_modifier.arguments(arg)
        while True:
            if playlist := playlist_advisor.advise(arg):
                logger.info(f"Advisor picked '{playlist}' to play")
                play_playlist(playlist)
            if exit_pending: raise SystemExit(exit_status_code)
    except Exception as e:
        logger.critical_error(f"Unexpected error: {e}")
        raise
    finally: 
        procman.stop_all()
        log_file.close()
