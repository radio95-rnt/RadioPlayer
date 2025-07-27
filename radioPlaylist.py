#!/usr/bin/env python3
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
from dataclasses import dataclass

# Configuration
FILES_DIR = "/home/user/mixes/"
PLAYLISTS_DIR = "/home/user/playlists/"
FORMATS = ('.mp3', '.m4a')
POLISH_INDICATORS = ("Polskie", "Dzem")

@dataclass
class InterfaceState:
    last_header: Optional[Tuple] = None
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

class FileManager:
    @staticmethod
    def get_audio_files(directory: str) -> List[str]:
        """Get all audio files from the specified directory."""
        audio_files = []
        try:
            for file in os.listdir(directory):
                if file.lower().endswith(FORMATS):
                    audio_files.append(file)
            return sorted(audio_files)
        except FileNotFoundError:
            print(f"Error: Directory '{directory}' not found.")
            return []
        except PermissionError:
            print(f"Error: Permission denied for directory '{directory}'.")
            return []

class SearchManager:
    @staticmethod
    def filter_files(files: List[str], search_term: str) -> List[str]:
        """Filter and sort files based on search term."""
        if not search_term:
            return files
        
        search_lower = search_term.lower()
        
        # Group files by match type
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
        
        # Return sorted results: starts_with first, then contains, then has_chars
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
    
    def ensure_playlist_dir(self, day: str) -> str:
        """Ensure playlist directory exists for the given day."""
        playlist_dir = os.path.expanduser(os.path.join(PLAYLISTS_DIR, day))
        if not os.path.exists(playlist_dir):
            os.makedirs(playlist_dir)
        return playlist_dir
    
    def load_playlists(self, days: List[str]) -> Dict[str, Dict[str, Set[str]]]:
        """Load all playlists from disk."""
        if self.config.is_custom_mode:
            # In custom mode, we only need one "day" entry
            playlists = {"custom": {period: set() for period in self.periods}}
            # Load existing custom playlist if it exists
            if os.path.exists(self.config.custom_playlist_file):
                with open(self.config.custom_playlist_file, 'r') as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            filename = os.path.basename(line)
                            self.custom_playlist_files.add(filename)
                            # In custom mode, we'll use 'day' as the default period for display
                            playlists["custom"]["day"].add(filename)
            return playlists
        else:
            # Original functionality for weekly playlists
            playlists = {}
            for day in days:
                playlists[day] = {period: set() for period in self.periods}
                playlist_dir = os.path.expanduser(os.path.join(PLAYLISTS_DIR, day))
                
                if os.path.exists(playlist_dir):
                    for period in self.periods:
                        playlist_file = os.path.join(playlist_dir, period)
                        if os.path.exists(playlist_file):
                            with open(playlist_file, 'r') as f:
                                for line in f:
                                    line = line.strip()
                                    if line:
                                        filename = os.path.basename(line)
                                        playlists[day][period].add(filename)
            return playlists
    
    def update_playlist_file(self, day: str, period: str, filepath: str, add: bool):
        """Update a playlist file by adding or removing a file."""
        if self.config.is_custom_mode:
            self._update_custom_playlist(filepath, add)
        else:
            self._update_weekly_playlist(day, period, filepath, add)
    
    def _update_custom_playlist(self, filepath: str, add: bool):
        """Update the custom playlist file."""
        full_filepath = os.path.join(FILES_DIR, filepath)
        
        # Ensure the directory exists
        os.makedirs(os.path.dirname(self.config.custom_playlist_file), exist_ok=True)
        
        # Read existing content
        lines = []
        if os.path.exists(self.config.custom_playlist_file):
            with open(self.config.custom_playlist_file, 'r') as f:
                lines = f.read().splitlines()
        
        if add and full_filepath not in lines:
            lines.append(full_filepath)
            self.custom_playlist_files.add(filepath)
        elif not add and full_filepath in lines:
            lines.remove(full_filepath)
            self.custom_playlist_files.discard(filepath)
        
        # Write back to file
        with open(self.config.custom_playlist_file, 'w') as f:
            f.write('\n'.join(lines) + ('\n' if lines else ''))
    
    def _update_weekly_playlist(self, day: str, period: str, filepath: str, add: bool):
        """Update a weekly playlist file (original functionality)."""
        playlist_dir = self.ensure_playlist_dir(day)
        playlist_file = os.path.join(playlist_dir, period)
        full_filepath = os.path.join(FILES_DIR, filepath)
        
        if not os.path.exists(playlist_file):
            with open(playlist_file, 'w') as f:
                pass
        
        with open(playlist_file, 'r') as f:
            lines = f.read().splitlines()
        
        if add and full_filepath not in lines:
            lines.append(full_filepath)
        elif not add and full_filepath in lines:
            lines.remove(full_filepath)
        
        with open(playlist_file, 'w') as f:
            f.write('\n'.join(lines) + ('\n' if lines else ''))
    
    def copy_day_to_all(self, playlists: Dict, source_day: str, days: List[str]) -> Dict:
        """Copy all playlists from source day to all other days."""
        if self.config.is_custom_mode:
            # No-op in custom mode
            return playlists
            
        for target_day in days:
            if target_day == source_day:
                continue
            
            for period in self.periods:
                target_dir = self.ensure_playlist_dir(target_day)
                target_file = os.path.join(target_dir, period)
                
                filepaths = [os.path.join(FILES_DIR, filename) 
                           for filename in playlists[source_day][period]]
                
                with open(target_file, 'w') as f:
                    f.write('\n'.join(filepaths) + ('\n' if filepaths else ''))
                
                playlists[target_day][period] = set(playlists[source_day][period])
        
        return playlists
    
    def copy_current_file_to_all(self, playlists: Dict, source_day: str, 
                                days: List[str], current_file: str) -> Tuple[Dict, bool]:
        """Copy current file's playlist assignments to all other days."""
        if self.config.is_custom_mode:
            # No-op in custom mode
            return playlists, False
            
        source_periods = {
            period: current_file in playlists[source_day][period]
            for period in self.periods
        }
        
        if not any(source_periods.values()):
            return playlists, False
        
        for target_day in days:
            if target_day == source_day:
                continue
            
            for period, is_present in source_periods.items():
                target_set = playlists[target_day][period]
                full_path = os.path.join(FILES_DIR, current_file)
                
                if is_present:
                    target_set.add(current_file)
                else:
                    target_set.discard(current_file)
                
                playlist_dir = self.ensure_playlist_dir(target_day)
                playlist_file = os.path.join(playlist_dir, period)
                
                if os.path.exists(playlist_file):
                    with open(playlist_file, 'r') as f:
                        lines = [line.strip() for line in f.readlines()]
                else:
                    lines = []
                
                if is_present and full_path not in lines:
                    lines.append(full_path)
                elif not is_present:
                    while full_path in lines:
                        lines.remove(full_path)
                
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

class StatsCalculator:
    @staticmethod
    def calculate_category_percentages(playlists: Dict, current_day: str, config: Config) -> Optional[Tuple]:
        """Calculate category distribution percentages."""
        if config.is_custom_mode:
            # In custom mode, show simple stats
            custom_files = playlists.get("custom", {}).get("day", set())
            total_files = len(FileManager.get_audio_files(FILES_DIR))
            assigned_count = len(custom_files)
            
            if total_files == 0:
                return None
                
            assigned_percent = (assigned_count / total_files) * 100
            polskie_count = sum(1 for file in custom_files if any(element in file for element in POLISH_INDICATORS))
            polskie_percent = (polskie_count / assigned_count) * 100 if assigned_count > 0 else 0
            
            return {"custom": assigned_percent}, {"custom": polskie_percent}, polskie_percent
        
        # Original weekly mode calculation
        periods = ['late_night', 'morning', 'day', 'night']
        category_counts = {period: 0 for period in periods}
        polskie_counts = {period: 0 for period in periods}
        
        for period in periods:
            for file in playlists[current_day][period]:
                category_counts[period] += 1
                if any(element in file for element in POLISH_INDICATORS):
                    polskie_counts[period] += 1
        
        total_count = sum(category_counts.values())
        if total_count == 0:
            return None
        
        percentages = {
            period: (count / total_count) * 100 
            for period, count in category_counts.items()
        }
        
        polskie_percentages = {
            period: (polskie_counts[period] / category_counts[period]) * 100 
            if category_counts[period] > 0 else 0
            for period in periods
        }
        
        total_pl = (sum(polskie_counts.values()) / sum(category_counts.values())) * 100
        
        return percentages, polskie_percentages, total_pl

class DateUtils:
    @staticmethod
    def get_days_of_week() -> List[str]:
        """Get days of the week starting from today."""
        days = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
        today = datetime.now().weekday()
        return days[today:] + days[:today]

class DisplayManager:
    def __init__(self, terminal_utils: TerminalUtils, stats_calc: StatsCalculator, config: Config):
        self.terminal = terminal_utils
        self.stats = stats_calc
        self.config = config
    
    def draw_header(self, playlists: Dict, current_day: str, current_day_idx: int, 
                   days: List[str], term_width: int, force_redraw: bool = False, 
                   state: InterfaceState = None):
        """Draw the header with category distribution and day navigation."""
        result = self.stats.calculate_category_percentages(playlists, current_day, self.config)
        percentages, polskie_percentages, total_pl = result or ({}, {}, 0)
        
        if self.config.is_custom_mode:
            # Custom mode header - simpler display
            category_bar = f"Custom Playlist: {self.config.custom_playlist_file} | "
            custom_percent = percentages.get("custom", 0)
            polskie_percent = polskie_percentages.get("custom", 0)
            category_bar += f"Selected: {custom_percent:.1f}% | Polish: {polskie_percent:.1f}%"
            
            if len(category_bar) > term_width - 2:
                category_bar = category_bar[:term_width - 5] + "..."
            
            header_content = (category_bar, "")  # No day bar in custom mode
        else:
            # Original weekly mode header
            category_bar = ""
            for category in ['late_night', 'morning', 'day', 'night']:
                percent = percentages.get(category, 0)
                polskie_percent = polskie_percentages.get(category, 0)
                category_bar += f"{category[:4].capitalize()}: {percent:.1f}% (P:{polskie_percent:.1f}%) | "
            category_bar += f"TP:{total_pl:0.1f}% | "
            
            # Calculate unassigned files
            assigned_files = set()
            periods = ['late_night', 'morning', 'day', 'night']
            days_of_week = DateUtils.get_days_of_week()
            for day in days_of_week:
                for period in periods:
                    assigned_files.update(playlists[day][period])
            
            total_files = len(FileManager.get_audio_files(FILES_DIR))
            assigned_count = len(assigned_files)
            unassigned = ((total_files - assigned_count) / total_files) * 100 if total_files > 0 else 0
            category_bar += f"UA:{unassigned:0.1f}%"
            
            if len(category_bar) > term_width - 2:
                category_bar = category_bar[:term_width - 5] + "..."
            
            # Day bar
            day_bar = ""
            for i, day in enumerate(days):
                if i == current_day_idx:
                    day_bar += f"\033[1;44m[{day}]\033[0m "
                else:
                    day_bar += f"[{day}] "
            
            header_content = (category_bar, day_bar.strip())
        
        if force_redraw or (state and state.last_header != header_content):
            self.terminal.move_cursor(1)
            self.terminal.clear_line()
            if self.config.is_custom_mode:
                print("\033[1;37mCustom Playlist Mode:\033[0m".center(term_width), end="", flush=True)
            else:
                print("\033[1;37mCategory Distribution:\033[0m".center(term_width), end="", flush=True)
            
            self.terminal.move_cursor(2)
            self.terminal.clear_line()
            print(header_content[0].center(term_width), end="", flush=True)
            
            if not self.config.is_custom_mode:
                self.terminal.move_cursor(3)
                self.terminal.clear_line()
                print(header_content[1], end="", flush=True)
            
            if state:
                state.last_header = header_content
    
    def get_header_height(self) -> int:
        """Get the height of the header section."""
        return 2 if self.config.is_custom_mode else 3
    
    def draw_search_bar(self, search_term: str, term_width: int, force_redraw: bool = False,
                       state: InterfaceState = None):
        """Draw the search bar."""
        search_row = self.get_header_height() + 3  # After header + keybinds
        
        if force_redraw or (state and state.last_search != search_term):
            self.terminal.move_cursor(search_row)
            self.terminal.clear_line()
            search_display = f"Search: {search_term}"
            if len(search_display) > term_width - 2:
                search_display = search_display[:term_width - 5] + "..."
            print(f"\033[1;33m{search_display}\033[0m", end="", flush=True)
            
            if state:
                state.last_search = search_term
    
    def draw_files_section(self, audio_files: List[str], playlists: Dict, selected_idx: int, 
                          current_day: str, scroll_offset: int, term_width: int, term_height: int,
                          force_redraw: bool = False, state: InterfaceState = None):
        """Draw the files list section."""
        header_height = self.get_header_height()
        available_lines = 4 + header_height  # header + keybinds + search + position + message
        start_idx = max(0, min(scroll_offset, len(audio_files) - available_lines))
        end_idx = min(start_idx + available_lines, len(audio_files))
        
        files_display_state = (start_idx, end_idx, selected_idx, current_day)
        
        if force_redraw or (state and (state.last_files_display != files_display_state or 
                                      state.last_selected_idx != selected_idx)):
            
            # Position info line
            position_row = header_height + 4
            self.terminal.move_cursor(position_row)
            self.terminal.clear_line()
            
            if start_idx > 0:
                print("↑", end="")
            else:
                print(" ", end="")
            
            if self.config.is_custom_mode:
                position_info = f" Custom | File {selected_idx + 1}/{len(audio_files)} "
            else:
                position_info = f" {current_day.capitalize()} | File {selected_idx + 1}/{len(audio_files)} "
            padding = term_width - len(position_info) - 2
            print(position_info.center(padding), end="")
            
            if end_idx < len(audio_files):
                print("↓", end="", flush=True)
            else:
                print(" ", end="", flush=True)
            
            # File list
            for display_row, idx in enumerate(range(start_idx, end_idx)):
                file = audio_files[idx]
                line_row = header_height + 6 + display_row
                
                if self.config.is_custom_mode:
                    # In custom mode, only show 'C' for custom playlist
                    in_custom = file in playlists.get("custom", {}).get("day", set())
                    c_color = "\033[1;32m" if in_custom else "\033[1;30m"
                    row_highlight = "\033[1;44m" if idx == selected_idx else ""
                    
                    max_filename_length = term_width - 6
                    display_file = file
                    if len(file) > max_filename_length:
                        display_file = file[:max_filename_length-3] + "..."
                    
                    self.terminal.move_cursor(line_row)
                    self.terminal.clear_line()
                    print(f"{row_highlight}[{c_color}C\033[0m{row_highlight}] {display_file}\033[0m", end="", flush=True)
                else:
                    # Original weekly mode display
                    in_late_night = file in playlists[current_day]['late_night']
                    in_morning = file in playlists[current_day]['morning']
                    in_day = file in playlists[current_day]['day']
                    in_night = file in playlists[current_day]['night']
                    
                    l_color = "\033[1;32m" if in_late_night else "\033[1;30m"
                    m_color = "\033[1;32m" if in_morning else "\033[1;30m"
                    d_color = "\033[1;32m" if in_day else "\033[1;30m"
                    n_color = "\033[1;32m" if in_night else "\033[1;30m"
                    
                    row_highlight = "\033[1;44m" if idx == selected_idx else ""
                    
                    max_filename_length = term_width - 15
                    display_file = file
                    if len(file) > max_filename_length:
                        display_file = file[:max_filename_length-3] + "..."
                    
                    self.terminal.move_cursor(line_row)
                    self.terminal.clear_line()
                    print(f"{row_highlight}[{l_color}L\033[0m{row_highlight}] [{m_color}M\033[0m{row_highlight}] [{d_color}D\033[0m{row_highlight}] [{n_color}N\033[0m{row_highlight}] {display_file}\033[0m", end="", flush=True)
            
            # Clear remaining lines
            for clear_row in range(header_height + 6 + (end_idx - start_idx), term_height):
                self.terminal.move_cursor(clear_row)
                self.terminal.clear_line()
            
            if state:
                state.last_files_display = files_display_state
                state.last_selected_idx = selected_idxbar[:term_width - 5] + "..."
        
        # Day bar
        day_bar = ""
        for i, day in enumerate(days):
            if i == current_day_idx:
                day_bar += f"\033[1;44m[{day}]\033[0m "
            else:
                day_bar += f"[{day}] "
        
        header_content = (category_bar, day_bar.strip())
        
        if force_redraw or (state and state.last_header != header_content):
            self.terminal.move_cursor(1)
            self.terminal.clear_line()
            print("\033[1;37mCategory Distribution:\033[0m".center(term_width), end="", flush=True)
            
            self.terminal.move_cursor(2)
            self.terminal.clear_line()
            print(category_bar.center(term_width), end="", flush=True)
            
            self.terminal.move_cursor(3)
            self.terminal.clear_line()
            print(day_bar.strip(), end="", flush=True)
            
            if state:
                state.last_header = header_content
    
    def draw_search_bar(self, search_term: str, term_width: int, force_redraw: bool = False,
                       state: InterfaceState = None):
        """Draw the search bar."""
        if force_redraw or (state and state.last_search != search_term):
            self.terminal.move_cursor(self.get_header_height() + 3)
            self.terminal.clear_line()
            search_display = f"Search: {search_term}"
            if len(search_display) > term_width - 2:
                search_display = search_display[:term_width - 5] + "..."
            print(f"\033[1;33m{search_display}\033[0m", end="", flush=True)
            
            if state:
                state.last_search = search_term
    
    def draw_files_section(self, audio_files: List[str], playlists: Dict, selected_idx: int, 
                          current_day: str, scroll_offset: int, term_width: int, term_height: int,
                          force_redraw: bool = False, state: InterfaceState = None):
        """Draw the files list section."""
        available_lines = term_height - 4 - self.get_header_height()  # Adjusted for search bar
        start_idx = max(0, min(scroll_offset, len(audio_files) - available_lines))
        end_idx = min(start_idx + available_lines, len(audio_files))
        
        files_display_state = (start_idx, end_idx, selected_idx, current_day)
        
        if force_redraw or (state and (state.last_files_display != files_display_state or 
                                      state.last_selected_idx != selected_idx)):
            
            # Position info line
            self.terminal.move_cursor(7)
            self.terminal.clear_line()
            
            if start_idx > 0:
                print("↑", end="")
            else:
                print(" ", end="")
            
            position_info = f" {current_day.capitalize()} | File {selected_idx + 1}/{len(audio_files)} "
            padding = term_width - len(position_info) - 2
            print(position_info.center(padding), end="")
            
            if end_idx < len(audio_files):
                print("↓", end="", flush=True)
            else:
                print(" ", end="", flush=True)
            
            # File list
            for display_row, idx in enumerate(range(start_idx, end_idx)):
                file = audio_files[idx]
                line_row = 4 + display_row + self.get_header_height()  # Start after header and search
                
                in_late_night = file in playlists[current_day]['late_night']
                in_morning = file in playlists[current_day]['morning']
                in_day = file in playlists[current_day]['day']
                in_night = file in playlists[current_day]['night']
                
                l_color = "\033[1;32m" if in_late_night else "\033[1;30m"
                m_color = "\033[1;32m" if in_morning else "\033[1;30m"
                d_color = "\033[1;32m" if in_day else "\033[1;30m"
                n_color = "\033[1;32m" if in_night else "\033[1;30m"
                
                row_highlight = "\033[1;44m" if idx == selected_idx else ""
                
                max_filename_length = term_width - 15
                display_file = file
                if len(file) > max_filename_length:
                    display_file = file[:max_filename_length-3] + "..."
                
                self.terminal.move_cursor(line_row)
                self.terminal.clear_line()
                if not self.config.is_custom_mode: print(f"{row_highlight}[{l_color}L\033[0m{row_highlight}] [{m_color}M\033[0m{row_highlight}] [{d_color}D\033[0m{row_highlight}] [{n_color}N\033[0m{row_highlight}] {display_file}\033[0m", end="", flush=True)
                else: print(f"{row_highlight}[{d_color}C\033[0m{row_highlight}] {display_file}\033[0m", end="", flush=True)
            
            # Clear remaining lines
            for clear_row in range(9 + (end_idx - start_idx), term_height):
                self.terminal.move_cursor(clear_row)
                self.terminal.clear_line()
            
            if state:
                state.last_files_display = files_display_state
                state.last_selected_idx = selected_idx

class Application:
    def __init__(self, config: Config):
        self.config = config
        self.file_manager = FileManager()
        self.search_manager = SearchManager()
        self.playlist_manager = PlaylistManager(config)
        self.terminal = TerminalUtils()
        self.stats = StatsCalculator()
        self.display = DisplayManager(self.terminal, self.stats, config)
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
        self.all_audio_files = []
        self.filtered_files = []
        self.playlists = {}
        self.days_of_week = []
    
    def setup_signal_handler(self):
        """Setup signal handler for graceful exit."""
        def signal_handler(sig, frame):
            self.terminal.show_cursor()
            self.terminal.clear_screen()
            sys.exit(0)
        
        signal.signal(signal.SIGINT, signal_handler)
    
    def initialize_data(self):
        """Initialize application data."""
        self.all_audio_files = self.file_manager.get_audio_files(FILES_DIR)
        if not self.all_audio_files:
            print("No audio files found. Exiting.")
            return False
        
        self.filtered_files = self.all_audio_files.copy()
        
        if self.config.is_custom_mode:
            self.days_of_week = ["custom"]  # Single "day" for custom mode
        else:
            self.days_of_week = DateUtils.get_days_of_week()
        
        self.playlists = self.playlist_manager.load_playlists(self.days_of_week)
        return True
    
    def update_search(self, new_search: str):
        """Update search term and filter files."""
        self.search_term = new_search
        self.filtered_files = self.search_manager.filter_files(self.all_audio_files, self.search_term)
        
        # Reset selection if current selection is not in filtered results
        if self.selected_idx >= len(self.filtered_files):
            self.selected_idx = max(0, len(self.filtered_files) - 1)
        elif self.filtered_files and self.selected_idx < len(self.filtered_files):
            # Keep current file selected if it's still in results
            current_file = self.all_audio_files[self.selected_idx] if self.selected_idx < len(self.all_audio_files) else None
            if current_file and current_file in self.filtered_files:
                self.selected_idx = self.filtered_files.index(current_file)
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
            header_height = self.display.get_header_height()
            keybind_row = header_height + 1
            
            self.terminal.move_cursor(keybind_row)
            if self.config.is_custom_mode:
                print("UP/DOWN: Navigate | C: Toggle | /: Search | Q: Quit", end="", flush=True)
            else:
                print("UP/DOWN: Navigate | D/N/L/M: Toggle | C: Copy day | F: Copy file | /: Search | Q: Quit", end="", flush=True)
            
            self.terminal.move_cursor(keybind_row + 1)
            print("ESC: Exit search | ENTER: Apply search", end="", flush=True)
        
        # Draw header
        self.display.draw_header(self.playlists, current_day, self.current_day_idx, 
                               self.days_of_week, term_width, force_redraw, self.state)
        
        # Draw search bar
        self.display.draw_search_bar(self.search_term, term_width, force_redraw, self.state)
        
        # Draw files section
        self.display.draw_files_section(self.filtered_files, self.playlists, self.selected_idx,
                                      current_day, self.scroll_offset, term_width, term_height,
                                      force_redraw, self.state)
        
        # Handle message display
        if self.flash_message != self.state.last_message:
            message_row = self.display.get_header_height() + 5
            self.terminal.move_cursor(message_row)
            self.terminal.clear_line()
            if self.flash_message:
                print(f"\033[1;32m{self.flash_message}\033[0m", end="", flush=True)
            self.state.last_message = self.flash_message
    
    def handle_navigation_key(self, key: str):
        """Handle navigation keys."""
        term_width, term_height = self.terminal_cache.getElement("width", False), self.terminal_cache.getElement("height", False)
        if term_width is None or term_height is None:
            term_width, term_height = self.terminal.get_terminal_size()
        
        header_height = self.display.get_header_height()
        visible_lines = term_height - (header_height + 5)
        
        if key == 'A':  # Up arrow
            self.selected_idx = max(0, self.selected_idx - 1)
        elif key == 'B':  # Down arrow
            self.selected_idx = min(len(self.filtered_files) - 1, self.selected_idx + 1)
        elif key == 'C' and not self.config.is_custom_mode:  # Right arrow (disabled in custom mode)
            self.current_day_idx = (self.current_day_idx + 1) % len(self.days_of_week)
        elif key == 'D' and not self.config.is_custom_mode:  # Left arrow (disabled in custom mode)
            self.current_day_idx = (self.current_day_idx - 1) % len(self.days_of_week)
        elif key == '5':  # Page Up
            self.selected_idx = max(0, self.selected_idx - visible_lines)
        elif key == '6':  # Page Down
            self.selected_idx = min(len(self.filtered_files) - 1, self.selected_idx + visible_lines)
        elif key == '1':  # Home
            self.selected_idx = 0
        elif key == '4':  # End
            self.selected_idx = len(self.filtered_files) - 1
    
    def toggle_playlist(self, period: str):
        """Toggle current file in specified playlist period."""
        if not self.filtered_files:
            return
        
        current_day = self.days_of_week[self.current_day_idx]
        file = self.filtered_files[self.selected_idx]
        
        if self.config.is_custom_mode:
            # In custom mode, all operations work with the "day" period
            is_in_playlist = file in self.playlists["custom"]["day"]
            
            if is_in_playlist:
                self.playlists["custom"]["day"].remove(file)
            else:
                self.playlists["custom"]["day"].add(file)
            
            self.playlist_manager.update_playlist_file("custom", "day", file, not is_in_playlist)
        else:
            # Original weekly mode
            is_in_playlist = file in self.playlists[current_day][period]
            
            if is_in_playlist:
                self.playlists[current_day][period].remove(file)
            else:
                self.playlists[current_day][period].add(file)
            
            self.playlist_manager.update_playlist_file(current_day, period, file, not is_in_playlist)
    
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
                
                header_height = self.display.get_header_height()
                visible_lines = term_height - (header_height + 4)
                
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
                    self.state.last_search != self.search_term
                )
                
                if needs_redraw:
                    self.draw_interface()
                    self.state.last_current_day_idx = self.current_day_idx
                    self.state.last_scroll_offset = self.scroll_offset
                
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
                    header_height = self.display.get_header_height()
                    visible_lines = term_height - (header_height + 5)
                    self.selected_idx = min(len(self.filtered_files) - 1, self.selected_idx + visible_lines)
                elif key.lower() == 'c':
                    if self.config.is_custom_mode:
                        # In custom mode, 'c' toggles the custom playlist
                        self.toggle_playlist('day')
                    else:
                        # In weekly mode, 'c' copies day to all
                        current_day = self.days_of_week[self.current_day_idx]
                        self.playlists = self.playlist_manager.copy_day_to_all(
                            self.playlists, current_day, self.days_of_week)
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
                    if self.filtered_files:
                        current_day = self.days_of_week[self.current_day_idx]
                        current_file = self.filtered_files[self.selected_idx]
                        
                        self.playlists, success = self.playlist_manager.copy_current_file_to_all(
                            self.playlists, current_day, self.days_of_week, current_file)
                        
                        if success:
                            self.flash_message = f"File '{current_file}' copied to all days!"
                        else:
                            self.flash_message = f"File not in any playlist! Add it first."
                        self.message_timer = 0
                elif key.isupper() and len(key) == 1 and key.isalpha():
                    # Jump to file starting with letter
                    target_letter = key.lower()
                    found_idx = -1
                    for i in range(self.selected_idx + 1, len(self.filtered_files)):
                        if self.filtered_files[i].lower().startswith(target_letter):
                            found_idx = i
                            break
                    if found_idx == -1:
                        for i in range(0, self.selected_idx):
                            if self.filtered_files[i].lower().startswith(target_letter):
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
    
    config = Config(custom_playlist_file=args.playlist)
    app = Application(config)
    return app.run()


if __name__ == "__main__":
    exit(main())