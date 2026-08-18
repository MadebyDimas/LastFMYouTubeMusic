import logging
import json
from pathlib import Path
from typing import List, Optional, Dict, Any
from ytmusicapi import YTMusic, setup
from src.config import settings

logger = logging.getLogger("lastfm_scrobbler.ytmusic")

def parse_duration_to_seconds(duration_str: Any) -> Optional[int]:
    """Parses '3:45' or '1:02:30' or integer to seconds."""
    if isinstance(duration_str, int):
        return duration_str
    if not duration_str or not isinstance(duration_str, str):
        return None
    parts = duration_str.strip().split(":")
    try:
        if len(parts) == 2:
            return int(parts[0]) * 60 + int(parts[1])
        elif len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
    except ValueError:
        return None
    return None

class YTMTrack:
    def __init__(self, raw: Dict[str, Any]):
        self.raw = raw
        self.title: str = raw.get("title", "")
        self.video_id: Optional[str] = raw.get("videoId")
        
        # Artist extraction
        artists_data = raw.get("artists") or []
        if isinstance(artists_data, list):
            self.artists: List[str] = [a.get("name", "") for a in artists_data if isinstance(a, dict) and a.get("name")]
        else:
            self.artists = []
        self.artist: str = ", ".join(self.artists) if self.artists else ""

        # Album extraction
        album_data = raw.get("album")
        if isinstance(album_data, dict):
            self.album: Optional[str] = album_data.get("name")
        elif isinstance(album_data, str):
            self.album = album_data
        else:
            self.album = None

        # Duration
        self.duration_seconds: Optional[int] = raw.get("duration_seconds")
        if not self.duration_seconds and "duration" in raw:
            self.duration_seconds = parse_duration_to_seconds(raw.get("duration"))

        # Thumbnails
        thumbnails = raw.get("thumbnails") or []
        self.thumbnail_url: Optional[str] = thumbnails[-1].get("url") if thumbnails else None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "artist": self.artist,
            "album": self.album,
            "video_id": self.video_id,
            "duration_seconds": self.duration_seconds,
            "thumbnail_url": self.thumbnail_url
        }

    def __repr__(self) -> str:
        return f"<YTMTrack {self.artist} - {self.title} ({self.video_id})>"

class YTMClient:
    def __init__(self, auth_file: Optional[Path] = None):
        self.auth_file = auth_file or settings.ytm_auth_path
        self.ytm: Optional[YTMusic] = None
        self._init_ytm()

    def _init_ytm(self) -> bool:
        if self.auth_file and self.auth_file.exists():
            try:
                self.ytm = YTMusic(str(self.auth_file))
                logger.info(f"Initialized YouTube Music with auth file: {self.auth_file}")
                return True
            except Exception as e:
                logger.error(f"Failed to initialize YTMusic with {self.auth_file}: {e}")
                self.ytm = None
                return False
        else:
            logger.warning(f"No YTMusic auth file found at {self.auth_file}. Setup required.")
            self.ytm = None
            return False

    def is_authenticated(self) -> bool:
        return self.ytm is not None

    def get_history(self) -> List[YTMTrack]:
        if not self.is_authenticated():
            if not self._init_ytm():
                raise RuntimeError("YouTube Music is not authenticated. Please provide credentials.")
        try:
            raw_history = self.ytm.get_history()
            tracks = [YTMTrack(item) for item in raw_history if item.get("title")]
            return tracks
        except Exception as e:
            logger.error(f"Error fetching YouTube Music history: {e}")
            raise

    @staticmethod
    def setup_from_headers(raw_headers: str, target_path: Path) -> bool:
        """
        Takes raw HTTP request headers, cURL command, or raw Cookie string
        from music.youtube.com and generates a browser.json auth file.
        """
        import re
        raw = raw_headers.strip()

        # Support 'Copy as cURL'
        if "curl " in raw.lower():
            headers = re.findall(r"-H\s+[\x27\x22]([^\x27\x22]+)[\x27\x22]", raw, re.IGNORECASE)
            raw = "\n".join(headers)

        # Support raw Cookie value (with or without 'cookie:' prefix)
        if "SID=" in raw and not any(line.lower().startswith("cookie:") for line in raw.split("\n")):
            raw = f"cookie: {raw}\n"

        # Auto add x-goog-authuser if omitted
        if "x-goog-authuser" not in raw.lower():
            raw += "\nx-goog-authuser: 0\n"

        try:
            target_path.parent.mkdir(parents=True, exist_ok=True)
            setup(filepath=str(target_path), headers_raw=raw)
            # Verify it loads
            YTMusic(str(target_path))
            return True
        except Exception as e:
            logger.error(f"Failed to setup YTMusic headers: {e}")
            raise
