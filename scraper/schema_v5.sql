-- schema_v5: capture-mode support on venues.
--
-- CSO serves its event feed as a React SPA that only fires a POST
-- XHR to /api/products/productionseasons after a user-session bootstrap
-- (Incapsula cookies + antiforgery CSRF tokens). Reproducing that bootstrap
-- headlessly is too fragile to maintain; instead the render service grew a /capture
-- endpoint that navigates the page in a real browser, watches network
-- traffic, and returns the first response whose URL contains a caller-
-- supplied substring.
--
-- Fetch mode for such a venue is 'capture', and `render_capture_match`
-- holds the substring the render service should wait for. Existing 'static' and
-- 'browser' modes unaffected.
--
-- Idempotent: safe to re-run.

ALTER TABLE events.venues
  ADD COLUMN IF NOT EXISTS render_capture_match text;
