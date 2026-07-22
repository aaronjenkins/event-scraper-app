"""bot daily tick.

Pulls events from every fetcher (ESPN, SerpAPI, venue DB), de-dupes and
re-classifies, then writes a single ``events.json`` payload that the
``event-scraper-ui`` SPA renders. Posts a short Signal note with a link to
the SPA.
"""

import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List
from urllib.parse import quote
from zoneinfo import ZoneInfo

import requests
from dotenv import load_dotenv

from cleanup import clean
from config import LOOKAHEAD_DAYS
from llm import reclassify_non_espn
from sources import Event, fetch_espn, fetch_serpapi
from venue_db import list_current_events

LOCAL_TZ = ZoneInfo("America/New_York")

load_dotenv()

SIGNAL_WEBHOOK_URL = os.environ.get("SIGNAL_WEBHOOK_URL", "http://localhost:7200")
SIGNAL_WEBHOOK_KEY = os.environ.get("SIGNAL_WEBHOOK_KEY", "changeme")
SIGNAL_GROUP_ID = os.environ.get("SIGNAL_GROUP_ID", "")

# JSON output consumed by the event-scraper-ui SPA. The nginx container on
# localhost bind-mounts this path at /usr/share/nginx/html/events.json.
EVENTS_JSON_PATH = Path(os.environ.get(
    "EVENTS_JSON_PATH", "/var/cache/eventscraper/events.json"
))
SPA_URL = os.environ.get("SPA_URL", "https://events.example.com/")


def send_message(message: str) -> None:
    if not SIGNAL_GROUP_ID:
        print("Notifier Error: SIGNAL_GROUP_ID not set, refusing to send")
        return
    try:
        resp = requests.post(f"{SIGNAL_WEBHOOK_URL}/send", json={
            "message": message,
            "platform": "signal",
            "group_id": SIGNAL_GROUP_ID,
            "api_key": SIGNAL_WEBHOOK_KEY,
        }, timeout=30)
        resp.raise_for_status()
        print(f"Signal digest queued via Notifier: {resp.json()}")
    except requests.RequestException as e:
        print(f"Notifier Error: {e}")


def _local(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(LOCAL_TZ)


def _clean_venue(raw: str | None) -> str:
    """First non-blank line, first comma-separated segment. Collapses ICS
    multi-line LOCATION blocks and drops trailing addresses/cities."""
    if not raw:
        return ""
    for line in raw.splitlines():
        line = line.strip()
        if line:
            return line.split(",")[0].strip()
    return ""


def _format_time(local_start: datetime) -> str | None:
    if local_start.hour == 0 and local_start.minute == 0:
        return None
    return local_start.strftime("%-I:%M %p")


def _spotify_search_url(artist: str) -> str:
    return f"https://open.spotify.com/search/{quote(artist, safe='')}"


def _youtube_search_url(artist: str) -> str:
    return f"https://www.youtube.com/results?search_query={quote(artist, safe='')}"


def _event_to_dict(e: Event) -> dict[str, Any]:
    local_start = _local(e.start)
    return {
        "date": local_start.strftime("%Y-%m-%d"),
        "time": e.time_display or _format_time(local_start),
        "title": e.title,
        "venue": _clean_venue(e.venue),
        "url": e.url,
        "emoji": e.emoji,
        "source": e.source,
        "broadcast": e.broadcast,
        "tv_links": list(e.tv_links),
        "spotify_searches": [
            {"name": a, "url": _spotify_search_url(a)} for a in e.artists
        ],
        "youtube_searches": [
            {"name": a, "url": _youtube_search_url(a)} for a in e.artists
        ],
    }


def build_payload(events: List[Event], generated_at: datetime) -> dict[str, Any]:
    return {
        "generated_at": generated_at.isoformat(),
        "lookahead_days": LOOKAHEAD_DAYS,
        "event_count": len(events),
        "events": [_event_to_dict(e) for e in events],
    }


def write_events_json(payload: dict[str, Any]) -> bool:
    """Write events.json atomically (tmp + rename) so the SPA never sees a
    half-written file. Mode 0644 so the docker-side nginx process (different
    uid) can read it through the bind-mount. Returns True on success."""
    try:
        EVENTS_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w",
            dir=EVENTS_JSON_PATH.parent,
            prefix=".events.",
            suffix=".json.tmp",
            delete=False,
        ) as tmp:
            json.dump(payload, tmp, ensure_ascii=False, indent=2)
            tmp_path = Path(tmp.name)
        tmp_path.chmod(0o644)
        tmp_path.replace(EVENTS_JSON_PATH)
        print(f"wrote {EVENTS_JSON_PATH} ({payload['event_count']} events)")
        return True
    except Exception as e:
        print(f"events.json write failed: {e}")
        return False


def main() -> None:
    all_events: List[Event] = []
    for fetcher in (fetch_espn, fetch_serpapi):
        try:
            batch = fetcher()
            print(f"[{fetcher.__module__}] fetched {len(batch)} events")
            all_events.extend(batch)
        except Exception as e:
            print(f"[{fetcher.__module__}] fetcher crashed: {e}")

    try:
        db_events = list_current_events(LOOKAHEAD_DAYS)
        print(f"[db] loaded {len(db_events)} events from events.events")
        all_events.extend(db_events)
    except Exception as e:
        print(f"[db] events load crashed: {e}")

    cleaned = clean(all_events)
    print(f"After cleanup: {len(cleaned)} events")
    # ESPN and SerpAPI events still get LLM-classified at render time because
    # they're live fetches (no scraper pipeline stamping emoji on insert).
    reclassify_non_espn([e for e in cleaned if not e.source.startswith("venue:")])
    for e in cleaned:
        print(f"  {e.emoji} [{e.source}] {e.title[:80]}")

    generated_at = datetime.now(LOCAL_TZ)
    display_str = generated_at.strftime("%b %d, %Y")
    payload = build_payload(cleaned, generated_at)

    if "--dry-run" in sys.argv:
        print("--- DRY RUN ---")
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    if not write_events_json(payload):
        print("events.json write failed; skipping Signal post")
        return

    send_message(
        f"📅 Local Events — {display_str}\n"
        f"{len(cleaned)} upcoming over the next {LOOKAHEAD_DAYS} days\n"
        f"{SPA_URL}"
    )


if __name__ == "__main__":
    main()
