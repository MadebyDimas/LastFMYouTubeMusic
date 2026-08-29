import logging
import json
import re
from pathlib import Path
from typing import List, Optional, Dict, Any
from ytmusicapi import YTMusic, setup
from ytmusicapi.exceptions import YTMusicServerError, YTMusicUserError
from src.config import settings

logger = logging.getLogger("lastfm_scrobbler.ytmusic")

def parse_duration_to_seconds(duration_str: Any) -> Optional[int]:
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
        
        artists_data = raw.get("artists") or []
        if isinstance(artists_data, list):
            self.artists: List[str] = [a.get("name", "") for a in artists_data if isinstance(a, dict) and a.get("name")]
        else:
            self.artists = []
        self.artist: str = ", ".join(self.artists) if self.artists else ""

        album_data = raw.get("album")
        if isinstance(album_data, dict):
            self.album: Optional[str] = album_data.get("name")
        elif isinstance(album_data, str):
            self.album = album_data
        else:
            self.album = None

        self.duration_seconds: Optional[int] = raw.get("duration_seconds")
        if not self.duration_seconds and "duration" in raw:
            self.duration_seconds = parse_duration_to_seconds(raw.get("duration"))

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
        self.auth_file = auth_file
        self.ytm: Optional[YTMusic] = None
        self._init_ytm()

    def _init_ytm(self) -> bool:
        auth_path = self.auth_file or settings.ytm_auth_path
        if auth_path and auth_path.exists():
            try:
                with open(auth_path, "r", encoding="utf-8") as f:
                    data = json.load(f)

                if isinstance(data, dict) and "cookie" in data and "authorization" not in data:
                    try:
                        from ytmusicapi.helpers import sapisid_from_cookie, get_authorization
                        cookie = data.get("cookie", "")
                        sapisid = sapisid_from_cookie(cookie)
                        origin = data.get("origin", "https://music.youtube.com")
                        data["authorization"] = get_authorization(f"{sapisid} {origin}")
                        with open(auth_path, "w", encoding="utf-8") as f:
                            json.dump(data, f, indent=4)
                    except Exception as e:
                        logger.warning(f"Could not auto-generate authorization header: {e}")

                self.ytm = YTMusic(str(auth_path))
                logger.info(f"Initialized YouTube Music with auth file: {auth_path}")
                return True
            except Exception as e:
                logger.error(f"Failed to initialize YTMusic with {auth_path}: {e}")
                self.ytm = None
                return False
        else:
            logger.warning(f"No YTMusic auth file found at {auth_path}. Setup required.")
            self.ytm = None
            return False

    def is_authenticated(self) -> bool:
        return self.ytm is not None

    def get_history(self) -> List[YTMTrack]:
        if not self.is_authenticated():
            if not self._init_ytm():
                raise RuntimeError("YouTube Music is not authenticated. Please run 'setup-headers'.")
        try:
            raw_history = self.ytm.get_history()
            tracks = [YTMTrack(item) for item in raw_history if item.get("title")]
            return tracks
        except Exception as e:
            err_str = str(e)
            if isinstance(e, (YTMusicServerError, YTMusicUserError)) or err_str == "None":
                raise RuntimeError("YouTube Music session expired or invalid credentials. Please update headers via 'setup-headers'.") from e
            logger.error(f"Error fetching YouTube Music history: {e}")
            raise

    @staticmethod
    def setup_from_headers(raw_headers: str, target_path: Path) -> bool:
        raw = raw_headers.strip()

        if "curl " in raw.lower():
            headers = [line.split(" ", 1)[1].strip("'\"") for line in raw.split("\n") if line.strip().startswith("-H ")]
            raw = "\n".join(headers)

        if "SID=" in raw and not any(line.lower().startswith("cookie:") for line in raw.split("\n")):
            raw = f"cookie: {raw}\n"

        if "x-goog-authuser" not in raw.lower():
            raw += "\nx-goog-authuser: 0\n"

        try:
            target_path.parent.mkdir(parents=True, exist_ok=True)
            setup(filepath=str(target_path), headers_raw=raw)

            with open(target_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            if isinstance(data, dict) and "cookie" in data and "authorization" not in data:
                try:
                    from ytmusicapi.helpers import sapisid_from_cookie, get_authorization
                    cookie = data.get("cookie", "")
                    sapisid = sapisid_from_cookie(cookie)
                    origin = data.get("origin", "https://music.youtube.com")
                    data["authorization"] = get_authorization(f"{sapisid} {origin}")
                    with open(target_path, "w", encoding="utf-8") as f:
                        json.dump(data, f, indent=4)
                except Exception as e:
                    logger.warning(f"Could not inject authorization header: {e}")

            ytm = YTMusic(str(target_path))
            try:
                ytm.get_history()
            except Exception as test_err:
                raise ValueError(
                    f"Headers saved to {target_path}, but history verification failed: "
                    f"YouTube Music returned an unauthenticated response. "
                    f"Ensure you are logged into music.youtube.com in your browser before copying headers."
                ) from test_err

            return True
        except Exception as e:
            logger.error(f"Failed to setup YTMusic headers: {e}")
            raise
