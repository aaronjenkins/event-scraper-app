"""Nightly retention pruner for the events schema.

Runs out-of-band from scrape.py so a bloated DB can't block a daily fetch.
Fired by scraper-retention.timer at 04:00 local — three hours before the
scrape tick so the day starts clean.

- events.events: hard-delete rows soft-deleted more than 30 days ago.
  The 30-day grace lets a parser regression ("venue dropped all events")
  get re-discovered + un-soft-deleted on the next successful parse.
- events.fetch_log: hard-delete rows older than 30 days. fetch_log is
  operational telemetry — long-tail retention adds no value once the run
  in question is no longer on the journalctl window.

No secrets needed; reuses SCRAPER_DATABASE_URL from the shared env.
"""
import sys

from db import connect


RETENTION_DAYS_EVENTS = 30
RETENTION_DAYS_FETCH_LOG = 30


def main() -> int:
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            "DELETE FROM events.events "
            "WHERE deleted_at IS NOT NULL "
            f"  AND deleted_at < now() - interval '{RETENTION_DAYS_EVENTS} days'"
        )
        events_pruned = cur.rowcount
        cur.execute(
            "DELETE FROM events.fetch_log "
            f"WHERE fetched_at < now() - interval '{RETENTION_DAYS_FETCH_LOG} days'"
        )
        fetch_log_pruned = cur.rowcount
        conn.commit()
    print(
        f"[retention] events.soft-deleted >{RETENTION_DAYS_EVENTS}d: {events_pruned}, "
        f"fetch_log >{RETENTION_DAYS_FETCH_LOG}d: {fetch_log_pruned}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
