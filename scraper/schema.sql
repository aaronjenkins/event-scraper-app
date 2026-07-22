-- `events` schema: venue registry + scraped events.
--
-- Re-runnable: uses IF NOT EXISTS and idempotent seeds.

CREATE SCHEMA IF NOT EXISTS events;

CREATE TABLE IF NOT EXISTS events.venues (
    id              serial PRIMARY KEY,
    slug            text UNIQUE NOT NULL,
    name            text NOT NULL,
    url             text,
    parser          text NOT NULL,
    snapshot_path   text,
    schedule        text NOT NULL DEFAULT '0 7 * * *',
    last_fetched_at timestamptz,
    enabled         boolean NOT NULL DEFAULT true,
    notes           text,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now()
);

-- last_parsed_count powers the parser-collapse alert in scrape.py. When a
-- run produces 0 rows after the previous run produced >0, we post to Signal.
ALTER TABLE events.venues ADD COLUMN IF NOT EXISTS last_parsed_count integer;

-- render_mode picks the fetch path in scrape.py: 'static' = requests.get,
-- 'browser' = the render service /render (full browser navigation), 'capture' =
-- the render service /capture (intercept a session-authenticated XHR; needs
-- render_capture_match — see schema_v5.sql).
-- render_wait_selector is consulted by 'browser' mode to wait for a CSS
-- selector before snapshotting the DOM.
ALTER TABLE events.venues ADD COLUMN IF NOT EXISTS render_mode text NOT NULL DEFAULT 'static';
ALTER TABLE events.venues ADD COLUMN IF NOT EXISTS render_wait_selector text;

CREATE INDEX IF NOT EXISTS venues_enabled_idx
    ON events.venues (enabled)
    WHERE enabled;

CREATE TABLE IF NOT EXISTS events.fetch_log (
    id         bigserial PRIMARY KEY,
    venue_id   integer NOT NULL REFERENCES events.venues(id) ON DELETE CASCADE,
    fetched_at timestamptz NOT NULL DEFAULT now(),
    ok         boolean NOT NULL,
    bytes      integer,
    duration_ms integer,
    error      text
);

CREATE INDEX IF NOT EXISTS fetch_log_venue_time_idx
    ON events.fetch_log (venue_id, fetched_at DESC);

-- Seed your venues here (re-run-safe via ON CONFLICT DO NOTHING). Each row maps
-- a venue to the parser that handles its page. See scraper/parsers/ for the
-- available parser keys (ics, json_ld, espn_json, serpapi_search).
--
-- INSERT INTO events.venues (slug, name, url, parser, schedule,
--     render_mode, render_wait_selector, render_capture_match, enabled, notes)
-- VALUES
--   ('example_ics',    'Example Venue (ICS)',     'https://example.com/events.ics', 'ics',            '0 7 * * *', 'static',  NULL, NULL, true, 'Any iCalendar feed'),
--   ('example_jsonld', 'Example Venue (JSON-LD)', 'https://example.com/events',     'json_ld',        '0 7 * * *', 'browser', NULL, NULL, true, 'schema.org Event JSON-LD on the page'),
--   ('serpapi',        'SerpAPI Google Events',   'https://serpapi.com/search?engine=google_events&q=Events+in+Your+City&hl=en&gl=us&htichips=date:week&api_key=${SERPAPI_KEY}', 'serpapi_search', '0 7 * * *', 'static', NULL, NULL, true, 'Google Events; api_key templated from SERPAPI_KEY env')
-- ON CONFLICT (slug) DO NOTHING;
