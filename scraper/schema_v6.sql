-- schema_v6: mark venues whose sources are legitimately empty sometimes.
--
-- _is_sharp_drop only alerts on the >0 -> 0 transition. Once a venue is
-- flat at 0 it never alerts again, so a stale parser can hide for months
-- behind a green Healthchecks ping (CSO parsed 0 for weeks after their
-- API started wrapping its response; Ensemble did the same after moving
-- events off the homepage). scrape.py now also nags on the flat-zero case.
--
-- Some sources are legitimately empty for long stretches, though: the
-- ESPN college feeds return "events": [] for the whole off-season. Those
-- set allow_zero_parse and are skipped by the flat-zero nag.
--
-- They still get sharp-drop alerts, so an in-season regression (8 -> 0)
-- is NOT masked by the flag. The flag only suppresses the standing nag.
--
-- Idempotent: safe to re-run.

ALTER TABLE events.venues
  ADD COLUMN IF NOT EXISTS allow_zero_parse boolean NOT NULL DEFAULT false;

COMMENT ON COLUMN events.venues.allow_zero_parse IS
  'Source is legitimately empty at times (e.g. ESPN college feeds off-season); suppresses the stuck-at-zero nag but not sharp-drop alerts.';
