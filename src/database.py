import sqlite3
import time
from typing import List, Optional, Dict, Any
from pathlib import Path

class Database:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # Scrobbles table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS scrobbles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    video_id TEXT,
                    title TEXT NOT NULL,
                    artist TEXT NOT NULL,
                    album TEXT,
                    duration_seconds INTEGER,
                    scrobbled_at INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    error_message TEXT
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_video_id ON scrobbles(video_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_scrobbled_at ON scrobbles(scrobbled_at)")

            # Key-value config table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS kv_store (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at INTEGER NOT NULL
                )
            """)
            conn.commit()

    def add_scrobble(self, title: str, artist: str, album: Optional[str], 
                     video_id: Optional[str], duration: Optional[int], 
                     scrobbled_at: Optional[int] = None, 
                     status: str = "scrobbled", error: Optional[str] = None) -> int:
        if scrobbled_at is None:
            scrobbled_at = int(time.time())
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO scrobbles (video_id, title, artist, album, duration_seconds, scrobbled_at, status, error_message)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (video_id, title, artist, album, duration, scrobbled_at, status, error))
            conn.commit()
            return cursor.lastrowid

    def is_recently_scrobbled(self, title: str, artist: str, video_id: Optional[str], within_seconds: int = 120) -> bool:
        """
        Checks if this track was already scrobbled within recent timeframe (to avoid rapid duplicates).
        """
        cutoff = int(time.time()) - within_seconds
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if video_id:
                cursor.execute("""
                    SELECT id FROM scrobbles 
                    WHERE (video_id = ? OR (LOWER(title) = LOWER(?) AND LOWER(artist) = LOWER(?)))
                      AND scrobbled_at >= ? AND status = 'scrobbled'
                    LIMIT 1
                """, (video_id, title, artist, cutoff))
            else:
                cursor.execute("""
                    SELECT id FROM scrobbles 
                    WHERE LOWER(title) = LOWER(?) AND LOWER(artist) = LOWER(?)
                      AND scrobbled_at >= ? AND status = 'scrobbled'
                    LIMIT 1
                """, (title, artist, cutoff))
            return cursor.fetchone() is not None

    def get_latest_scrobbles(self, limit: int = 20) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, video_id, title, artist, album, duration_seconds, scrobbled_at, status, error_message
                FROM scrobbles
                ORDER BY scrobbled_at DESC
                LIMIT ?
            """, (limit,))
            return [dict(row) for row in cursor.fetchall()]

    def get_total_scrobbles(self) -> int:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM scrobbles WHERE status = 'scrobbled'")
            return cursor.fetchone()[0]

    def set_config(self, key: str, value: str):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO kv_store (key, value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
            """, (key, value, int(time.time())))
            conn.commit()

    def get_config(self, key: str) -> Optional[str]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM kv_store WHERE key = ?", (key,))
            row = cursor.fetchone()
            return row["value"] if row else None
