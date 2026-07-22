"""Generic ICS parser."""
from datetime import datetime, timezone
from typing import List

from db import Venue


def _to_dt(value):
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return datetime.combine(value, datetime.min.time(), tzinfo=timezone.utc)


def parse(venue: Venue, body: bytes):
    from . import ParsedEvent
    try:
        from icalendar import Calendar
    except ImportError:
        print(f"[ics:{venue.slug}] icalendar not installed, skipping")
        return []
    try:
        cal = Calendar.from_ical(body)
    except Exception as e:
        print(f"[ics:{venue.slug}] parse failed: {e}")
        return []
    out: List[ParsedEvent] = []
    for comp in cal.walk("VEVENT"):
        try:
            raw_dtstart = comp.get("DTSTART").dt
            # A datetime means the feed specified a time; a bare date means
            # all-day / time-unknown and we synthesise midnight in _to_dt.
            time_known = isinstance(raw_dtstart, datetime)
            start = _to_dt(raw_dtstart)
            end = _to_dt(comp.get("DTEND").dt) if comp.get("DTEND") else None
            title = str(comp.get("SUMMARY", "")).strip()
            loc = str(comp.get("LOCATION", "")).strip()
            url = str(comp.get("URL", "")) or f"ics:{venue.slug}:{title}:{start.isoformat()}"
            out.append(ParsedEvent(
                title=title,
                start=start,
                end=end,
                url=url,
                venue_display=loc,
                raw_source="ics",
                time_known=time_known,
            ))
        except Exception as e:
            print(f"[ics:{venue.slug}] skipping: {e}")
    return out
