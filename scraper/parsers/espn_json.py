"""ESPN public schedule JSON parser.

Each ESPN team has its own venue row in events.venues, with the
team-schedule URL stored verbatim:

    https://site.api.espn.com/apis/site/v2/sports/<league>/teams/<id>/schedule

The team_id is read back out of the path so we can filter to home games
only — every Cincinnati team currently configured is home-only. (If a
future team needs both home and away, drop or invert the home_only check
and split the slug accordingly.)

Migrated from bot/sources/espn_source.py on 2026-04-30 when the
external sources were folded into scraper's daily indexing. Broadcast
labels and tv_links were intentionally not carried over — events.events
has no columns for them, and the SPA renderer that consumed them is being
rebuilt to read directly from the DB.
"""
import json
import re
from datetime import datetime
from typing import List

from db import Venue


_TEAM_ID_RE = re.compile(r"/teams/(\d+)/schedule")


def _team_id_from_url(url: str) -> str:
    m = _TEAM_ID_RE.search(url or "")
    return m.group(1) if m else ""


def _is_home(comp: dict, team_id: str) -> bool:
    for c in comp.get("competitors") or []:
        if str(c.get("id")) == str(team_id):
            return c.get("homeAway") == "home"
    return False


def parse(venue: Venue, body: bytes):
    from . import ParsedEvent
    try:
        payload = json.loads(body.decode(errors="replace"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        print(f"[espn_json:{venue.slug}] body parse failed: {e}")
        return []
    team_id = _team_id_from_url(venue.url or "")
    out: List[ParsedEvent] = []
    for e in payload.get("events") or []:
        try:
            dt_str = e.get("date")
            if not dt_str:
                continue
            comp = (e.get("competitions") or [{}])[0]
            if team_id and not _is_home(comp, team_id):
                continue
            start = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
            name = e.get("name") or e.get("shortName") or "Game"
            url = (e.get("links") or [{}])[0].get("href") or ""
            if not url:
                # ESPN sometimes ships pre-season stub rows without a links
                # array; we'd produce a duplicate-key collision in the
                # (venue_id, url, start_at) unique index without a URL.
                continue
            out.append(ParsedEvent(
                title=name,
                start=start,
                url=url,
                raw_source="espn_json",
                time_known=True,
            ))
        except Exception as ex:
            print(f"[espn_json:{venue.slug}] skipping event: {ex}")
    return out
