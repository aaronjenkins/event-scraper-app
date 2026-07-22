-- schema_v3: time_known flag on events.
--
-- Some venues (Memorial Hall's show-date, Cincinnati Shakespeare's range
-- start, all-day ICS entries, MEMI/MOTR rows without a posted showtime)
-- can only produce a date — we synthesise midnight for start_at so the
-- (venue_id, url, start_at) unique constraint still works. time_known
-- lets renderers distinguish "legitimately starts at 00:00" from
-- "placeholder midnight, show 'TBA'".
--
-- Idempotent: safe to re-run. Existing rows default to true; the next
-- daily scrape's ON CONFLICT path will overwrite them with the correct
-- value from ParsedEvent.time_known.

ALTER TABLE events.events
  ADD COLUMN IF NOT EXISTS time_known boolean NOT NULL DEFAULT true;
