"""schema.org Event JSON-LD parser (MusicEvent / TheaterEvent / etc.)."""
import json
import re
from datetime import datetime
from typing import List

from db import Venue

BLOCK_RE = re.compile(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', re.S)
WANTED_TYPES = {"MusicEvent", "Event", "TheaterEvent", "ComedyEvent", "SportsEvent"}


def _parse_iso(dt):
    try:
        return datetime.fromisoformat(dt.replace("Z", "+00:00"))
    except Exception:
        return None


def parse(venue: Venue, body: bytes):
    from . import ParsedEvent
    html = body.decode(errors="replace")
    seen = set()
    out: List[ParsedEvent] = []
    for match in BLOCK_RE.finditer(html):
        try:
            data = json.loads(match.group(1))
        except Exception:
            continue
        records = data if isinstance(data, list) else [data]
        for d in records:
            if not isinstance(d, dict) or d.get("@type") not in WANTED_TYPES:
                continue
            start = _parse_iso(d.get("startDate", ""))
            if start is None:
                continue
            url = d.get("url", "")
            if not url or url in seen:
                continue
            seen.add(url)
            loc = d.get("location")
            loc_name = loc.get("name") if isinstance(loc, dict) else ""
            out.append(ParsedEvent(
                title=(d.get("name") or "").strip(),
                start=start,
                url=url,
                venue_display=loc_name or "",
                raw_source="json_ld",
            ))
    return out
