# event-scraper-app

A self-hostable local-events aggregator. It scrapes venue calendars and pulls
sports/search feeds into Postgres, publishes a daily `events.json`, and renders
it as a browsable web agenda — optionally posting a daily digest to a Signal
webhook.

It ships configured for one city (Cincinnati) as the reference dataset; the
venue list, parsers, and config are swappable for any city.

## Components

| Dir | What it does | Stack |
|-----|--------------|-------|
| [`scraper/`](scraper) | Fetches each venue's calendar on a schedule, runs a per-venue parser, and writes normalized events to Postgres. | Python + psycopg2 |
| [`bot/`](bot) | Merges venue events with ESPN sports and SerpAPI; dedupes; LLM-classifies; writes `events.json`; posts a digest to a Signal webhook. | Python |
| [`ui/`](ui) | Renders `events.json` as an agenda with per-event calendar export. | Vite + React + TypeScript |

```
venue sites → scraper → Postgres (events.events) ┐
ESPN / SerpAPI ──────────────────────────────────┼→ bot → events.json → ui
                                                  ┘      └→ Signal digest
```

## Quick start

```bash
# 1. Postgres — create a database and load the schema
createdb events
psql events -f scraper/schema.sql
for v in scraper/schema_v*.sql; do psql events -f "$v"; done   # migrations, in order

# 2. Config
cp .env.example .env        # then edit — at minimum set DATABASE_URL

# 3. Scraper (populates events.events)
cd scraper && python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
python scrape.py

# 4. Bot (writes events.json + optional Signal digest)
cd ../bot && python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
python index.py

# 5. UI
cd ../ui && npm install && npm run dev      # or `npm run build` → dist/
```

The bot writes `events.json` to `EVENTS_JSON_PATH`; serve that file at the UI's
`/data/events.json` (same origin). In dev the UI falls back to the sample at
`ui/public/data/events.json`.

## Configuration

All settings are environment variables — see [`.env.example`](.env.example).
Highlights:

- **`DATABASE_URL`** — Postgres connection (scraper + bot).
- **`SERPAPI_KEY` / `SERP_API_KEY`** — [SerpAPI](https://serpapi.com) key for the Google-Events source (optional).
- **`LITELLM_URL` / `LITELLM_KEY`** — an OpenAI-compatible ([LiteLLM](https://litellm.ai)) endpoint for emoji/artist classification. Set `*_LLM=0` to disable.
- **`RENDER_URL` / `RENDER_API_KEY`** — a headless-browser render microservice with `/render` and `/capture` endpoints, used for JS-heavy or bot-protected venues. Static venues need none.
- **`SIGNAL_WEBHOOK_URL` / `SIGNAL_WEBHOOK_KEY` / `SIGNAL_GROUP_ID`** — an optional webhook (expects `POST /send {message, group_id, api_key}`) for the daily digest and scraper alerts. Leave unset to disable.

## Adding your venues

This ships as a blank template — no venues are seeded.

1. **Venues** — add rows to `scraper/schema.sql` (`events.venues`), one per venue, each naming the parser that handles its page. Write parsers in `scraper/parsers/` (the `ParsedEvent` contract is in `parsers/__init__.py`). The bundled generic parsers cover most cases: `ics` (any iCalendar feed), `json_ld` (schema.org Event JSON-LD), `serpapi_search` (Google Events), `espn_json` (ESPN team schedules).
2. **Sports** — set `CITY`, `STATE_CODE`, and `ESPN_TEAMS` in `bot/config.py` (team ids come from ESPN team-page URLs).
3. **Branding** — update the title and colors in `ui/src`.

## Notes

- Deployment is left to you; `scraper/systemd/` and `bot/` include example
  systemd unit + timer files (edit the `User=`/paths for your host).
