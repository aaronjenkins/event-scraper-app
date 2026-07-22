-- schema_v4: artists array on events.
--
-- The LLM classify step extracts musical-artist names from the title for
-- each music/comedy event (🎸 🎼 🎤). Cincyeventbot renders those as
-- Spotify-search links — https://open.spotify.com/search/<artist> is a
-- public, auth-free URL so no Spotify developer app is needed.
--
-- Empty array for non-music events (sports / theatre / art / festival /
-- karaoke / open-mic). Nullable would have worked just as well; keeping
-- NOT NULL DEFAULT '[]' so downstream code never has to branch on NULL.
--
-- Idempotent: safe to re-run.

ALTER TABLE events.events
  ADD COLUMN IF NOT EXISTS artists jsonb NOT NULL DEFAULT '[]'::jsonb;
