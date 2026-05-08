from enum import Enum
import datetime, sys, os, io
from typing import LiteralString, TextIO
import syslog as sl

try:
    import colorama # type: ignore
    colorama.init()
except ModuleNotFoundError:
    print("log95: colorama is not installed.")

class log95Levels(Enum):
    DEBUG = 0
    VERBOSE = 1
    CRITICAL_ERROR = 2
    ERROR = 3
    WARN = 4
    INFO = 5

def level_to_syslog(level: log95Levels):
    match level:
        case log95Levels.DEBUG: return sl.LOG_DEBUG
        case log95Levels.VERBOSE: return sl.LOG_DEBUG
        case log95Levels.INFO: return sl.LOG_INFO
        case log95Levels.WARN: return sl.LOG_WARNING
        case log95Levels.ERROR: return sl.LOG_ERR
        case log95Levels.CRITICAL_ERROR: return sl.LOG_CRIT
        case _: return sl.LOG_NOTICE

class SyslogTextIO(io.TextIOWrapper):
    def syslog(self, level: log95Levels, message: str): sl.syslog(level_to_syslog(level), message)

class log95:
    def __init__(self, tag : str="...", level: log95Levels = log95Levels.CRITICAL_ERROR, output: TextIO | io.TextIOWrapper | SyslogTextIO = sys.stdout) -> None:
        self.tag = str(tag)
        self.level = int(level.value)
        self.output = output
    def log(self, level: log95Levels, *args:str, seperator=" ") -> None:
        we_have_color = "colorama" in sys.modules
        def level_to_str(_level: log95Levels, _color: bool) -> LiteralString | str:
            if _color:
                match _level:
                    case log95Levels.VERBOSE: return f"{colorama.Fore.LIGHTWHITE_EX}VERBOSE{colorama.Fore.RESET}"
                    case log95Levels.CRITICAL_ERROR: return f"{colorama.Fore.RED}CRITICAL{colorama.Fore.RESET}"
                    case log95Levels.ERROR: return f"{colorama.Fore.LIGHTRED_EX}ERROR{colorama.Fore.RESET}"
                    case log95Levels.WARN: return f"{colorama.Fore.YELLOW}WARN{colorama.Fore.RESET}"
                    case log95Levels.INFO: return f"{colorama.Fore.BLUE}INFO{colorama.Fore.RESET}"
                    case _: return _level.name
            else:
                match _level:
                    case log95Levels.CRITICAL_ERROR: return "CRITICAL"
                    case _: return _level.name
        if level.value > self.level: self.output.write(f"[{self.tag}] ({level_to_str(level, we_have_color)}) @ ({datetime.datetime.now().strftime('%d.%m.%Y %H:%M:%S.%f')}) - {seperator.join(args)}{os.linesep}")
        if isinstance(self.output, SyslogTextIO): self.output.syslog(level, seperator.join(args))
    def debug(self, *args:str, seperator=" ") -> None:
        self.log(log95Levels.DEBUG, *args, seperator)
    def verbose(self, *args:str, seperator=" ") -> None:
        self.log(log95Levels.VERBOSE, *args, seperator)
    def critical_error(self, *args:str, seperator=" ") -> None:
        self.log(log95Levels.CRITICAL_ERROR, *args, seperator)
    def error(self, *args:str, seperator=" ") -> None:
        self.log(log95Levels.ERROR, *args, seperator)
    def warning(self, *args:str, seperator=" ") -> None:
        self.log(log95Levels.WARN, *args, seperator)
    def info(self, *args:str, seperator=" ") -> None:
        self.log(log95Levels.INFO, *args, seperator)