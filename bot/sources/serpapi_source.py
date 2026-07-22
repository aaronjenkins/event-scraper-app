"""SerpAPI Google Events source. Preserves legacy behavior."""
import os
import re
from datetime import datetime, timedelta
from typing import List, Optional
from zoneinfo import ZoneInfo

from classify import classify_text
from .base import Event

LOCAL_TZ = ZoneInfo("America/New_York")


def _localize(dt: datetime) -> datetime:
    """SerpAPI returns Cincinnati local times. Stamp them ET so the downstream
    conversion in index._local doesn't treat them as UTC and shift by 4h."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=LOCAL_TZ)
    return dt


_DASH = re.compile(r"\s*[–-]\s*")
# Trailing timezone abbreviation Google sometimes appends, e.g.
# "Thu, Apr 30, 8 PM EDT". strptime can't consume these without %Z (which
# is locale-dependent and unreliable), so we strip them — every SerpAPI
# event is already known to be Cincinnati local time.
_TRAILING_TZ = re.compile(
    r"\s+(?:[ECMP][SD]T|UTC|GMT|UT|AKDT|AKST|HST|HDT)\s*$"
)
# Time formats include a clock; date-only formats don't. Date-only matches
# render as midnight ET, which _format_time in bot/index.py
# already suppresses to None — so the SPA shows just the day header.
_TIME_FORMATS = (
    "%a, %b %d, %I %p",
    "%a, %b %d, %I:%M %p",
    "%b %d, %I %p",
    "%b %d, %I:%M %p",
)
_DATE_ONLY_FORMATS = (
    "%a, %b %d",
    "%b %d",
)


def _parse_when(when: str) -> tuple[datetime, Optional[str]]:
    """Return (sort_dt, display_str). The datetime is always tz-aware in ET
    so downstream code doesn't have to guess."""
    raw = (when or "").strip()
    parts = _DASH.split(raw, 1) if raw else [""]
    head = _TRAILING_TZ.sub("", parts[0].strip())
    tail = parts[1].strip() if len(parts) > 1 else ""
    # Google writes "7 – 10 PM" with meridiem only on the end time; borrow it.
    if head and tail and not re.search(r"(?i)\b[ap]m\b", head):
        m = re.search(r"(?i)\b([ap]m)\b", tail)
        if m:
            head = f"{head} {m.group(1).upper()}"
    now = datetime.now(LOCAL_TZ)
    # SerpAPI 'when' has no year. strptime defaults to 1900 — must replace.
    for fmt in _TIME_FORMATS + _DATE_ONLY_FORMATS:
        try:
            parsed = datetime.strptime(head, fmt).replace(year=now.year)
            parsed = _localize(parsed)
            if parsed < now - timedelta(days=1):
                parsed = parsed.replace(year=now.year + 1)
            # Successful parse — let the digest's _format_time render just
            # the start time (or suppress it for date-only matches that
            # land on midnight). The day is already a section header.
            return parsed, None
        except ValueError:
            continue
    # Unparseable — keep the event in the window by stamping it near-future
    # and fall back to Google's raw "when" string so the row still carries
    # some time context instead of a bare "—".
    return now + timedelta(hours=1), raw or None


def fetch() -> List[Event]:
    key = os.environ.get("SERP_API_KEY")
    if not key:
        return []
    try:
        from serpapi import GoogleSearch
    except ImportError:
        print("[serpapi] google-search-results not installed, skipping")
        return []

    params = {
        "api_key": key,
        "q": "Events in Cincinnati",
        "gl": "us",
        "hl": "en",
        "htichips": "date:week",
        "engine": "google_events",
    }
    try:
        results = GoogleSearch(params).get_dict().get("events_results") or []
    except Exception as e:
        print(f"[serpapi] fetch failed: {e}")
        return []

    events: List[Event] = []
    for r in results:
        try:
            start, display = _parse_when((r.get("date") or {}).get("when", ""))
            title = r.get("title", "").strip()
            venue = (r.get("address") or [""])[0]
            events.append(Event(
                title=title,
                start=start,
                venue=venue,
                url=r.get("link", ""),
                source="serpapi",
                time_display=display,
                emoji=classify_text(f"{title} {venue}"),
            ))
        except Exception as e:
            print(f"[serpapi] skipping row: {e}")
    return events
