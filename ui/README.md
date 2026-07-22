# event-scraper-ui

Static SPA that renders the [bot](../bot/) agenda. Reads a
sibling `events.json`; no backend.

## Stack

Vite 8 · React 19 · TypeScript · plain CSS (per the JS UI baseline). No UI
library — agenda + chips do not need Radix.

## Layout

- `src/App.tsx` — fetches `./events.json` once on mount.
- `src/components/Agenda.tsx` — groups events by date.
- `src/components/EventCard.tsx` — one row per event: time · emoji · title ·
  venue · broadcast badge · TV / Spotify / YouTube chips.
- `src/types.ts` — payload shape the bot writes.
- `src/styles.css` — dark theme, mobile-friendly. No CSS framework.
- `public/events.json` — sample payload used in dev only; the deployed
  container mounts the live file over the top.

## Dev

```bash
npm install
npm run dev
```

## Build

```bash
npm run build
```

Outputs to `dist/`. The deployed `nginx:alpine` container on localhost
mounts `dist/` read-only and overlays the live `events.json` written by
bot at `/var/cache/eventscraper/events.json`.

## URL

`http://localhost:8301/` (LAN only).
