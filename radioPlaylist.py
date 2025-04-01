#!/usr/bin/env python3
import os
import sys
import termios
import tty
import signal
import shutil
import libcache
from datetime import datetime

files_dir = "/home/user/mixes/"
playlists_dir = "/home/user/playlists/"

formats = ('.mp3', '.m4a')

def get_audio_files(directory) -> list[str]:
	audio_files = []
	try:
		for file in os.listdir(directory):
			file: str
			if file.lower().endswith(formats):
				audio_files.append(file)
		return sorted(audio_files)
	except FileNotFoundError:
		print(f"Error: Directory '{directory}' not found.")
		return []
	except PermissionError:
		print(f"Error: Permission denied for directory '{directory}'.")
		return []

def get_char() -> str:
	fd = sys.stdin.fileno()
	old_settings = termios.tcgetattr(fd)
	try:
		tty.setraw(sys.stdin.fileno())
		ch = sys.stdin.read(1)
	finally:
		termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
	return ch

def clear_screen() -> None:
	print("\033c", end="")

def get_terminal_size() -> os.terminal_size:
	return shutil.get_terminal_size()

def get_days_of_week() -> list[str]:
	days = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
	today = datetime.now().weekday()
	return days[today:] + days[:today]

def ensure_playlist_dir(day: str) -> str:
	playlist_dir = os.path.expanduser(os.path.join(playlists_dir, day))
	if not os.path.exists(playlist_dir):
		os.makedirs(playlist_dir)
	return playlist_dir

def calculate_category_percentages(playlists, current_day):
	category_counts = {'morning': 0, 'day': 0, 'night': 0, 'late_night': 0}
	polskie_counts = {'morning': 0, 'day': 0, 'night': 0, 'late_night': 0}

	for category in category_counts.keys():
		for file in playlists[current_day][category]:
			category_counts[category] += 1
			if "Polskie" in file or "Dzem" in file:
				polskie_counts[category] += 1

	total_count = sum(category_counts.values())

	if total_count == 0:
		return None

	percentages = {
		category: (count / total_count) * 100 for category, count in category_counts.items()
	}

	polskie_percentages = {
		category: (polskie_counts[category] / category_counts[category]) * 100 if category_counts[category] > 0 else 0
		for category in category_counts
	}

	return percentages, polskie_percentages, sum(polskie_percentages.values())/len(polskie_percentages.keys())

def update_playlist_file(day: str, period: str, filepath: str, add: bool):
	playlist_dir = ensure_playlist_dir(day)
	playlist_file = os.path.join(playlist_dir, period)

	full_filepath = os.path.join(files_dir, filepath)

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

def load_playlists(days: list[str]):
	playlists = {}
	for day in days:
		playlists[day] = {'morning': set(), 'day': set(), 'night': set(), 'late_night': set()}
		playlist_dir = os.path.expanduser(os.path.join(playlists_dir, day))

		if os.path.exists(playlist_dir):
			for period in ['morning', 'day', 'night', 'late_night']:
				playlist_file = os.path.join(playlist_dir, period)
				if os.path.exists(playlist_file):
					with open(playlist_file, 'r') as f:
						for line in f:
							line = line.strip()
							if line:
								filename = os.path.basename(line)
								playlists[day][period].add(filename)

	return playlists

def copy_day_to_all(playlists: dict, source_day: str, days: list[str]):
	periods = ['morning', 'day', 'night', 'late_night']

	for target_day in days:
		if target_day == source_day:
			continue

		for period in periods:
			target_dir = ensure_playlist_dir(target_day)
			target_file = os.path.join(target_dir, period)

			filepaths = []
			for filename in playlists[source_day][period]:
				full_path = os.path.join(files_dir, filename)
				filepaths.append(full_path)

			with open(target_file, 'w') as f:
				f.write('\n'.join(filepaths) + ('\n' if filepaths else ''))

			playlists[target_day][period] = set(playlists[source_day][period])

	return playlists

def copy_current_file_to_all(playlists: dict, source_day: str, days: list[str], current_file: str):
	source_periods = {
		'morning': current_file in playlists[source_day]['morning'],
		'day': current_file in playlists[source_day]['day'],
		'night': current_file in playlists[source_day]['night'],
		'late_night': current_file in playlists[source_day]['late_night']
	}

	if not any(source_periods.values()):
		return playlists, False

	for target_day in days:
		if target_day == source_day:
			continue

		for period, is_present in source_periods.items():
			target_set = playlists[target_day][period]
			full_path = os.path.join(files_dir, current_file)

			if is_present:
				target_set.add(current_file)
			else:
				target_set.discard(current_file)

			playlist_dir = ensure_playlist_dir(target_day)
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

def draw_interface(audio_files: list, playlists: dict, selected_idx: int, current_day_idx: int, scroll_offset: int, terminal_size_cache: libcache.Cache, message=None):
	clear_screen()
	term_width, term_height = terminal_size_cache.getElement("width", False), terminal_size_cache.getElement("height", False)
	if term_width is None or term_height is None:
		term_width, term_height = get_terminal_size()
		terminal_size_cache.saveElement("width", term_width, 5, False, True)
		terminal_size_cache.saveElement("height", term_height, 5, False, True)
	days = get_days_of_week()
	current_day = days[current_day_idx]

	percentages, polskie_percentages, total_pl = calculate_category_percentages(playlists, current_day) or ({}, {}, 0)

	available_lines = term_height - 6
	start_idx = max(0, min(scroll_offset, len(audio_files) - available_lines))
	end_idx = min(start_idx + available_lines, len(audio_files))

	print("\033[1;37mCategory Distribution:\033[0m".center(term_width))
	category_bar = ""
	for category in ['morning', 'day', 'night', 'late_night']:
		percent = percentages.get(category, 0)
		polskie_percent = polskie_percentages.get(category, 0)
		category_bar += f"{category[:4].capitalize()}: {percent:.1f}% (P:{polskie_percent:.1f}%) | "
	category_bar += f"TP:{total_pl:0.1f}%"

	if len(category_bar) > term_width - 2:
		category_bar = category_bar[:term_width - 5] + "..."
	print(category_bar.center(term_width))

	day_bar = ""
	for i, day in enumerate(days):
		if i == current_day_idx:
			day_bar += f"\033[1;44m[{day}]\033[0m "
		else:
			day_bar += f"[{day}] "
	print(day_bar.strip())

	print("UP/DOWN: Navigate | D/N/L: Toggle | C: Copy day to all | F: Copy file to all | Q: Quit")

	if start_idx > 0:
		print("↑", end="")
	else:
		print(" ", end="")

	position_info = f" {current_day.capitalize()} | File {selected_idx + 1}/{len(audio_files)} "
	padding = term_width - len(position_info) - 2
	print(position_info.center(padding), end="")

	if end_idx < len(audio_files):
		print("↓")
	else:
		print(" ")

	if message:
		print(f"\033[1;32m{message}\033[0m")
	else:
		print()

	for idx in range(start_idx, end_idx):
		file = audio_files[idx]

		in_morning = file in playlists[current_day]['morning']
		in_day = file in playlists[current_day]['day']
		in_night = file in playlists[current_day]['night']
		in_late_night = file in playlists[current_day]['late_night']

		m_color = "\033[1;32m" if in_morning else "\033[1;30m"
		d_color = "\033[1;32m" if in_day else "\033[1;30m"
		n_color = "\033[1;32m" if in_night else "\033[1;30m"
		l_color = "\033[1;32m" if in_late_night else "\033[1;30m"

		if idx == selected_idx:
			row_highlight = "\033[1;44m"
		else:
			row_highlight = ""

		max_filename_length = term_width - 15
		if len(file) > max_filename_length:
			file = file[:max_filename_length-3] + "..."

		print(f"{row_highlight}[{m_color}M\033[0m{row_highlight}] [{d_color}D\033[0m{row_highlight}] [{n_color}N\033[0m{row_highlight}] [{l_color}L\033[0m{row_highlight}] {file}\033[0m")

def main():
	audio_files = get_audio_files(files_dir)

	if not audio_files:
		print("No audio files found. Exiting.")
		return

	days_of_week = get_days_of_week()
	playlists = load_playlists(days_of_week)

	selected_idx = 0
	current_day_idx = 0
	scroll_offset = 0
	flash_message = None
	message_timer = 0

	def signal_handler(sig, frame):
		clear_screen()
		sys.exit(0)

	signal.signal(signal.SIGINT, signal_handler)

	terminal_size_cache = libcache.Cache()

	while True:
		term_width, term_height = terminal_size_cache.getElement("width", False), terminal_size_cache.getElement("height", False)
		if term_width is None or term_height is None:
			term_width, term_height = get_terminal_size()
			terminal_size_cache.saveElement("width", term_width, 5, False, True)
			terminal_size_cache.saveElement("height", term_height, 5, False, True)
		visible_lines = term_height - 6

		if selected_idx < scroll_offset:
			scroll_offset = selected_idx
		elif selected_idx >= scroll_offset + visible_lines:
			scroll_offset = selected_idx - visible_lines + 1

		draw_interface(audio_files, playlists, selected_idx, current_day_idx, scroll_offset, terminal_size_cache, flash_message)

		if flash_message:
			message_timer += 1
			if message_timer > 1:
				flash_message = None
				message_timer = 0

		key = get_char()

		if key == 'q':
			clear_screen()
			break
		elif key == '\x1b':
			next_key = get_char()
			if next_key == '[':
				arrow_key = get_char()
				if arrow_key == 'A':
					selected_idx = max(0, selected_idx - 1)
				elif arrow_key == 'B':
					selected_idx = min(len(audio_files) - 1, selected_idx + 1)
				elif arrow_key == 'C':
					current_day_idx = (current_day_idx + 1) % len(days_of_week)
				elif arrow_key == 'D':
					current_day_idx = (current_day_idx - 1) % len(days_of_week)
				elif arrow_key == '5':
					try:
						next_key = get_char()
					except:
						pass
					selected_idx = max(0, selected_idx - visible_lines)
				elif arrow_key == '6':
					try:
						next_key = get_char()
					except:
						pass
					selected_idx = min(len(audio_files) - 1, selected_idx + visible_lines)
		elif key == ' ':
			selected_idx = min(len(audio_files) - 1, selected_idx + visible_lines)
		elif key.lower() == 'm':
			current_day = days_of_week[current_day_idx]
			file = audio_files[selected_idx]
			is_in_playlist = file in playlists[current_day]['morning']

			if is_in_playlist:
				playlists[current_day]['morning'].remove(file)
			else:
				playlists[current_day]['morning'].add(file)

			update_playlist_file(current_day, 'morning', file, not is_in_playlist)
		elif key.lower() == 'd':
			current_day = days_of_week[current_day_idx]
			file = audio_files[selected_idx]
			is_in_playlist = file in playlists[current_day]['day']

			if is_in_playlist:
				playlists[current_day]['day'].remove(file)
			else:
				playlists[current_day]['day'].add(file)

			update_playlist_file(current_day, 'day', file, not is_in_playlist)

		elif key.lower() == 'n':
			current_day = days_of_week[current_day_idx]
			file = audio_files[selected_idx]
			is_in_playlist = file in playlists[current_day]['night']

			if is_in_playlist:
				playlists[current_day]['night'].remove(file)
			else:
				playlists[current_day]['night'].add(file)

			update_playlist_file(current_day, 'night', file, not is_in_playlist)

		elif key.lower() == 'l':
			current_day = days_of_week[current_day_idx]
			file = audio_files[selected_idx]
			is_in_playlist = file in playlists[current_day]['late_night']

			if is_in_playlist:
				playlists[current_day]['late_night'].remove(file)
			else:
				playlists[current_day]['late_night'].add(file)

			update_playlist_file(current_day, 'late_night', file, not is_in_playlist)

		elif key.lower() == 'c':
			current_day = days_of_week[current_day_idx]
			playlists = copy_day_to_all(playlists, current_day, days_of_week)
			flash_message = f"Playlists from {current_day} copied to all other days!"
			message_timer = 0

		elif key.lower() == 'f':
			current_day = days_of_week[current_day_idx]
			current_file = audio_files[selected_idx]

			playlists, success = copy_current_file_to_all(playlists, current_day, days_of_week, current_file)

			if success:
				flash_message = f"File '{current_file}' copied to all days!"
			else:
				flash_message = f"File not in any playlist! Add it first."
			message_timer = 0

		elif key == 'g':
			selected_idx = 0
		elif key == 'G':
			selected_idx = len(audio_files) - 1

if __name__ == "__main__":
	main()
