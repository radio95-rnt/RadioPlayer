from . import PlaylistModifierModule, Track
DEFAULT_CROSSFADE = 5.0
class Module(PlaylistModifierModule):
    def modify(self, global_args: dict, playlist: list[Track]) -> list[Track] | None:
        out = []
        for track in playlist:
            do_cross_fade = track.official
            track_crossfade = float(track.args.get("crossfade", DEFAULT_CROSSFADE) if track.args else DEFAULT_CROSSFADE) or DEFAULT_CROSSFADE
            if do_cross_fade and track_crossfade:
                out.append(Track(track.path, track_crossfade, track_crossfade, do_cross_fade, track.args, focus_time_offset=-track_crossfade))
            else: out.append(track)
        return out
playlistmod = (Module(),1)