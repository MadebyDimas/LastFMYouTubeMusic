import os
from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Paths
    DATA_DIR: str = os.getenv("DATA_DIR", "./data")
    
    # Last.fm credentials
    LASTFM_API_KEY: str = ""
    LASTFM_API_SECRET: str = ""
    LASTFM_USERNAME: str = ""
    LASTFM_PASSWORD: str = ""
    LASTFM_PASSWORD_HASH: str = ""
    LASTFM_SESSION_KEY: str = ""
    
    # YouTube Music Auth
    YTM_AUTH_TYPE: str = "oauth"  # 'oauth' or 'browser' or 'auto'
    YTM_AUTH_FILE: Optional[str] = None
    
    # Scrobbler settings
    POLL_INTERVAL: int = 30  # seconds between checking YTM history
    CLEAN_TITLES: bool = True  # clean (Official Video), (Lyrics) etc.
    SCROBBLE_PERCENTAGE: float = 0.2  # Scrobble threshold (20% of track)
    MIN_TRACK_DURATION: int = 30  # minimum duration in seconds to scrobble
    
    # Logging
    LOG_LEVEL: str = "INFO"

    @property
    def data_path(self) -> Path:
        p = Path(self.DATA_DIR)
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def ytm_auth_path(self) -> Path:
        if self.YTM_AUTH_FILE:
            return Path(self.YTM_AUTH_FILE)
        # Check oauth.json first, then browser.json
        oauth_path = self.data_path / "oauth.json"
        if oauth_path.exists():
            return oauth_path
        browser_path = self.data_path / "browser.json"
        if browser_path.exists():
            return browser_path
        return oauth_path

    @property
    def db_path(self) -> Path:
        return self.data_path / "scrobbler.db"

settings = Settings()
