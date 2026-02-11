#!/usr/bin/env python3
import time
import os
import sys
import termios
import tty
import signal
import shutil
import libcache
import argparse
from datetime import datetime
from typing import List, Dict, Set, Tuple, Optional
from dataclasses import dataclass, field
from pathlib import Path

# Configuration
FILES_DIR = Path("/home/user/mixes/")
PLAYLISTS_DIR = Path("/home/user/playlists/")
POLISH_INDICATORS = ("Polskie", "Dzem")

@dataclass
class InterfaceState:
    last_header: Optional[str] = None
    last_files_display: Optional[Tuple] = None
    last_selected_idx: int = -1
    last_current_day_idx: int = -1
    last_scroll_offset: int = -1
    last_message: Optional[str] = None
    last_search: str = ""

@dataclass
class Config:
    custom_playlist_file: Optional[str] = None

    @property
    def is_custom_mode(self) -> bool:
        return self.custom_playlist_file is not None

@dataclass
class FileItem:
    """Represents either a single file or a folder containing files."""
    name: str
    path: Path
    is_folder: bool
    _all_files_cache: Optional[Set[str]] = field(default=None, init=False, repr=False)

    @property
    def display_name(self) -> str:
        if self.is_folder:
            return f"📁 {self.name}/"
        return self.name

    @property
    def all_files(self) -> Set[str]:
        """Return set of relative paths for all files in this item."""
        if self._all_files_cache is not None:
            return self._all_files_cache
            
        if self.is_folder:
            # For folders, get all files inside
            folder_path = self.path.parent
            files = set()
            if folder_path.exists():
                for file in sorted(folder_path.glob("*")):
                    if file.is_file():
                        rel_path = str(file.relative_to(FILES_DIR))
                        files.add(rel_path)
            self._all_files_cache = files
            return files
        else:
            # For single files
            rel_path = str(self.path.relative_to(FILES_DIR))
            self._all_files_cache = {rel_path}
            return self._all_files_cache

class FileManager:
    @staticmethod
    def get_file_items(directory: Path) -> List[FileItem]:
        """Get all audio files and folders containing audio files as FileItem objects."""
        items = []
        try:
            for entry in sorted(directory.glob("*")):
                if entry.is_dir():
                    # Create folder item
                    item = FileItem(name=entry.name, path=entry / "*", is_folder=True)
                    items.append(item)
                elif entry.is_file():
                    # Create file item
                    item = FileItem(name=entry.name, path=entry, is_folder=False)
                    items.append(item)
            return items
        except FileNotFoundError:
            print(f"Error: Directory '{directory}' not found.")
            return []
        except PermissionError:
            print(f"Error: Permission denied for directory '{directory}'.")
            return []

class SearchManager:
    @staticmethod
    def filter_file_items(items: List[FileItem], search_term: str) -> List[FileItem]:
        if not search_term:
            return items

        search_lower = search_term.lower()

        # Group items by match type
        starts_with = []
        contains = []
        has_chars = []

        for item in items:
            item_name_lower = item.name.lower()

            if item_name_lower.startswith(search_lower):
                starts_with.append(item)
            elif search_lower in item_name_lower:
                contains.append(item)
            elif SearchManager._has_matching_chars(item_name_lower, search_lower):
                has_chars.append(item)

        return starts_with + contains + has_chars

    @staticmethod
    def filter_files(files: List[str], search_term: str) -> List[str]:
        if not search_term:
            return files

        search_lower = search_term.lower()

        starts_with = []
        contains = []
        has_chars = []

        for file in files:
            file_lower = file.lower()

            if file_lower.startswith(search_lower):
                starts_with.append(file)
            elif search_lower in file_lower:
                contains.append(file)
            elif SearchManager._has_matching_chars(file_lower, search_lower):
                has_chars.append(file)

        return starts_with + contains + has_chars

    @staticmethod
    def _has_matching_chars(text: str, search: str) -> bool:
        """Check if text contains all characters from search (in any order)."""
        search_chars = set(search)
        text_chars = set(text)
        return search_chars.issubset(text_chars)

class PlaylistManager:
    def __init__(self, config: Config):
        self.periods = ['late_night', 'morning', 'day', 'night']
        self.config = config
        self.custom_playlist_files = set()

    def ensure_playlist_dir(self, day: str) -> Path:
        """Ensure playlist directory exists for the given day."""
        playlist_dir = PLAYLISTS_DIR / day
        playlist_dir.mkdir(parents=True, exist_ok=True)
        return playlist_dir

    def load_playlists(self, days: List[str]) -> Dict[str, Dict[str, Set[str]]]:
        """Load all playlists from disk."""
        if self.config.is_custom_mode and self.config.custom_playlist_file:
            # In custom mode, we only need one "day" entry
            playlists = {"custom": {period: set() for period in self.periods}}
            # Load existing custom playlist if it exists
            custom_path = Path(self.config.custom_playlist_file)
            if custom_path.exists():
                with open(custom_path, 'r') as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            # Check if it's a directory pattern
                            if line.endswith("/*"):
                                # It's a directory pattern - expand it to individual files
                                dir_path = Path(line[:-2])  # Remove /*
                                if dir_path.exists():
                                    for file in sorted(dir_path.glob("*")):
                                        if file.is_file():
                                            try:
                                                rel_path = str(file.relative_to(FILES_DIR))
                                                self.custom_playlist_files.add(rel_path)
                                                playlists["custom"]["day"].add(rel_path)
                                            except ValueError:
                                                pass
                            else:
                                # Individual file
                                abs_path = Path(line)
                                try:
                                    rel_path = str(abs_path.relative_to(FILES_DIR))
                                except ValueError:
                                    # If it's already relative, use as is
                                    rel_path = line
                                
                                self.custom_playlist_files.add(rel_path)
                                playlists["custom"]["day"].add(rel_path)
            return playlists
        else:
            # Original functionality for weekly playlists
            playlists = {}
            for day in days:
                playlists[day] = {period: set() for period in self.periods}
                playlist_dir = PLAYLISTS_DIR / day

                if playlist_dir.exists():
                    for period in self.periods:
                        playlist_file = playlist_dir / period
                        if playlist_file.exists():
                            with open(playlist_file, 'r') as f:
                                for line in f:
                                    line = line.strip()
                                    if line:
                                        # Check if it's a directory pattern
                                        if line.endswith("/*"):
                                            # It's a directory pattern - expand it to individual files
                                            dir_path = Path(line[:-2])  # Remove /*
                                            if dir_path.exists():
                                                for file in sorted(dir_path.glob("*")):
                                                    if file.is_file():
                                                        try:
                                                            rel_path = str(file.relative_to(FILES_DIR))
                                                            playlists[day][period].add(rel_path)
                                                        except ValueError:
                                                            pass
                                        else:
                                            # Individual file
                                            abs_path = Path(line)
                                            try:
                                                rel_path = str(abs_path.relative_to(FILES_DIR))
                                            except ValueError:
                                                # If it's already relative, use as is
                                                rel_path = line
                                            playlists[day][period].add(rel_path)
            return playlists

    def update_playlist_file(self, day: str, period: str, file_item: FileItem, add: bool):
        """Update a playlist file by adding or removing files from a FileItem."""
        if self.config.is_custom_mode:
            self._update_custom_playlist(file_item, add)
        else:
            self._update_weekly_playlist(day, period, file_item, add)

    def _update_custom_playlist(self, file_item: FileItem, add: bool):
        """Update the custom playlist file."""
        if not self.config.custom_playlist_file:
            raise Exception("No custom playlist file specified")
        
        custom_path = Path(self.config.custom_playlist_file)
        custom_path.parent.mkdir(parents=True, exist_ok=True)

        # Read existing content
        lines = []
        if custom_path.exists():
            with open(custom_path, 'r') as f:
                lines = f.read().splitlines()

        if add:
            if file_item.is_folder:
                # For folders, write the directory pattern
                folder_path = file_item.path.parent
                dir_pattern = str(folder_path / "*")
                
                # Remove any individual files from this folder that might exist
                lines = [line for line in lines if not line.startswith(str(folder_path) + "/")]
                
                # Add the directory pattern if not already there
                if dir_pattern not in lines:
                    lines.append(dir_pattern)
                
                # Update tracking set with all files
                for rel_path in file_item.all_files:
                    self.custom_playlist_files.add(rel_path)
            else:
                # For individual files, add the file path
                abs_path = str(file_item.path)
                if abs_path not in lines:
                    lines.append(abs_path)
                
                # Update tracking set
                for rel_path in file_item.all_files:
                    self.custom_playlist_files.add(rel_path)
        else:
            if file_item.is_folder:
                # Remove directory pattern
                folder_path = file_item.path.parent
                dir_pattern = str(folder_path / "*")
                
                # Remove the pattern and any individual files from this folder
                lines = [line for line in lines if line != dir_pattern and not line.startswith(str(folder_path) + "/")]
                
                # Update tracking set
                for rel_path in file_item.all_files:
                    self.custom_playlist_files.discard(rel_path)
            else:
                # Remove individual file
                abs_path = str(file_item.path)
                while abs_path in lines:
                    lines.remove(abs_path)
                
                # Update tracking set
                for rel_path in file_item.all_files:
                    self.custom_playlist_files.discard(rel_path)

        with open(custom_path, 'w') as f:
            f.write('\n'.join(lines) + ('\n' if lines else ''))

    def _update_weekly_playlist(self, day: str, period: str, file_item: FileItem, add: bool):
        """Update a weekly playlist file."""
        playlist_dir = self.ensure_playlist_dir(day)
        playlist_file = playlist_dir / period

        if not playlist_file.exists():
            playlist_file.touch()

        with open(playlist_file, 'r') as f:
            lines = f.read().splitlines()

        if add:
            if file_item.is_folder:
                # For folders, write the directory pattern
                folder_path = file_item.path.parent
                dir_pattern = str(folder_path / "*")
                
                # Remove any individual files from this folder that might exist
                lines = [line for line in lines if not line.startswith(str(folder_path) + "/")]
                
                # Add the directory pattern if not already there
                if dir_pattern not in lines:
                    lines.append(dir_pattern)
            else:
                # For individual files, add the file path
                abs_path = str(file_item.path)
                if abs_path not in lines:
                    lines.append(abs_path)
        else:
            if file_item.is_folder:
                # Remove directory pattern
                folder_path = file_item.path.parent
                dir_pattern = str(folder_path / "*")
                
                # Remove the pattern and any individual files from this folder
                lines = [line for line in lines if line != dir_pattern and not line.startswith(str(folder_path) + "/")]
            else:
                # Remove individual file
                abs_path = str(file_item.path)
                while abs_path in lines:
                    lines.remove(abs_path)

        with open(playlist_file, 'w', encoding='utf-8', errors='strict') as f:
            for line in lines:
                try:
                    f.write(line + '\n')
                except UnicodeEncodeError as e:
                    print("⚠️ Encoding error in line:", repr(line))
                    time.sleep(5)
                    exit()

    def is_file_item_in_playlist(self, file_item: FileItem, day: str, period: str, playlists: Dict) -> bool:
        """Check if ALL files in the item are in the playlist."""
        playlist_set = playlists.get(day, {}).get(period, set())
        return all(rel_path in playlist_set for rel_path in file_item.all_files)

    def copy_day_to_all(self, playlists: Dict, source_day: str, days: List[str]) -> Dict:
        """Copy all playlists from source day to all other days."""
        if self.config.is_custom_mode:
            return playlists

        for target_day in days:
            if target_day == source_day:
                continue

            for period in self.periods:
                target_dir = self.ensure_playlist_dir(target_day)
                target_file = target_dir / period

                # Convert relative paths to absolute paths
                filepaths = [str(FILES_DIR / rel_path) 
                           for rel_path in playlists[source_day][period]]

                with open(target_file, 'w') as f:
                    f.write('\n'.join(filepaths) + ('\n' if filepaths else ''))

                playlists[target_day][period] = set(playlists[source_day][period])

        return playlists

    def copy_current_item_to_all(self, playlists: Dict, source_day: str,
                                days: List[str], current_item: FileItem) -> Tuple[Dict, bool]:
        """Copy current item's playlist assignments to all other days."""
        if self.config.is_custom_mode:
            # No-op in custom mode
            return playlists, False

        # Check which periods the item's files are in
        source_periods = {}
        for period in self.periods:
            source_periods[period] = self.is_file_item_in_playlist(current_item, source_day, period, playlists)

        for target_day in days:
            if target_day == source_day:
                continue

            for period, is_present in source_periods.items():
                target_set = playlists[target_day][period]

                # Get all relative paths for this item
                item_rel_paths = current_item.all_files

                if is_present:
                    # Add all files from the item
                    target_set.update(item_rel_paths)
                else:
                    # Remove all files from the item
                    for rel_path in item_rel_paths:
                        target_set.discard(rel_path)

                # Update the playlist file
                playlist_dir = self.ensure_playlist_dir(target_day)
                playlist_file = playlist_dir / period

                if playlist_file.exists():
                    with open(playlist_file, 'r') as f:
                        lines = [line.strip() for line in f.readlines()]
                else:
                    lines = []

                if is_present:
                    if current_item.is_folder:
                        # For folders, write the directory pattern
                        folder_path = current_item.path.parent
                        dir_pattern = str(folder_path / "*")
                        
                        # Remove any individual files from this folder
                        lines = [line for line in lines if not line.startswith(str(folder_path) + "/")]
                        
                        # Add the directory pattern
                        if dir_pattern not in lines:
                            lines.append(dir_pattern)
                    else:
                        # For individual files
                        abs_path = str(current_item.path)
                        if abs_path not in lines:
                            lines.append(abs_path)
                else:
                    if current_item.is_folder:
                        # Remove directory pattern and individual files
                        folder_path = current_item.path.parent
                        dir_pattern = str(folder_path / "*")
                        lines = [line for line in lines if line != dir_pattern and not line.startswith(str(folder_path) + "/")]
                    else:
                        # Remove individual file
                        abs_path = str(current_item.path)
                        while abs_path in lines:
                            lines.remove(abs_path)

                with open(playlist_file, 'w') as f:
                    f.write('\n'.join(lines) + ('\n' if lines else ''))

        return playlists, True

class TerminalUtils:
    @staticmethod
    def get_char() -> str:
        """Get a single character from stdin."""
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        try:
            tty.setraw(sys.stdin.fileno())
            ch = sys.stdin.read(1)
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        return ch

    @staticmethod
    def clear_screen():
        print("\033[2J\033[H", end="", flush=True)

    @staticmethod
    def move_cursor(row: int, col: int = 1):
        print(f"\033[{row};{col}H", end="", flush=True)

    @staticmethod
    def clear_line():
        print("\033[2K", end="", flush=True)

    @staticmethod
    def hide_cursor():
        print("\033[?25l", end="", flush=True)

    @staticmethod
    def show_cursor():
        print("\033[?25h", end="", flush=True)

    @staticmethod
    def get_terminal_size() -> os.terminal_size:
        return shutil.get_terminal_size()

class DateUtils:
    @staticmethod
    def get_days_of_week() -> List[str]:
        """Get days of the week starting from today."""
        days = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
        today = datetime.now().weekday()
        return days[today:] + days[:today]

class DisplayManager:
    def __init__(self, terminal_utils: TerminalUtils, config: Config):
        self.terminal = terminal_utils
        self.config = config

    def draw_header(self, current_day_idx: int,
                   days: List[str], term_width: int,
                   force_redraw: bool = False, state: InterfaceState | None = None):
        """Draw the header, only if content has changed."""
        if not state:
            raise Exception("State required")

        if self.config.is_custom_mode:
            # Custom mode header
            header_content = f"Custom Playlist: {self.config.custom_playlist_file}"
        else:
            header_content = " ".join([f"\033[1;44m[{day}]\033[0m" if i == current_day_idx else f"[{day}]" for i, day in enumerate(days)])

        # Optimization: Only redraw if content has changed or if forced
        if force_redraw or state.last_header != header_content:
            self.terminal.move_cursor(1)
            self.terminal.clear_line()
            print(header_content.center(term_width), end="", flush=True)

            state.last_header = header_content

    def draw_search_bar(self, search_term: str, force_redraw: bool = False,
                       state: InterfaceState | None = None):
        """Draw the search bar, only if the search term has changed."""
        if not state:
            raise Exception("State required")
        # Optimization: Only redraw if search term changes
        if force_redraw or state.last_search != search_term:
            self.terminal.move_cursor(4)
            self.terminal.clear_line()
            search_display = f"Search: {search_term}"
            print(f"\033[1;33m{search_display}\033[0m")
            state.last_search = search_term

    def draw_files_section(self, file_items: List[FileItem], playlists: Dict, selected_idx: int,
                          current_day: str, scroll_offset: int, term_width: int, term_height: int,
                          force_redraw: bool = False, state: InterfaceState | None = None):
        """Draw the files list, optimized to only redraw when necessary."""
        if not state:
            raise Exception("State required")
        available_lines = term_height - 6

        start_idx = scroll_offset
        end_idx = min(start_idx + available_lines, len(file_items))

        # Create a snapshot of the current state to compare against the last one
        files_display_state = (
            start_idx, end_idx, selected_idx, current_day,
            # We also need to know if the playlist data for the visible items has changed
            tuple(self._get_item_playlist_status(item, playlists, current_day) for item in file_items[start_idx:end_idx])
        )

        if force_redraw or state.last_files_display != files_display_state:

            # Position info line
            self.terminal.move_cursor(6)
            self.terminal.clear_line()

            if start_idx > 0:
                print("↑", end="")
            else:
                print(" ", end="")

            if self.config.is_custom_mode:
                position_info = f" Custom | Item {selected_idx + 1}/{len(file_items)} "
            else:
                position_info = f" {current_day.capitalize()} | Item {selected_idx + 1}/{len(file_items)} "
            padding = term_width - len(position_info) - 2
            print(position_info.center(padding), end="")

            if end_idx < len(file_items):
                print("↓", end="", flush=True)
            else:
                print(" ", end="", flush=True)

            # File list
            for display_row, idx in enumerate(range(start_idx, end_idx)):
                item = file_items[idx]
                line_row = 7 + display_row
                self.terminal.move_cursor(line_row)
                self.terminal.clear_line()

                if self.config.is_custom_mode:
                    # In custom mode, only show 'C' for custom playlist
                    in_custom = all(rel_path in playlists.get("custom", {}).get("day", set())
                                  for rel_path in item.all_files)
                    c_color = "\033[1;32m" if in_custom else "\033[1;30m"
                    row_highlight = "\033[1;44m" if idx == selected_idx else ""

                    max_filename_length = term_width - 6
                    display_name = item.display_name
                    if len(display_name) > max_filename_length:
                        display_name = display_name[:max_filename_length-3] + "..."

                    print(f"{row_highlight}[{c_color}C\033[0m{row_highlight}] {display_name}\033[0m", end="", flush=True)
                else:
                    # Original weekly mode display
                    in_late_night = all(rel_path in playlists[current_day]['late_night']
                                      for rel_path in item.all_files)
                    in_morning = all(rel_path in playlists[current_day]['morning']
                                   for rel_path in item.all_files)
                    in_day = all(rel_path in playlists[current_day]['day']
                               for rel_path in item.all_files)
                    in_night = all(rel_path in playlists[current_day]['night']
                                 for rel_path in item.all_files)

                    l_color = "\033[1;32m" if in_late_night else "\033[1;30m"
                    m_color = "\033[1;32m" if in_morning else "\033[1;30m"
                    d_color = "\033[1;32m" if in_day else "\033[1;30m"
                    n_color = "\033[1;32m" if in_night else "\033[1;30m"

                    row_highlight = "\033[1;44m" if idx == selected_idx else ""

                    max_filename_length = term_width - 15
                    display_name = item.display_name
                    if len(display_name) > max_filename_length:
                        display_name = display_name[:max_filename_length-3] + "..."

                    print(f"{row_highlight}[{l_color}L\033[0m{row_highlight}] [{m_color}M\033[0m{row_highlight}] [{d_color}D\033[0m{row_highlight}] [{n_color}N\033[0m{row_highlight}] {display_name}\033[0m", end="", flush=True)

            # Clear remaining lines
            last_end_idx = state.last_files_display[1] if state.last_files_display else 0
            if end_idx < last_end_idx:
                 for i in range(end_idx, last_end_idx):
                    self.terminal.move_cursor(7 + (i - start_idx))
                    self.terminal.clear_line()

            state.last_files_display = files_display_state

    def _get_item_playlist_status(self, item: FileItem, playlists: Dict, current_day: str) -> Tuple:
        """Get playlist status for an item to use in display state comparison."""
        if self.config.is_custom_mode:
            return (all(rel_path in playlists.get("custom", {}).get("day", set())
                       for rel_path in item.all_files),)
        else:
            return (
                all(rel_path in playlists[current_day]['late_night'] for rel_path in item.all_files),
                all(rel_path in playlists[current_day]['morning'] for rel_path in item.all_files),
                all(rel_path in playlists[current_day]['day'] for rel_path in item.all_files),
                all(rel_path in playlists[current_day]['night'] for rel_path in item.all_files)
            )

class Application:
    def __init__(self, config: Config):
        self.config = config
        self.file_manager = FileManager()
        self.search_manager = SearchManager()
        self.playlist_manager = PlaylistManager(config)
        self.terminal = TerminalUtils()
        self.display = DisplayManager(self.terminal, config)
        self.terminal_cache = libcache.Cache()
        self.state = InterfaceState()

        # Application state
        self.selected_idx = 0
        self.current_day_idx = 0
        self.scroll_offset = 0
        self.flash_message = None
        self.message_timer = 0
        self.search_term = ""
        self.in_search_mode = False

        # Data
        self.all_file_items = []
        self.filtered_file_items = []
        self.playlists = {}
        self.days_of_week = []

        self.redraw = False

    def setup_signal_handler(self):
        """Setup signal handler for graceful exit."""
        def signal_handler(sig, frame):
            self.terminal.show_cursor()
            self.terminal.clear_screen()
            sys.exit(0)

        signal.signal(signal.SIGINT, signal_handler)

    def initialize_data(self):
        """Initialize application data."""
        self.all_file_items = self.file_manager.get_file_items(FILES_DIR)
        if not self.all_file_items:
            print("No audio files or folders found. Exiting.")
            return False

        self.filtered_file_items = self.all_file_items.copy()

        if self.config.is_custom_mode:
            self.days_of_week = ["custom"]  # Single "day" for custom mode
        else:
            self.days_of_week = DateUtils.get_days_of_week()

        self.playlists = self.playlist_manager.load_playlists(self.days_of_week)
        return True

    def update_search(self, new_search: str):
        """Update search term and filter file items."""
        self.search_term = new_search
        self.filtered_file_items = self.search_manager.filter_file_items(self.all_file_items, self.search_term)

        # Reset selection if current selection is not in filtered results
        if self.selected_idx >= len(self.filtered_file_items):
            self.selected_idx = max(0, len(self.filtered_file_items) - 1)
        elif self.filtered_file_items and self.selected_idx < len(self.filtered_file_items):
            # Keep current item selected if it's still in results
            current_item = self.all_file_items[self.selected_idx] if self.selected_idx < len(self.all_file_items) else None
            if current_item and current_item in self.filtered_file_items:
                self.selected_idx = self.filtered_file_items.index(current_item)
            else:
                self.selected_idx = 0

    def draw_interface(self, force_redraw: bool = False):
        """Draw the complete interface."""
        term_width, term_height = self.terminal_cache.getElement("width", False), self.terminal_cache.getElement("height", False)
        if term_width is None or term_height is None:
            term_width, term_height = self.terminal.get_terminal_size()
            self.terminal_cache.saveElement("width", term_width, 5, False, True)
            self.terminal_cache.saveElement("height", term_height, 5, False, True)
            force_redraw = True

        current_day = self.days_of_week[self.current_day_idx]

        if force_redraw:
            self.terminal.clear_screen()
            self.terminal.hide_cursor()

            # Draw static elements

            self.terminal.move_cursor(2)
            if self.config.is_custom_mode:
                print("UP/DOWN: Navigate | C: Toggle | /: Search | Q: Quit", end="", flush=True)
            else:
                print("UP/DOWN: Navigate | D/N/L/M: Toggle | C: Copy day | F: Copy item | /: Search | Q: Quit", end="", flush=True)

            self.terminal.move_cursor(3)
            print("ESC: Exit search | ENTER: Apply search", end="", flush=True)

        # Draw header
        self.display.draw_header(self.current_day_idx,
                               self.days_of_week, term_width, force_redraw, self.state)

        # Draw search bar
        self.display.draw_search_bar(self.search_term, force_redraw, self.state)

        # Draw files section
        self.display.draw_files_section(self.filtered_file_items, self.playlists, self.selected_idx,
                                      current_day, self.scroll_offset, term_width, term_height,
                                      force_redraw, self.state)

        # Handle message display
        if self.flash_message != self.state.last_message:
            self.terminal.move_cursor(6)
            self.terminal.clear_line()
            if self.flash_message:
                print(f"\033[1;32m{self.flash_message}\033[0m", end="", flush=True)
            self.state.last_message = self.flash_message

    def handle_navigation_key(self, key: str):
        """Handle navigation keys."""
        term_width, term_height = self.terminal_cache.getElement("width", False), self.terminal_cache.getElement("height", False)
        if term_width is None or term_height is None:
            term_width, term_height = self.terminal.get_terminal_size()

        visible_lines = term_height - 6

        if key == 'A':  # Up arrow
            self.selected_idx = max(0, self.selected_idx - 1)
        elif key == 'B':  # Down arrow
            self.selected_idx = min(len(self.filtered_file_items) - 1, self.selected_idx + 1)
        elif key == 'C' and not self.config.is_custom_mode:  # Right arrow (disabled in custom mode)
            self.current_day_idx = (self.current_day_idx + 1) % len(self.days_of_week)
        elif key == 'D' and not self.config.is_custom_mode:  # Left arrow (disabled in custom mode)
            self.current_day_idx = (self.current_day_idx - 1) % len(self.days_of_week)
        elif key == '5':  # Page Up
            self.selected_idx = max(0, self.selected_idx - visible_lines)
        elif key == '6':  # Page Down
            self.selected_idx = min(len(self.filtered_file_items) - 1, self.selected_idx + visible_lines)
        elif key == '1':  # Home
            self.selected_idx = 0
        elif key == '4':  # End
            self.selected_idx = len(self.filtered_file_items) - 1

    def toggle_playlist(self, period: str):
        """Toggle current file item in specified playlist period."""
        if not self.filtered_file_items:
            return

        current_day = self.days_of_week[self.current_day_idx]
        file_item = self.filtered_file_items[self.selected_idx]

        if self.config.is_custom_mode:
            # In custom mode, all operations work with the "day" period
            is_in_playlist = self.playlist_manager.is_file_item_in_playlist(file_item, "custom", "day", self.playlists)

            if is_in_playlist:
                # Remove all files from the item
                for rel_path in file_item.all_files:
                    self.playlists["custom"]["day"].discard(rel_path)
            else:
                # Add all files from the item
                self.playlists["custom"]["day"].update(file_item.all_files)

            self.playlist_manager.update_playlist_file("custom", "day", file_item, not is_in_playlist)
        else:
            # Original weekly mode
            is_in_playlist = self.playlist_manager.is_file_item_in_playlist(file_item, current_day, period, self.playlists)

            if is_in_playlist:
                # Remove all files from the item
                for rel_path in file_item.all_files:
                    self.playlists[current_day][period].discard(rel_path)
            else:
                # Add all files from the item
                self.playlists[current_day][period].update(file_item.all_files)

            self.playlist_manager.update_playlist_file(current_day, period, file_item, not is_in_playlist)
        
        self.redraw = True

    def handle_search_input(self, key: str):
        """Handle search input."""
        if key == '\x7f' or key == '\x08':  # Backspace
            if self.search_term:
                self.search_term = self.search_term[:-1]
                self.update_search(self.search_term)
        elif key == '\r' or key == '\n':  # Enter
            self.in_search_mode = False
        elif key == '\x1b':  # Escape
            self.search_term = ""
            self.update_search(self.search_term)
            self.in_search_mode = False
        elif key.isprintable() and len(self.search_term) < 50:
            self.search_term += key
            self.update_search(self.search_term)

    def run(self):
        """Main application loop."""
        if not self.initialize_data():
            return 1

        self.setup_signal_handler()

        # Initial draw
        self.draw_interface(force_redraw=True)

        try:
            while True:
                # Update scroll offset
                term_width, term_height = self.terminal_cache.getElement("width", False), self.terminal_cache.getElement("height", False)
                if term_width is None or term_height is None:
                    term_width, term_height = self.terminal.get_terminal_size()

                visible_lines = term_height - 6

                if self.selected_idx < self.scroll_offset:
                    self.scroll_offset = self.selected_idx
                elif self.selected_idx >= self.scroll_offset + visible_lines:
                    self.scroll_offset = self.selected_idx - visible_lines + 1

                # Check if redraw is needed
                needs_redraw = (
                    self.state.last_selected_idx != self.selected_idx or
                    self.state.last_current_day_idx != self.current_day_idx or
                    self.state.last_scroll_offset != self.scroll_offset or
                    self.flash_message != self.state.last_message or
                    self.state.last_search != self.search_term or
                    self.redraw
                )

                if needs_redraw:
                    self.draw_interface()
                    self.state.last_selected_idx = self.selected_idx
                    self.state.last_current_day_idx = self.current_day_idx
                    self.state.last_scroll_offset = self.scroll_offset
                    if self.redraw: self.redraw = False

                # Handle flash message timer
                if self.flash_message:
                    self.message_timer += 1
                    if self.message_timer > 1:
                        self.flash_message = None
                        self.message_timer = 0

                # Get input
                key = self.terminal.get_char()

                # Handle search mode
                if self.in_search_mode:
                    self.handle_search_input(key)
                    continue

                # Handle regular input
                if key == 'q':
                    break
                elif key == '/':
                    self.in_search_mode = True
                elif key == '\x1b':  # Escape sequences
                    next_key = self.terminal.get_char()
                    if next_key == '[':
                        arrow_key = self.terminal.get_char()
                        self.handle_navigation_key(arrow_key)
                        if arrow_key in ['5', '6', '1', '4']:
                            try:
                                self.terminal.get_char()  # Consume the ~ character
                            except:
                                pass
                elif key == ' ':
                    self.selected_idx = min(len(self.filtered_file_items) - 1, self.selected_idx + (term_height - 6))
                elif key.lower() == 'c':
                    if self.config.is_custom_mode:
                        # In custom mode, 'c' toggles the custom playlist
                        self.toggle_playlist('day')
                    else:
                        # In weekly mode, 'c' copies day to all
                        current_day = self.days_of_week[self.current_day_idx]
                        self.playlists = self.playlist_manager.copy_day_to_all(self.playlists, current_day, self.days_of_week)
                        self.flash_message = f"Playlists from {current_day} copied to all other days!"
                        self.message_timer = 0
                elif key.lower() == 'm' and not self.config.is_custom_mode:
                    self.toggle_playlist('morning')
                elif key.lower() == 'd' and not self.config.is_custom_mode:
                    self.toggle_playlist('day')
                elif key.lower() == 'n' and not self.config.is_custom_mode:
                    self.toggle_playlist('night')
                elif key.lower() == 'l' and not self.config.is_custom_mode:
                    self.toggle_playlist('late_night')
                elif key.lower() == 'f' and not self.config.is_custom_mode:
                    if self.filtered_file_items:
                        current_day = self.days_of_week[self.current_day_idx]
                        current_item = self.filtered_file_items[self.selected_idx]

                        self.playlists, success = self.playlist_manager.copy_current_item_to_all(self.playlists, current_day, self.days_of_week, current_item)

                        if success:
                            item_name = current_item.display_name
                            self.flash_message = f"Item '{item_name}' copied to all days!"
                        else:
                            self.flash_message = f"Item not in any playlist! Add it first."
                        self.message_timer = 0
                elif key.isupper() and len(key) == 1 and key.isalpha():
                    # Jump to item starting with letter
                    target_letter = key.lower()
                    found_idx = -1
                    for i in range(self.selected_idx + 1, len(self.filtered_file_items)):
                        if self.filtered_file_items[i].name.lower().startswith(target_letter):
                            found_idx = i
                            break
                    if found_idx == -1:
                        for i in range(0, self.selected_idx):
                            if self.filtered_file_items[i].name.lower().startswith(target_letter):
                                found_idx = i
                                break
                    if found_idx != -1:
                        self.selected_idx = found_idx

        finally:
            self.terminal.show_cursor()
            self.terminal.clear_screen()

        return 0


def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Audio Playlist Manager",
        prog="radioPlaylist"
    )
    parser.add_argument(
        "-p", "--playlist",
        type=str,
        help="Custom playlist output file (e.g., /tmp/list.txt)"
    )
    return parser.parse_args()


def main():
    """Main entry point."""
    args = parse_arguments()

    fd = sys.stdin.fileno()
    original_settings = termios.tcgetattr(fd)

    new_settings = termios.tcgetattr(fd)
    new_settings[3] = new_settings[3] & ~termios.ECHOCTL
    termios.tcsetattr(fd, termios.TCSADRAIN, new_settings)

    config = Config(custom_playlist_file=args.playlist)
    app = Application(config)
    code = app.run()
    termios.tcsetattr(fd, termios.TCSADRAIN, original_settings)
    exit(code)


if __name__ == "__main__":
    main()