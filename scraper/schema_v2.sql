-- v2 schema: parsed events table. Populated by scraper after each scrape.
-- Re-runnable.

CREATE TABLE IF NOT EXISTS events.events (
    id              bigserial PRIMARY KEY,
    venue_id        integer NOT NULL REFERENCES events.venues(id) ON DELETE CASCADE,
    title           text NOT NULL,
    start_at        timestamptz NOT NULL,
    end_at          timestamptz,
    url             text NOT NULL,
    emoji           text,
    raw_source      text,
    first_seen_at   timestamptz NOT NULL DEFAULT now(),
    last_seen_at    timestamptz NOT NULL DEFAULT now(),
    deleted_at      timestamptz,
    UNIQUE (venue_id, url, start_at)
);

CREATE INDEX IF NOT EXISTS events_start_idx
    ON events.events (start_at)
    WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS events_venue_idx
    ON events.events (venue_id)
    WHERE deleted_at IS NULL;
