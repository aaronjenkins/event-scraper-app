"""Dedupe, filter, and sort events before sending."""
import re
from datetime import datetime, timedelta, timezone
from typing import List

from config import (
    DEDUPE_TITLE_THRESHOLD,
    KEYWORDS_ALLOW,
    KEYWORDS_BLOCK,
    LOOKAHEAD_DAYS,
)
from sources.base import Event


_WS = re.compile(r"\s+")
_PUNCT = re.compile(r"[^a-z0-9 ]+")


def _norm(s: str) -> str:
    s = s.lower()
    s = _PUNCT.sub(" ", s)
    return _WS.sub(" ", s).strip()


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def filter_window(events: List[Event]) -> List[Event]:
    """Keep events that overlap the look-ahead window.

    An event qualifies if any part of [start, end] falls inside [now, now+N]:
    - Upcoming events: start is inside the window.
    - Currently-running events (e.g. multi-week Playhouse productions): start
      is already in the past, but end is still in the future.

    Events without an end default to a zero-length range at start, so the
    original single-datetime logic is unchanged.
    """
    now = datetime.now(timezone.utc)
    window_end = now + timedelta(days=LOOKAHEAD_DAYS)
    out: List[Event] = []
    for e in events:
        start = _aware(e.start)
        end = _aware(e.end) if e.end else start
        if end < now or start > window_end:
            continue
        out.append(e)
    return out


def filter_keywords(events: List[Event]) -> List[Event]:
    allow = [k.lower() for k in KEYWORDS_ALLOW]
    block = [k.lower() for k in KEYWORDS_BLOCK]
    out = []
    for e in events:
        hay = f"{e.title} {e.venue}".lower()
        if block and any(b in hay for b in block):
            continue
        if allow and not any(a in hay for a in allow):
            continue
        out.append(e)
    return out


def dedupe(events: List[Event]) -> List[Event]:
    try:
        from rapidfuzz import fuzz
    except ImportError:
        print("[cleanup] rapidfuzz missing, exact-match dedupe only")
        fuzz = None

    kept: List[Event] = []
    for e in events:
        e_title = _norm(e.title)
        e_day = e.day_key()
        dup = False
        for k in kept:
            if k.day_key() != e_day:
                continue
            k_title = _norm(k.title)
            if k_title == e_title:
                dup = True
                break
            if fuzz and fuzz.token_set_ratio(e_title, k_title) >= DEDUPE_TITLE_THRESHOLD:
                dup = True
                break
        if not dup:
            kept.append(e)
    return kept


def _source_rank(src: str) -> int:
    # Prefer structured sources when dedupe picks a winner by stable sort.
    order = {"ticketmaster": 0, "ics": 1, "serpapi": 2}
    for key, rank in order.items():
        if src.startswith(key):
            return rank
    return 99


def clean(events: List[Event]) -> List[Event]:
    events = filter_window(events)
    events = filter_keywords(events)
    events.sort(key=lambda e: (_aware(e.start), _source_rank(e.source)))
    events = dedupe(events)
    return events
