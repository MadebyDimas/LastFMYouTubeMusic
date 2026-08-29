import asyncio
import logging
import sys
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from rich.logging import RichHandler

from src.config import settings
from src.database import Database
from src.ytmusic_client import YTMClient
from src.lastfm_client import LastFMClient
from src.tracker import ScrobbleTracker

def setup_logging():
    logging.basicConfig(
        level=settings.LOG_LEVEL.upper(),
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(rich_tracebacks=True, show_path=False)]
    )

async def tracking_loop(tracker: ScrobbleTracker):
    tracker.is_running = True
    tracker.log_event("Scrobbler daemon started in background. Listening for tracks...", level="info")
    while tracker.is_running:
        try:
            tracker.process_history()
        except Exception as e:
            tracker.log_event(f"Unexpected error in tracking loop: {e}", level="error")
        await asyncio.sleep(settings.POLL_INTERVAL)

def interactive_setup_headers():
    print("\n=== YouTube Music Headers Setup ===")
    print("1. Go to https://music.youtube.com in your browser")
    print("2. Open DevTools (F12) -> Network tab -> filter 'player' or 'browse'")
    print("3. Right click any request -> Copy -> Copy request headers (or copy Cookie)")
    print("4. Paste below, followed by an empty line (or press Ctrl+D / EOF):\n")
    lines = []
    try:
        while True:
            line = input()
            if not line and lines:
                break
            lines.append(line)
    except EOFError:
        pass
    raw = "\n".join(lines).strip()
    if not raw:
        print("No input provided. Aborted.")
        return
    auth_path = settings.data_path / "browser.json"
    try:
        YTMClient.setup_from_headers(raw, auth_path)
        print(f"\n\033[92m✅ Successfully saved and verified authentication at {auth_path}\033[0m")
    except Exception as e:
        print(f"\n\033[91m❌ Setup failed: {e}\033[0m")

async def run_server():
    setup_logging()
    logger = logging.getLogger("lastfm_scrobbler.main")
    logger.info("Starting YouTube Music -> Last.fm Scrobbler...")

    db = Database(settings.db_path)
    ytm = YTMClient()
    lastfm = LastFMClient(db)
    tracker = ScrobbleTracker(ytm, lastfm, db)

    await tracking_loop(tracker)

def main():
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == "setup-headers":
            interactive_setup_headers()
            return

    try:
        asyncio.run(run_server())
    except (KeyboardInterrupt, SystemExit):
        print("\nScrobbler stopped.")

if __name__ == "__main__":
    main()
