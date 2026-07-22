"""Postgres access for the scraper.

Reads/writes the `events` schema. The connection URL comes from
SCRAPER_DATABASE_URL (or DATABASE_URL as a fallback).
"""
import os
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import Iterator, List, Optional
from zoneinfo import ZoneInfo

import psycopg2
import psycopg2.extras

# Parsers emit naive local times. If the DB session TZ is UTC, naive values
# would be silently interpreted as UTC on insert. We stamp LOCAL_TZ on naive
# values before write; already-aware values (ICS, ESPN) pass through. Set the
# LOCAL_TZ env var to your city's timezone.
LOCAL_TZ = ZoneInfo(os.environ.get("LOCAL_TZ", "America/New_York"))


def _localize(dt):
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=LOCAL_TZ)
    return dt

DATABASE_URL = os.environ.get(
    "SCRAPER_DATABASE_URL",
    os.environ.get("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/events"),
)


@dataclass
class Venue:
    id: int
    slug: str
    name: str
    url: Optional[str]
    parser: str
    snapshot_path: Optional[str]
    schedule: str
    last_fetched_at: Optional[datetime]
    enabled: bool
    notes: Optional[str]
    render_mode: str = "static"
    render_wait_selector: Optional[str] = None
    last_parsed_count: Optional[int] = None
    render_capture_match: Optional[str] = None
    allow_zero_parse: bool = False


@contextmanager
def connect() -> Iterator[psycopg2.extensions.connection]:
    conn = psycopg2.connect(DATABASE_URL)
    try:
        yield conn
    finally:
        conn.close()


_VENUE_COLS = (
    "id, slug, name, url, parser, snapshot_path, schedule, last_fetched_at, "
    "enabled, notes, render_mode, render_wait_selector, last_parsed_count, "
    "render_capture_match, allow_zero_parse"
)


def set_parsed_count(venue_id: int, n: int) -> None:
    """Record how many events the most recent parse produced for a venue."""
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE events.venues SET last_parsed_count = %s, updated_at = now() WHERE id = %s",
            (n, venue_id),
        )
        conn.commit()


def list_venues(*, enabled_only: bool = True) -> List[Venue]:
    where = "WHERE enabled" if enabled_only else ""
    with connect() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(f"SELECT {_VENUE_COLS} FROM events.venues {where} ORDER BY id")
        return [Venue(**row) for row in cur.fetchall()]


def record_fetch(venue_id: int, *, ok: bool, bytes_: int, duration_ms: int, error: Optional[str]) -> None:
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO events.fetch_log (venue_id, ok, bytes, duration_ms, error)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (venue_id, ok, bytes_, duration_ms, error),
        )
        if ok:
            cur.execute(
                "UPDATE events.venues SET last_fetched_at = now(), updated_at = now() WHERE id = %s",
                (venue_id,),
            )
        conn.commit()


def upsert_events(venue_id: int, rows):
    """Upsert rows returned by a parser. Returns lists of (inserted, updated,
    deleted) event ids so the caller can run LLM classification only on the
    new ones. Soft-deletes any previously-seen rows for this venue that did
    not appear in `rows` this time.
    """
    inserted, updated = [], []
    seen_keys = set()
    with connect() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        for r in rows:
            start = _localize(r.start)
            end = _localize(r.end)
            seen_keys.add((r.url, start))
            time_known = getattr(r, "time_known", True)
            cur.execute(
                """
                INSERT INTO events.events
                    (venue_id, title, start_at, end_at, url, raw_source,
                     time_known, first_seen_at, last_seen_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, now(), now())
                ON CONFLICT (venue_id, url, start_at) DO UPDATE SET
                    title        = EXCLUDED.title,
                    end_at       = EXCLUDED.end_at,
                    raw_source   = EXCLUDED.raw_source,
                    time_known   = EXCLUDED.time_known,
                    last_seen_at = now(),
                    deleted_at   = NULL
                RETURNING id, (xmax = 0) AS inserted
                """,
                (
                    venue_id,
                    r.title,
                    start,
                    end,
                    r.url,
                    r.raw_source or None,
                    time_known,
                ),
            )
            row = cur.fetchone()
            if row["inserted"]:
                inserted.append(row["id"])
            else:
                updated.append(row["id"])

        # Soft-delete everything else under this venue that wasn't seen.
        cur.execute(
            """
            UPDATE events.events
               SET deleted_at = now()
             WHERE venue_id = %s
               AND deleted_at IS NULL
               AND (url, start_at) NOT IN %s
             RETURNING id
            """,
            (venue_id, tuple(seen_keys) if seen_keys else (("", datetime.fromtimestamp(0)),)),
        )
        deleted = [row["id"] for row in cur.fetchall()]
        conn.commit()

    return inserted, updated, deleted


def set_event_emoji(event_id: int, emoji: str) -> None:
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE events.events SET emoji = %s WHERE id = %s",
            (emoji, event_id),
        )
        conn.commit()


def set_event_artists(event_id: int, artists: list) -> None:
    """Write an array of artist names (may be empty) into the events.artists
    JSONB column. The bot uses this to render Spotify-search links."""
    import json as _json
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE events.events SET artists = %s::jsonb WHERE id = %s",
            (_json.dumps(list(artists or [])), event_id),
        )
        conn.commit()


def get_event(event_id: int):
    with connect() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            SELECT e.id, e.title, e.start_at, e.url, e.venue_id, v.name AS venue_name
              FROM events.events e
              JOIN events.venues v ON v.id = e.venue_id
             WHERE e.id = %s
            """,
            (event_id,),
        )
        return cur.fetchone()
