"""Read parsed events from events.events (populated by scraper).

bot no longer owns any venue parsers — it only consumes rows that
scraper has already scraped, parsed, and classified. ESPN and SerpAPI stay
as live fetches; everything else is a SQL read.
"""
import os
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Iterator, List

import psycopg2
import psycopg2.extras

from sources.base import Event

DATABASE_URL = os.environ.get(
    "BOT_DATABASE_URL",
    os.environ.get("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/events"),
)


@contextmanager
def _connect() -> Iterator[psycopg2.extensions.connection]:
    conn = psycopg2.connect(DATABASE_URL)
    try:
        yield conn
    finally:
        conn.close()


def list_current_events(lookahead_days: int) -> List[Event]:
    """Return rows from events.events whose [start, end] overlaps the
    [now, now+N] window. Events with a NULL end_at are treated as a
    zero-length range at start_at."""
    now = datetime.now(timezone.utc)
    window_end = now + timedelta(days=lookahead_days)
    with _connect() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            SELECT e.id, e.title, e.start_at, e.end_at, e.url, e.emoji,
                   e.time_known, e.artists,
                   v.slug AS venue_slug, v.name AS venue_name
              FROM events.events e
              JOIN events.venues v ON v.id = e.venue_id
             WHERE e.deleted_at IS NULL
               AND e.start_at <= %s
               AND COALESCE(e.end_at, e.start_at) >= %s
             ORDER BY e.start_at
            """,
            (window_end, now),
        )
        return [
            Event(
                title=row["title"],
                start=row["start_at"],
                end=row["end_at"],
                venue=row["venue_name"],
                url=row["url"] or "",
                source=f"venue:{row['venue_slug']}",
                emoji=row["emoji"] or "",
                time_display=None if row["time_known"] else "TBA",
                artists=list(row["artists"] or []),
            )
            for row in cur.fetchall()
        ]
