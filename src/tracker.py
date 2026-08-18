import time
import logging
from typing import Optional, Dict, Any, List
from src.config import settings
from src.database import Database
from src.ytmusic_client import YTMClient, YTMTrack
from src.lastfm_client import LastFMClient
from src.cleaner import parse_artist_and_title

logger = logging.getLogger("lastfm_scrobbler.tracker")

class TrackState:
    def __init__(self, track: YTMTrack, artist: str, title: str):
        self.track = track
        self.artist = artist
        self.title = title
        self.album = track.album
        self.video_id = track.video_id
        self.duration = track.duration_seconds or 180  # Default 3 mins if unknown
        self.first_seen_at = time.time()
        self.now_playing_sent = False
        self.scrobbled = False

    def elapsed_time(self) -> float:
        return time.time() - self.first_seen_at

    def is_eligible_for_scrobble(self, min_duration: int = 30, scrobble_percent: float = 0.2) -> bool:
        if self.duration < min_duration:
            # Track is shorter than 30s (e.g., sound effect or short intro)
            return False
        # Scrobble threshold: 20% of track length (capped at 4 minutes)
        required_seconds = min(self.duration * scrobble_percent, 240.0)
        return self.elapsed_time() >= required_seconds

    def is_finished(self) -> bool:
        """Returns True if the track duration plus a small buffer has elapsed."""
        return self.elapsed_time() >= (self.duration + 15)

    def is_playing(self) -> bool:
        """Returns True if the track is still within its playing duration."""
        return not self.is_finished()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "artist": self.artist,
            "album": self.album,
            "video_id": self.video_id,
            "duration": self.duration,
            "elapsed": int(min(self.elapsed_time(), self.duration)),
            "first_seen_at": int(self.first_seen_at),
            "thumbnail_url": self.track.thumbnail_url,
            "now_playing_sent": self.now_playing_sent,
            "scrobbled": self.scrobbled,
            "is_playing": self.is_playing()
        }

class ScrobbleTracker:
    def __init__(self, ytm_client: YTMClient, lastfm_client: LastFMClient, db: Database):
        self.ytm = ytm_client
        self.lastfm = lastfm_client
        self.db = db
        self.current_track: Optional[TrackState] = None
        self.last_handled_key: Optional[str] = None
        self.recent_events: List[Dict[str, Any]] = []
        self.is_running: bool = False
        self.last_poll_time: Optional[float] = None
        self.last_error: Optional[str] = None

    def log_event(self, message: str, level: str = "info", data: Optional[Dict[str, Any]] = None):
        event = {
            "timestamp": int(time.time()),
            "message": message,
            "level": level,
            "data": data or {}
        }
        self.recent_events.append(event)
        if len(self.recent_events) > 100:
            self.recent_events.pop(0)
        
        if level == "error":
            logger.error(message)
            self.last_error = message
        elif level == "warning":
            logger.warning(message)
        else:
            logger.info(message)

    def _normalize_track(self, raw_track: YTMTrack) -> tuple[str, str]:
        artist = raw_track.artist
        title = raw_track.title
        if settings.CLEAN_TITLES:
            artist, title = parse_artist_and_title(title, artist)
        return artist, title

    def _make_track_key(self, artist: str, title: str, video_id: Optional[str]) -> str:
        return f"{artist.strip().lower()}::{title.strip().lower()}::{video_id or ''}"

    def check_and_scrobble_current(self, force: bool = False):
        """
        Evaluates if the currently playing track has met scrobble criteria and scrobbles it.
        """
        if not self.current_track or self.current_track.scrobbled:
            return

        if force or self.current_track.is_eligible_for_scrobble(
            min_duration=settings.MIN_TRACK_DURATION,
            scrobble_percent=settings.SCROBBLE_PERCENTAGE
        ):
            # Check DB deduplication window
            dedup_window = max(self.current_track.duration * 2, 300)
            if self.db.is_recently_scrobbled(
                self.current_track.title,
                self.current_track.artist,
                self.current_track.video_id,
                within_seconds=dedup_window
            ):
                self.log_event(
                    f"Skip duplicate: {self.current_track.artist} - {self.current_track.title} already scrobbled recently",
                    level="info"
                )
                self.current_track.scrobbled = True
                return

            scrobble_ts = int(self.current_track.first_seen_at)
            try:
                self.lastfm.scrobble(
                    artist=self.current_track.artist,
                    title=self.current_track.title,
                    timestamp=scrobble_ts,
                    album=self.current_track.album,
                    duration=self.current_track.duration
                )
                self.db.add_scrobble(
                    title=self.current_track.title,
                    artist=self.current_track.artist,
                    album=self.current_track.album,
                    video_id=self.current_track.video_id,
                    duration=self.current_track.duration,
                    scrobbled_at=scrobble_ts,
                    status="scrobbled"
                )
                self.current_track.scrobbled = True
                self.log_event(
                    f"Scrobbled: {self.current_track.artist} - {self.current_track.title}",
                    level="success",
                    data=self.current_track.to_dict()
                )
            except Exception as e:
                self.log_event(f"Failed to scrobble {self.current_track.artist} - {self.current_track.title}: {e}", level="error")
                self.db.add_scrobble(
                    title=self.current_track.title,
                    artist=self.current_track.artist,
                    album=self.current_track.album,
                    video_id=self.current_track.video_id,
                    duration=self.current_track.duration,
                    scrobbled_at=scrobble_ts,
                    status="failed",
                    error=str(e)
                )

    def process_history(self):
        """
        Fetches latest YTM history and detects track transitions without duplicate scrobbling.
        """
        self.last_poll_time = time.time()
        self.last_error = None

        if not self.ytm.is_authenticated():
            self.log_event("YouTube Music is not authenticated. Waiting for setup.", level="warning")
            return

        if not self.lastfm.is_authenticated():
            self.log_event("Last.fm is not authenticated. Waiting for setup.", level="warning")
            return

        try:
            history = self.ytm.get_history()
        except Exception as e:
            self.log_event(f"Failed to fetch YouTube Music history: {e}", level="error")
            return

        if not history:
            return

        latest_ytm_track = history[0]
        artist, title = self._normalize_track(latest_ytm_track)
        track_key = self._make_track_key(artist, title, latest_ytm_track.video_id)

        # If no active track is being tracked currently
        if self.current_track is None:
            # If this is the exact same track we already processed and completed, do not restart tracking
            if self.last_handled_key == track_key:
                return

            # Start new track tracking
            self.current_track = TrackState(latest_ytm_track, artist, title)
            self.last_handled_key = track_key
            self.lastfm.update_now_playing(
                artist=artist,
                title=title,
                album=self.current_track.album,
                duration=self.current_track.duration
            )
            self.current_track.now_playing_sent = True
            self.log_event(f"Now playing: {artist} - {title}", level="info", data=self.current_track.to_dict())
            return

        # Check if the track changed
        current_key = self._make_track_key(self.current_track.artist, self.current_track.title, self.current_track.video_id)
        same_track = (current_key == track_key)

        if same_track:
            # Same track is still playing. Check if it reached scrobble threshold
            self.check_and_scrobble_current()

            # If track duration elapsed + buffer, it has finished playing
            if self.current_track.is_finished():
                # Make sure it's scrobbled if eligible
                self.check_and_scrobble_current(force=False)
                # Clear active track when idle timeout is exceeded (> duration + 30s)
                # Note: self.last_handled_key remains set to track_key, preventing re-scrobbling!
                if self.current_track.elapsed_time() > (self.current_track.duration + 30):
                    self.current_track = None
        else:
            # Track changed! First, verify if previous track was eligible for scrobbling
            self.check_and_scrobble_current(force=False)

            # Start new current track
            self.current_track = TrackState(latest_ytm_track, artist, title)
            self.last_handled_key = track_key
            self.lastfm.update_now_playing(
                artist=artist,
                title=title,
                album=self.current_track.album,
                duration=self.current_track.duration
            )
            self.current_track.now_playing_sent = True
            self.log_event(f"Now playing: {artist} - {title}", level="info", data=self.current_track.to_dict())

    def get_status(self) -> Dict[str, Any]:
        return {
            "ytm_connected": self.ytm.is_authenticated(),
            "lastfm_connected": self.lastfm.is_authenticated(),
            "is_running": self.is_running,
            "last_poll_time": self.last_poll_time,
            "last_error": self.last_error,
            "current_track": self.current_track.to_dict() if self.current_track else None,
            "total_scrobbles": self.db.get_total_scrobbles(),
            "recent_scrobbles": self.db.get_latest_scrobbles(limit=15),
            "recent_events": self.recent_events[-20:]
        }
