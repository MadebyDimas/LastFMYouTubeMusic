import re
from typing import Tuple

# Patterns to strip from track titles (case-insensitive)
CLEAN_PATTERNS = [
    # Video / Audio format tags
    r"[\(\[\{]\s*(?:official\s+)?(?:music\s+)?video\s*[\)\]\}]",
    r"[\(\[\{]\s*(?:official\s+)?audio\s*[\)\]\}]",
    r"[\(\[\{]\s*(?:official\s+)?lyric(?:s)?(?:\s+video)?\s*[\)\]\}]",
    r"[\(\[\{]\s*visualizer\s*[\)\]\}]",
    r"[\(\[\{]\s*(?:4k|hd|hq|uhd)\s*(?:remaster(?:ed)?)?\s*[\)\]\}]",
    r"[\(\[\{]\s*clip\s+officiel\s*[\)\]\}]",
    r"[\(\[\{]\s*video\s+clip\s*[\)\]\}]",
    r"[\(\[\{]\s*(?:official\s+)?stream\s*[\)\]\}]",
    r"[\(\[\{]\s*album\s+version\s*[\)\]\}]",
    
    # Trailing standard noise
    r"\|\s*(?:official\s+)?(?:music\s+)?video.*$",
    r"\|\s*(?:official\s+)?audio.*$",
    r"\|\s*lyrics?.*$",
    
    # Clean redundant "HD", "4K" at the end
    r"\s*-\s*(?:official\s+)?(?:music\s+)?video.*$",
]

def clean_track_title(title: str, artist: str = "") -> str:
    """
    Cleans unwanted metadata (Official Music Video, Lyrics, etc.) from track title.
    """
    if not title:
        return ""

    cleaned = title

    # If title starts with "Artist - ", remove the artist part if it matches
    if artist and " - " in cleaned:
        parts = cleaned.split(" - ", 1)
        if parts[0].strip().lower() == artist.strip().lower():
            cleaned = parts[1]

    # Apply regex cleanups
    for pattern in CLEAN_PATTERNS:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)

    # Clean double spaces and extra whitespace
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    
    # Strip lingering empty brackets like () or []
    cleaned = re.sub(r"[\(\[\{]\s*[\)\]\}]", "", cleaned).strip()

    # If all cleaning removed everything, return original title
    return cleaned if cleaned else title

def parse_artist_and_title(raw_title: str, raw_artist: str) -> Tuple[str, str]:
    """
    Parses and sanitizes artist and title, detecting if artist is embedded in title (e.g. 'Artist - Song').
    """
    artist = raw_artist.strip() if raw_artist else "Unknown Artist"
    title = raw_title.strip() if raw_title else "Unknown Track"

    # If title has " - " format and artist is generic or matches
    if " - " in title:
        parts = title.split(" - ", 1)
        potential_artist = parts[0].strip()
        potential_title = parts[1].strip()

        # If YTM artist was unknown/topic/channel or closely matches
        if not raw_artist or raw_artist.lower() in ("unknown artist", "various artists", "various") or raw_artist.endswith(" - Topic"):
            artist = potential_artist
            title = potential_title
        elif potential_artist.lower() == raw_artist.lower():
            title = potential_title

    # Clean the title
    title = clean_track_title(title, artist)

    # If artist ends with " - Topic" (YouTube auto-generated channel suffix), clean it
    if artist.endswith(" - Topic"):
        artist = artist[:-8].strip()

    return artist, title
