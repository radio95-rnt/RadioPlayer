#!/usr/bin/env python3
import os
import sys
import termios
import tty
import signal
import shutil
from datetime import datetime

def get_audio_files(directory):
    """Get all mp3 and m4a files from the specified directory"""
    audio_files = []
    try:
        for file in os.listdir(directory):
            if file.lower().endswith(('.mp3', '.m4a')):
                audio_files.append(file)
        return sorted(audio_files)
    except FileNotFoundError:
        print(f"Error: Directory '{directory}' not found.")
        return []
    except PermissionError:
        print(f"Error: Permission denied for directory '{directory}'.")
        return []

def get_char():
    """Get a single character from standard input"""
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setraw(sys.stdin.fileno())
        ch = sys.stdin.read(1)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
    return ch

def clear_screen():
    """Clear the terminal screen"""
    print("\033c", end="")

def get_terminal_size():
    """Get the current terminal size"""
    return shutil.get_terminal_size()

def get_days_of_week():
    """Get list of days of the week starting from today"""
    days = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    today = datetime.now().weekday()  # 0 is Monday, 6 is Sunday
    # Reorder days so today is first
    return days[today:] + days[:today]

def ensure_playlist_dir(day):
    """Ensure playlist directory exists for the given day"""
    playlist_dir = os.path.expanduser(f"~/playlists/{day}")
    if not os.path.exists(playlist_dir):
        os.makedirs(playlist_dir)
    return playlist_dir

def update_playlist_file(day, period, filepath, add):
    """Add or remove a file from a playlist"""
    # Ensure day directory exists
    playlist_dir = ensure_playlist_dir(day)
    playlist_file = os.path.join(playlist_dir, period)
    
    # Get full path of the audio file
    full_filepath = os.path.join("/home/user/mixes", filepath)
    
    # Create file if it doesn't exist
    if not os.path.exists(playlist_file):
        with open(playlist_file, 'w') as f:
            pass
    
    # Read current playlist content
    with open(playlist_file, 'r') as f:
        lines = f.read().splitlines()
    
    # Add or remove file
    if add and full_filepath not in lines:
        lines.append(full_filepath)
    elif not add and full_filepath in lines:
        lines.remove(full_filepath)
    
    # Write updated playlist back to file
    with open(playlist_file, 'w') as f:
        f.write('\n'.join(lines) + ('\n' if lines else ''))

def load_playlists(days):
    """Load existing playlists for all days"""
    playlists = {}
    for day in days:
        playlists[day] = {'day': set(), 'night': set(), 'late_night': set()}
        playlist_dir = os.path.expanduser(f"~/playlists/{day}")
        
        if os.path.exists(playlist_dir):
            for period in ['day', 'night', 'late_night']:
                playlist_file = os.path.join(playlist_dir, period)
                if os.path.exists(playlist_file):
                    with open(playlist_file, 'r') as f:
                        for line in f:
                            line = line.strip()
                            if line:
                                # Extract filename only
                                filename = os.path.basename(line)
                                playlists[day][period].add(filename)
    
    return playlists

def copy_day_to_all(playlists, source_day, days, audio_files):
    """Copy playlists from source day to all other days"""
    periods = ['day', 'night', 'late_night']
    
    for target_day in days:
        if target_day == source_day:
            continue
            
        for period in periods:
            # Clear target day's period playlist
            target_dir = ensure_playlist_dir(target_day)
            target_file = os.path.join(target_dir, period)
            
            # Get files to write
            filepaths = []
            for filename in playlists[source_day][period]:
                full_path = os.path.join("/home/user/mixes", filename)
                filepaths.append(full_path)
            
            # Update the target playlist file
            with open(target_file, 'w') as f:
                f.write('\n'.join(filepaths) + ('\n' if filepaths else ''))
            
            # Update the playlists dictionary to match
            playlists[target_day][period] = set(playlists[source_day][period])
    
    return playlists

def copy_current_file_to_all(playlists, source_day, days, current_file):
    """Sync current file's presence in all days based on source_day's state"""
    # Get the source day's state for each period
    source_periods = {
        'day': current_file in playlists[source_day]['day'],
        'night': current_file in playlists[source_day]['night'],
        'late_night': current_file in playlists[source_day]['late_night']
    }
    
    # If file isn't in any playlist of the source day, return
    if not any(source_periods.values()):
        return playlists, False
    
    # Sync to all other days
    for target_day in days:
        if target_day == source_day:
            continue
        
        for period, is_present in source_periods.items():
            target_set = playlists[target_day][period]
            full_path = os.path.join("/home/user/mixes", current_file)
            
            # Update the in-memory playlist
            if is_present:
                target_set.add(current_file)
            else:
                target_set.discard(current_file)
            
            # Update the physical file
            playlist_dir = ensure_playlist_dir(target_day)
            playlist_file = os.path.join(playlist_dir, period)
            
            # Read existing content
            if os.path.exists(playlist_file):
                with open(playlist_file, 'r') as f:
                    lines = [line.strip() for line in f.readlines()]
            else:
                lines = []
            
            # Add or remove the file
            if is_present and full_path not in lines:
                lines.append(full_path)
            elif not is_present:
                while full_path in lines:
                    lines.remove(full_path)
            
            # Write updated content
            with open(playlist_file, 'w') as f:
                f.write('\n'.join(lines) + ('\n' if lines else ''))
    
    return playlists, True

def draw_interface(audio_files, playlists, selected_idx, current_day_idx, scroll_offset, message=None):
    """Draw the TUI interface with day-of-week sections"""
    clear_screen()
    term_width, term_height = get_terminal_size()
    days = get_days_of_week()
    current_day = days[current_day_idx]
    
    # Calculate visible range with scrolling
    available_lines = term_height - 5  # Header + status lines + message + footer
    start_idx = max(0, min(scroll_offset, len(audio_files) - available_lines))
    end_idx = min(start_idx + available_lines, len(audio_files))
    
    # Day navigation bar
    day_bar = ""
    for i, day in enumerate(days):
        if i == current_day_idx:
            day_bar += f"\033[1;44m[{day}]\033[0m "
        else:
            day_bar += f"[{day}] "
    print(day_bar.strip())
    
    # Controls and info line
    print(f"UP/DOWN: Navigate | D/N/L: Toggle | C: Copy day to all | F: Copy file to all | Q: Quit")
    
    # Display scroll indicators if needed
    if start_idx > 0:
        print("↑", end="")
    else:
        print(" ", end="")
    
    # Display position info in the middle
    position_info = f" {current_day.capitalize()} | File {selected_idx + 1}/{len(audio_files)} "
    padding = term_width - len(position_info) - 2  # 2 for scroll indicators
    print(position_info.center(padding), end="")
    
    # Display scroll indicator if more files below
    if end_idx < len(audio_files):
        print("↓")
    else:
        print(" ")
    
    # Display message if provided
    if message:
        print(f"\033[1;32m{message}\033[0m")
    else:
        print()  # Empty line for consistent spacing
    
    # Display visible files
    for idx in range(start_idx, end_idx):
        file = audio_files[idx]
        
        # Check if file is in playlists
        in_day = file in playlists[current_day]['day']
        in_night = file in playlists[current_day]['night']
        in_late_night = file in playlists[current_day]['late_night']
        
        d_color = "\033[1;32m" if in_day else "\033[1;30m"
        n_color = "\033[1;32m" if in_night else "\033[1;30m"
        l_color = "\033[1;32m" if in_late_night else "\033[1;30m"
        
        # Row highlighting for current selection
        if idx == selected_idx:
            row_highlight = "\033[1;44m"  # Blue background
        else:
            row_highlight = ""
        
        # Truncate filename if too long for the terminal width
        max_filename_length = term_width - 15  # Account for the selector buttons and spacing
        if len(file) > max_filename_length:
            file = file[:max_filename_length-3] + "..."
        
        print(f"{row_highlight}[{d_color}D\033[0m{row_highlight}] [{n_color}N\033[0m{row_highlight}] [{l_color}L\033[0m{row_highlight}] {file}\033[0m")

def main():
    """Main function to run the TUI"""
    directory = "/home/user/mixes"
    audio_files = get_audio_files(directory)
    
    if not audio_files:
        print("No audio files found. Exiting.")
        return
    
    days_of_week = get_days_of_week()
    playlists = load_playlists(days_of_week)
    
    selected_idx = 0  # Currently selected file index
    current_day_idx = 0  # Currently displayed day (0 = today)
    scroll_offset = 0  # Starting scroll position
    flash_message = None  # Message to display
    message_timer = 0  # Timer to clear the message
    
    # Handle Ctrl+C gracefully
    def signal_handler(sig, frame):
        clear_screen()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    
    # Main loop
    while True:
        term_width, term_height = get_terminal_size()
        visible_lines = term_height - 5  # Adjust for header, message and footer
        
        # Adjust scroll offset to keep selected item visible
        if selected_idx < scroll_offset:
            scroll_offset = selected_idx
        elif selected_idx >= scroll_offset + visible_lines:
            scroll_offset = selected_idx - visible_lines + 1
        
        # Draw the interface
        draw_interface(audio_files, playlists, selected_idx, current_day_idx, scroll_offset, flash_message)
        
        # Clear message after a short time (faster)
        if flash_message:
            message_timer += 1
            if message_timer > 1:  # Clear after 2 renders (faster)
                flash_message = None
                message_timer = 0
        
        # Get user input
        key = get_char()
        
        if key == 'q':  # Quit
            clear_screen()
            break
        elif key == '\x1b':  # Escape sequence for arrow keys
            next_key = get_char()
            if next_key == '[':
                arrow_key = get_char()
                if arrow_key == 'A':  # Up arrow
                    selected_idx = max(0, selected_idx - 1)
                elif arrow_key == 'B':  # Down arrow
                    selected_idx = min(len(audio_files) - 1, selected_idx + 1)
                elif arrow_key == 'C':  # Right arrow - next day
                    current_day_idx = (current_day_idx + 1) % len(days_of_week)
                elif arrow_key == 'D':  # Left arrow - previous day
                    current_day_idx = (current_day_idx - 1) % len(days_of_week)
                elif arrow_key == '5':  # Page Up
                    try:
                        next_key = get_char()  # Consume the trailing ~ character
                    except:
                        pass
                    selected_idx = max(0, selected_idx - visible_lines)
                elif arrow_key == '6':  # Page Down
                    try:
                        next_key = get_char()  # Consume the trailing ~ character
                    except:
                        pass
                    selected_idx = min(len(audio_files) - 1, selected_idx + visible_lines)
        elif key == ' ':  # Space for Page Down
            selected_idx = min(len(audio_files) - 1, selected_idx + visible_lines)
        elif key.lower() == 'd':  # Toggle Day playlist
            current_day = days_of_week[current_day_idx]
            file = audio_files[selected_idx]
            is_in_playlist = file in playlists[current_day]['day']
            
            if is_in_playlist:
                playlists[current_day]['day'].remove(file)
            else:
                playlists[current_day]['day'].add(file)
                
            update_playlist_file(current_day, 'day', file, not is_in_playlist)
            
        elif key.lower() == 'n':  # Toggle Night playlist
            current_day = days_of_week[current_day_idx]
            file = audio_files[selected_idx]
            is_in_playlist = file in playlists[current_day]['night']
            
            if is_in_playlist:
                playlists[current_day]['night'].remove(file)
            else:
                playlists[current_day]['night'].add(file)
                
            update_playlist_file(current_day, 'night', file, not is_in_playlist)
            
        elif key.lower() == 'l':  # Toggle Late Night playlist
            current_day = days_of_week[current_day_idx]
            file = audio_files[selected_idx]
            is_in_playlist = file in playlists[current_day]['late_night']
            
            if is_in_playlist:
                playlists[current_day]['late_night'].remove(file)
            else:
                playlists[current_day]['late_night'].add(file)
                
            update_playlist_file(current_day, 'late_night', file, not is_in_playlist)
            
        elif key.lower() == 'c':  # Copy current day to all other days
            current_day = days_of_week[current_day_idx]
            playlists = copy_day_to_all(playlists, current_day, days_of_week, audio_files)
            flash_message = f"Playlists from {current_day} copied to all other days!"
            message_timer = 0
            
        elif key.lower() == 'f':  # Copy current file to all other days
            current_day = days_of_week[current_day_idx]
            current_file = audio_files[selected_idx]
            
            # Try to copy the file to all days
            playlists, success = copy_current_file_to_all(playlists, current_day, days_of_week, current_file)
            
            if success:
                flash_message = f"File '{current_file}' copied to all days!"
            else:
                flash_message = f"File not in any playlist! Add it first."
            message_timer = 0
            
        elif key == 'g':  # Go to beginning
            selected_idx = 0
        elif key == 'G':  # Go to end
            selected_idx = len(audio_files) - 1

if __name__ == "__main__":
    main()
