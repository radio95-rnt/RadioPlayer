#!/usr/bin/env python3
import os, subprocess, importlib.util, importlib.machinery, types
import sys, signal, glob, time, traceback
import libcache
from modules import *
from threading import Lock

def prefetch(path):
    if os.name == "posix":
        with open(path, "rb") as f:
            fd = f.fileno()
            os.posix_fadvise(fd, 0, 0, os.POSIX_FADV_SEQUENTIAL)
            os.posix_fadvise(fd, 0, 0, os.POSIX_FADV_NOREUSE)
            os.posix_fadvise(fd, 0, 0, os.POSIX_FADV_WILLNEED)

MODULES_PACKAGE = "modules"
MODULES_DIR = Path(__file__, "..", MODULES_PACKAGE).resolve()

class ProcessManager(ABC_ProcessManager):
    def __init__(self) -> None:
        self.lock = Lock()
        self.processes: list[Process] = []
        self.duration_cache = libcache.Cache([])
    def _get_audio_duration(self, file_path: Path):
        if result := self.duration_cache.getElement(file_path.as_posix(), False): return result
        result = subprocess.run(['ffprobe', '-v', 'quiet', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', str(file_path)], capture_output=True, text=True)
        if result.returncode == 0:
            result = float(result.stdout.strip())
            self.duration_cache.saveElement(file_path.as_posix(), result, (60*60*2), False, True)
            return result
    def play(self, track: Track) -> Process:
        assert track.path.exists()
        cmd = ['ffplay', '-nodisp', '-hide_banner', '-autoexit', '-loglevel', 'quiet']

        duration = self._get_audio_duration(track.path.absolute())
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

class PlaylistParser:
    def __init__(self, output: log95.TextIO): self.logger = log95.log95("PARSER", output=output)

    def _check_for_imports(self, path: Path, seen=None) -> list[str]:
        if seen is None: seen = set()
        if not path.exists():
            self.logger.error(f"Playlist not found: {path.name}")
            return []
        lines = [line.strip() for line in path.read_text().splitlines() if line.strip()]

        out = []
        for line in lines:
            if line.startswith("@"):
                target = Path(line.removeprefix("@"))
                if target not in seen:
                    if not target.exists():
                        self.logger.error(f"Target {target.name} of {path.name} does not exist")
                        continue
                    seen.add(target)
                    out.extend(self._check_for_imports(target, seen))
            else: out.append(line)
        return out

    def parse(self, playlist_path: Path) -> tuple[dict[str, str], list[tuple[list[str], dict[str, str]]]]:
        lines = self._check_for_imports(playlist_path)
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
            out.append(([f for f in glob.glob(line) if Path(f).is_file()], arguments))
        return global_arguments, out

class ModuleManager:
    def __init__(self, output: log95.TextIO) -> types.NoneType:
        self.simple_modules: list[PlayerModule] = []
        self.playlist_modifier_modules: list[PlaylistModifierModule] = []
        self.playlist_advisor: PlaylistAdvisor | None = None
        self.active_modifier: ActiveModifier | None = None
        self.modules: list[tuple[importlib.machinery.ModuleSpec, types.ModuleType, str]] = []
        self.logger = log95.log95("MODULES", output=output)
    def shutdown_modules(self) -> None:
        for module in self.simple_modules:
            if module:
                try: module.shutdown()
                except BaseException: traceback.print_exc(file=self.logger.output)
    def load_modules(self):
        """Loads the modules into memory"""
        for file in MODULES_DIR.glob("*"):
            if file.name.endswith(".py") and file.name != "__init__.py":
                module_name = file.name[:-3]
                full_module_name = f"{MODULES_PACKAGE}.{module_name}"

                spec = importlib.util.spec_from_file_location(full_module_name, Path(MODULES_DIR, file))
                module = importlib.util.module_from_spec(spec) if spec else None
                assert spec and module

                sys.modules[full_module_name] = module
                if MODULES_PACKAGE not in sys.modules:
                    parent = types.ModuleType(MODULES_PACKAGE)
                    parent.__path__ = [str(MODULES_DIR)]
                    parent.__package__ = MODULES_PACKAGE
                    sys.modules[MODULES_PACKAGE] = parent
                module.__package__ = MODULES_PACKAGE

                module._log_out = self.logger.output # type: ignore
                module.__dict__['_log_out'] = self.logger.output
                self.modules.append((spec, module, module_name))
    def start_modules(self, arg):
        """Executes the module by the python interpreter"""
        procman = ProcessManager()
        for (spec, module, module_name) in self.modules:
            assert spec.loader
            try:
                start = time.perf_counter()
                if sys.platform == "linux":
                    def handler(signum, frame): raise TimeoutError("Module loading timed out")
                    signal.signal(signal.SIGALRM, handler)
                    signal.alarm(5)
                try: spec.loader.exec_module(module)
                except TimeoutError: self.logger.error(f"Module {module_name} took too long to load and was skipped.")
                finally:
                    if sys.platform == "linux": signal.alarm(0)
                if (time_took := time.perf_counter() - start) > 0.15: self.logger.warning(f"{module_name} took {time_took:.1f}s to start")
            except Exception as e:
                traceback.print_exc(file=self.logger.output)
                self.logger.error(f"Failed loading {module_name} due to {e}, continuing")
                continue

            if md := getattr(module, "module", None):
                if isinstance(md, list): self.simple_modules.extend(md)
                else: self.simple_modules.append(md)
            if md := getattr(module, "playlistmod", None):
                if isinstance(md, tuple):
                    md, index = md
                    if isinstance(md, list): self.playlist_modifier_modules[index:index] = md
                    else: self.playlist_modifier_modules.insert(index, md)
                elif isinstance(md, list): self.playlist_modifier_modules.extend(md)
                else: self.playlist_modifier_modules.append(md)
            if md := getattr(module, "advisor", None):
                if self.playlist_advisor: raise Exception("Multiple playlist advisors")
                self.playlist_advisor = md
            if md := getattr(module, "activemod", None):
                if self.active_modifier: raise Exception("Multiple active modifiers")
                self.active_modifier = md
            if md := getattr(module, "procman", None):
                if not isinstance(md, ABC_ProcessManager):
                    self.logger.error("Modular process manager does not inherit from ABC_ProcessManager.")
                    continue
                if procman.anything_playing(): procman.stop_all()
                procman = md
        InterModuleCommunication(self.simple_modules + [self.playlist_advisor, ProcmanCommunicator(procman), self.active_modifier])
        if self.active_modifier: self.active_modifier.arguments(arg)
        return procman

class RadioPlayer:
    def __init__(self, arg: str | None, output: log95.TextIO):
        self.exit_pending = False
        self.exit_status_code = self.intr_time = 0
        self.exit_lock = Lock()
        self.parser = PlaylistParser(output)
        self.procman: ABC_ProcessManager | None = None
        self.arg = arg
        self.logger = log95.log95("CORE", output=output)
        self.modman = ModuleManager(output)

    def shutdown(self):
        if self.procman: self.procman.stop_all()
        self.modman.shutdown_modules()
        self.logger.output.close()

    def handle_sigint(self, signum: int, frame: types.FrameType | None):
        with self.exit_lock:
            self.logger.info("Received CTRL+C (SIGINT)")
            if (now := time.monotonic()) and ((now - self.intr_time) > 5):
                self.intr_time = now
                self.logger.info("Will quit on song end.")
                self.exit_pending, self.exit_status_code = True, 130
            else:
                self.logger.warning("Force-Quit pending")
                raise SystemExit(130)

    def start(self):
        """Single functon for starting the core, returns but might exit raising an SystemExit"""
        self.logger.info("Core starting, loading modules")
        self.modman.load_modules()
        self.procman = self.modman.start_modules(self.arg)
        if not self.modman.playlist_advisor: self.logger.warning("Playlist advisor was not found. Beta mode of advisor-less is running (playlist modifiers will not work)")

    def play_once(self):
        """Plays a single playlist"""
        if self.modman.playlist_advisor:
            if not (playlist_path := self.modman.playlist_advisor.advise(self.arg)): return
            try: global_args, parsed = self.parser.parse(playlist_path)
            except Exception as e:
                self.logger.info(f"Exception ({e}) while parsing playlist, retrying in 15 seconds...");traceback.print_exc(file=self.logger.output)
                time.sleep(15)
                return

            playlist: list[Track] | None = []
            [playlist.extend(Track(Path(line).absolute(), 0, 0, True, args) for line in lns) for (lns, args) in parsed] # i can read this, i think

            [(playlist := module.modify(global_args, playlist) or playlist) for module in self.modman.playlist_modifier_modules if module] # yep
            assert len(playlist)

            prefetch(playlist[0].path)
            [mod.on_new_playlist(playlist, global_args) for mod in self.modman.simple_modules + [self.modman.active_modifier] if mod] # one liner'd everything

            max_iterator = len(playlist)
        else:
            max_iterator = 1
            playlist = None
        return_pending = track = False
        song_i = i = 0
        assert self.procman

        def get_track():
            nonlocal song_i, playlist, max_iterator
            track = None
            while track is None:
                if playlist:
                    playlist_track = playlist[song_i % len(playlist)]
                    playlist_next_track = playlist[song_i + 1] if song_i + 1 < len(playlist) else None
                else: playlist_track = playlist_next_track = None
                if self.modman.active_modifier:
                    (track, next_track), extend = self.modman.active_modifier.play(song_i, playlist_track, playlist_next_track)
                    if track is None: song_i += 1
                    if extend and track: max_iterator += 1
                else:
                    track = playlist_track
                    next_track = playlist_next_track
                    extend = False
            return track, next_track, extend

        def check_conditions():
            nonlocal return_pending
            assert self.procman
            if self.exit_pending:
                self.logger.info("Quit received, waiting for song end.")
                self.procman.wait_all()
                raise SystemExit(self.exit_status_code)
            elif return_pending:
                self.logger.info("Return reached, next song will reload the playlist.")
                self.procman.wait_all()
                return True
            if self.modman.playlist_advisor and self.modman.playlist_advisor.new_playlist():
                self.logger.info("Reloading now...")
                return True
            return False

        track, next_track, extend = get_track()
        while i < max_iterator:
            if check_conditions(): return

            self.logger.info(f"Now playing: {track.path.name}")
            prefetch(track.path)

            pr = self.procman.play(track)
            [module.on_new_track(song_i, pr.track, next_track) for module in self.modman.simple_modules if module]
            end_time = pr.started_at + pr.duration + pr.track.focus_time_offset

            while end_time >= time.monotonic() and pr.process.poll() is None:
                start = time.monotonic()
                [module.progress(song_i, track, time.monotonic() - pr.started_at, pr.duration, end_time - pr.started_at) for module in self.modman.simple_modules if module]
                if (elapsed := time.monotonic() - start) < 1 and (remaining_until_end := end_time - time.monotonic()) > 0: time.sleep(min(1 - elapsed, remaining_until_end))

            i += 1
            if not extend: song_i += 1

            if check_conditions(): return
            track, next_track, extend = get_track()
            prefetch(track.path)

    def loop(self):
        """Main loop of the player. This does not return and may or not raise an SystemExit"""
        try:
            while True:
                self.play_once()
                if self.exit_pending: raise SystemExit(self.exit_status_code)
        except Exception:
            traceback.print_exc(file=self.logger.output)
            raise

def main():
    log_file_path = Path("/tmp/radioPlayer_log")
    log_file_path.touch()

    core = RadioPlayer((" ".join(sys.argv[1:]) if len(sys.argv) > 1 else None), open(log_file_path, "w"))
    try:
        core.start()
        signal.signal(signal.SIGINT, core.handle_sigint)
        core.loop()
    except SystemExit:
        try: core.shutdown()
        except BaseException: traceback.print_exc()
        raise