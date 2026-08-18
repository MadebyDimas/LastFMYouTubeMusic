import logging
import time
from typing import Optional, Dict, Any
import pylast
from src.config import settings
from src.database import Database

logger = logging.getLogger("lastfm_scrobbler.lastfm")

class LastFMClient:
    def __init__(self, db: Database):
        self.db = db
        self.network: Optional[pylast.LastFMNetwork] = None
        self._init_network()

    def _init_network(self) -> bool:
        # Check if we have session key saved in DB or environment
        session_key = self.db.get_config("lastfm_session_key") or settings.LASTFM_SESSION_KEY
        api_key = self.db.get_config("lastfm_api_key") or settings.LASTFM_API_KEY
        api_secret = self.db.get_config("lastfm_api_secret") or settings.LASTFM_API_SECRET
        username = self.db.get_config("lastfm_username") or settings.LASTFM_USERNAME
        password_hash = self.db.get_config("lastfm_password_hash") or settings.LASTFM_PASSWORD_HASH

        if not api_key or not api_secret:
            logger.warning("Last.fm API key and secret not configured.")
            return False

        try:
            if session_key:
                self.network = pylast.LastFMNetwork(
                    api_key=api_key,
                    api_secret=api_secret,
                    session_key=session_key
                )
            elif username and password_hash:
                self.network = pylast.LastFMNetwork(
                    api_key=api_key,
                    api_secret=api_secret,
                    username=username,
                    password_hash=password_hash
                )
            elif username and hasattr(settings, "LASTFM_PASSWORD") and getattr(settings, "LASTFM_PASSWORD"):
                # if raw password is provided in settings
                p_hash = pylast.md5(getattr(settings, "LASTFM_PASSWORD"))
                self.network = pylast.LastFMNetwork(
                    api_key=api_key,
                    api_secret=api_secret,
                    username=username,
                    password_hash=p_hash
                )
            else:
                logger.warning("Last.fm credentials incomplete (need session_key or username+password_hash).")
                return False

            user = self.network.get_authenticated_user()
            user_name = user.get_name() if user else "Authenticated"
            logger.info(f"Successfully authenticated with Last.fm as: {user_name}")
            return True
        except Exception as e:
            logger.error(f"Failed to authenticate with Last.fm: {e}")
            self.network = None
            return False

    def is_authenticated(self) -> bool:
        return self.network is not None

    def scrobble(self, artist: str, title: str, timestamp: int, 
                 album: Optional[str] = None, duration: Optional[int] = None) -> bool:
        if not self.is_authenticated():
            if not self._init_network():
                raise RuntimeError("Last.fm is not configured or authenticated")

        try:
            logger.info(f"Scrobbling to Last.fm: {artist} - {title} (at {timestamp})")
            self.network.scrobble(
                artist=artist,
                title=title,
                timestamp=timestamp,
                album=album or "",
                duration=duration
            )
            return True
        except Exception as e:
            logger.error(f"Error scrobbling {artist} - {title}: {e}")
            raise

    def update_now_playing(self, artist: str, title: str, 
                           album: Optional[str] = None, duration: Optional[int] = None) -> bool:
        if not self.is_authenticated():
            if not self._init_network():
                return False

        try:
            self.network.update_now_playing(
                artist=artist,
                title=title,
                album=album or "",
                duration=duration
            )
            logger.debug(f"Updated Now Playing on Last.fm: {artist} - {title}")
            return True
        except Exception as e:
            logger.warning(f"Error updating now playing for {artist} - {title}: {e}")
            return False

    def get_user_info(self) -> Optional[Dict[str, Any]]:
        if not self.is_authenticated():
            return None
        try:
            user = self.network.get_authenticated_user()
            if not user:
                return None
            return {
                "name": user.get_name(),
                "playcount": user.get_playcount(),
                "url": user.get_url(),
                "image": user.get_image()
            }
        except Exception as e:
            logger.error(f"Error fetching Last.fm user info: {e}")
            return None
