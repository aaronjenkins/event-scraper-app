"""SerpAPI Google Events parser.

The venue's URL is the SerpAPI REST endpoint with engine=google_events
and the search params baked in (e.g. q=Events+in+Cincinnati). The
api_key is templated as ${SERPAPI_KEY} and substituted by scrape.py at
fetch time so the secret never lives in the DB.

The 'when' field SerpAPI returns is human-readable Google text — the
exact same shape we already handle in bot. The two real
failures we saw on 2026-04-30 ('Thu, Apr 30, 8 PM EDT' and 'Fri, May 1')
are covered by the format cascade below; if Google introduces a new
shape, unparseable rows fall through to time_known=False with the
current day stamped at midnight so the SPA still surfaces them as
date-only.
"""
import json
import re
from datetime import datetime, timedelta
from typing import List, Optional
from zoneinfo import ZoneInfo

from db import Venue


LOCAL_TZ = ZoneInfo("America/New_York")

_DASH = re.compile(r"\s*[–-]\s*")
_TRAILING_TZ = re.compile(
    r"\s+(?:[ECMP][SD]T|UTC|GMT|UT|AKDT|AKST|HST|HDT)\s*$"
)
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


def _parse_when(when: str, now: datetime) -> tuple[datetime, bool]:
    """Return (start_dt, time_known). time_known=False when only a date
    parsed (or nothing parsed and we fell back to today)."""
    raw = (when or "").strip()
    parts = _DASH.split(raw, 1) if raw else [""]
    head = _TRAILING_TZ.sub("", parts[0].strip())
    tail = parts[1].strip() if len(parts) > 1 else ""
    if head and tail and not re.search(r"(?i)\b[ap]m\b", head):
        m = re.search(r"(?i)\b([ap]m)\b", tail)
        if m:
            head = f"{head} {m.group(1).upper()}"
    for fmt in _TIME_FORMATS:
        try:
            parsed = datetime.strptime(head, fmt).replace(year=now.year, tzinfo=LOCAL_TZ)
            if parsed < now - timedelta(days=1):
                parsed = parsed.replace(year=now.year + 1)
            return parsed, True
        except ValueError:
            continue
    for fmt in _DATE_ONLY_FORMATS:
        try:
            parsed = datetime.strptime(head, fmt).replace(year=now.year, tzinfo=LOCAL_TZ)
            if parsed < now - timedelta(days=1):
                parsed = parsed.replace(year=now.year + 1)
            return parsed, False
        except ValueError:
            continue
    return now.replace(hour=0, minute=0, second=0, microsecond=0), False


def parse(venue: Venue, body: bytes, *, now: Optional[datetime] = None):
    from . import ParsedEvent
    # See ensemble_html.parse — `now` anchors year inference so frozen
    # fixtures stay deterministic instead of expiring with the calendar.
    now = now or datetime.now(LOCAL_TZ)
    try:
        payload = json.loads(body.decode(errors="replace"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        print(f"[serpapi_search:{venue.slug}] body parse failed: {e}")
        return []
    results = payload.get("events_results") or []
    out: List[ParsedEvent] = []
    seen: set[str] = set()
    for r in results:
        try:
            url = (r.get("link") or "").strip()
            if not url or url in seen:
                continue
            seen.add(url)
            title = (r.get("title") or "").strip()
            if not title:
                continue
            when = (r.get("date") or {}).get("when", "")
            start, time_known = _parse_when(when, now)
            venue_display = ""
            addr = r.get("address") or []
            if addr:
                venue_display = addr[0]
            out.append(ParsedEvent(
                title=title,
                start=start,
                url=url,
                venue_display=venue_display,
                raw_source="serpapi_search",
                time_known=time_known,
            ))
        except Exception as ex:
            print(f"[serpapi_search:{venue.slug}] skipping result: {ex}")
    return out
