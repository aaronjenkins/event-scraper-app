-- `events` schema: venue registry + scraped events. Single source of truth for
-- the DB layout. Re-runnable: IF NOT EXISTS everywhere, idempotent seeds.

CREATE SCHEMA IF NOT EXISTS events;

-- Venues to scrape. Each row names the parser that handles its page and how to
-- fetch it (static / browser-render / XHR-capture).
CREATE TABLE IF NOT EXISTS events.venues (
    id                   serial PRIMARY KEY,
    slug                 text UNIQUE NOT NULL,
    name                 text NOT NULL,
    url                  text,
    parser               text NOT NULL,                       -- key in scraper/parsers/ PARSERS
    snapshot_path        text,                                -- override for where the raw page is cached
    schedule             text NOT NULL DEFAULT '0 7 * * *',   -- cron; when this venue is due
    render_mode          text NOT NULL DEFAULT 'static',      -- static | browser | capture
    render_wait_selector text,                                -- 'browser': CSS selector to await before snapshot
    render_capture_match text,                                -- 'capture': substring of the XHR URL to intercept
    last_fetched_at      timestamptz,
    last_parsed_count    integer,                             -- rows the last parse produced (drop-alert basis)
    allow_zero_parse     boolean NOT NULL DEFAULT false,      -- source legitimately empty sometimes
    enabled              boolean NOT NULL DEFAULT true,
    notes                text,
    created_at           timestamptz NOT NULL DEFAULT now(),
    updated_at           timestamptz NOT NULL DEFAULT now()
);

COMMENT ON COLUMN events.venues.allow_zero_parse IS
  'Source is legitimately empty at times (e.g. off-season sports feeds); suppresses the stuck-at-zero nag but not sharp-drop alerts.';

CREATE INDEX IF NOT EXISTS venues_enabled_idx
    ON events.venues (enabled)
    WHERE enabled;

-- Parsed events. Upserted after each scrape; rows no longer seen are soft-deleted.
CREATE TABLE IF NOT EXISTS events.events (
    id            bigserial PRIMARY KEY,
    venue_id      integer NOT NULL REFERENCES events.venues(id) ON DELETE CASCADE,
    title         text NOT NULL,
    start_at      timestamptz NOT NULL,
    end_at        timestamptz,
    url           text NOT NULL,
    emoji         text,                                       -- classifier emoji
    artists       jsonb NOT NULL DEFAULT '[]'::jsonb,         -- LLM-extracted artist names (music/comedy)
    time_known    boolean NOT NULL DEFAULT true,              -- false = placeholder midnight, render "TBA"
    raw_source    text,
    first_seen_at timestamptz NOT NULL DEFAULT now(),
    last_seen_at  timestamptz NOT NULL DEFAULT now(),
    deleted_at    timestamptz,
    UNIQUE (venue_id, url, start_at)
);

CREATE INDEX IF NOT EXISTS events_start_idx
    ON events.events (start_at)
    WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS events_venue_idx
    ON events.events (venue_id)
    WHERE deleted_at IS NULL;

-- Per-fetch audit log.
CREATE TABLE IF NOT EXISTS events.fetch_log (
    id          bigserial PRIMARY KEY,
    venue_id    integer NOT NULL REFERENCES events.venues(id) ON DELETE CASCADE,
    fetched_at  timestamptz NOT NULL DEFAULT now(),
    ok          boolean NOT NULL,
    bytes       integer,
    duration_ms integer,
    error       text
);

CREATE INDEX IF NOT EXISTS fetch_log_venue_time_idx
    ON events.fetch_log (venue_id, fetched_at DESC);

-- Seed your venues here (re-run-safe via ON CONFLICT DO NOTHING). Each row maps
-- a venue to the parser that handles its page. Available parser keys live in
-- scraper/parsers/ (ics, json_ld, espn_json, serpapi_search).
--
-- INSERT INTO events.venues (slug, name, url, parser, schedule,
--     render_mode, render_wait_selector, render_capture_match, enabled, notes)
-- VALUES
--   ('example_ics',    'Example Venue (ICS)',     'https://example.com/events.ics', 'ics',            '0 7 * * *', 'static',  NULL, NULL, true, 'Any iCalendar feed'),
--   ('example_jsonld', 'Example Venue (JSON-LD)', 'https://example.com/events',     'json_ld',        '0 7 * * *', 'browser', NULL, NULL, true, 'schema.org Event JSON-LD on the page'),
--   ('serpapi',        'SerpAPI Google Events',   'https://serpapi.com/search?engine=google_events&q=Events+in+Your+City&hl=en&gl=us&htichips=date:week&api_key=${SERPAPI_KEY}', 'serpapi_search', '0 7 * * *', 'static', NULL, NULL, true, 'Google Events; api_key templated from SERPAPI_KEY env')
-- ON CONFLICT (slug) DO NOTHING;
