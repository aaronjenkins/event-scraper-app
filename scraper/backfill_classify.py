"""One-shot backfill — re-classify existing events for emoji + artists.

Pulls every enabled-venue event whose artists column is still the empty
default (i.e. never touched by the classifier), batches them through
llm.classify_batch, writes back. Intended as a one-off after adding the
artists column or changing the classifier; daily scrapes keep new inserts
current, so this stays idle afterwards.

Batches of 50 per LLM call to keep max_tokens reasonable.
"""
import sys

from db import connect, set_event_artists, set_event_emoji
from llm import classify_batch


BATCH = 20


def fetch_stale():
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT e.id, e.title, v.name
              FROM events.events e
              JOIN events.venues v ON v.id = e.venue_id
             WHERE e.deleted_at IS NULL
               AND e.start_at > now()
               AND e.artists = '[]'::jsonb
             ORDER BY e.start_at
            """
        )
        return cur.fetchall()


def main() -> int:
    rows = fetch_stale()
    print(f"[backfill] {len(rows)} events to re-classify")
    if not rows:
        return 0
    total_artists = 0
    for i in range(0, len(rows), BATCH):
        chunk = rows[i : i + BATCH]
        classifications = classify_batch(chunk)
        for eid, (emoji, artists) in classifications.items():
            set_event_emoji(eid, emoji)
            set_event_artists(eid, artists)
            if artists:
                total_artists += 1
        print(f"[backfill] batch {i // BATCH + 1}: {len(classifications)}/{len(chunk)} classified")
    print(f"[backfill] done — {total_artists} events got artist lists")
    return 0


if __name__ == "__main__":
    sys.exit(main())
