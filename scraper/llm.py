"""LiteLLM-backed per-event classifier.

Called from scrape.py once per newly-inserted event (or on demand for
updates whose emoji is still NULL). Single call per run, so we batch all
new events into one prompt and parse back a JSON array.

Returns both the display emoji AND a list of musical artist names
extracted from the title (empty list for non-music events). Artist names
feed the digest's Spotify-search links — `https://open.spotify.com/search/<name>`
is an auth-free public URL, so no Spotify Developer app is required.
"""
import json
import os
import re
from typing import Dict, List, Tuple

import requests

LITELLM_URL = os.environ.get("LITELLM_URL", "http://localhost:4000")
LITELLM_KEY = os.environ.get("LITELLM_KEY", "changeme")
LLM_MODEL = os.environ.get("SCRAPER_LLM_MODEL", "claude-haiku")
LLM_ENABLED = os.environ.get("SCRAPER_LLM", "1") != "0"

ALLOWED_EMOJI = {"⚾", "🏈", "🏀", "⚽", "🏒", "🎭", "🎼", "🎸", "🎤", "🎨", "🎪", "🍺", "🏃", "📅"}

SYSTEM_PROMPT = """You classify Cincinnati-area events for a daily digest.
For each event, return two things: an emoji and a list of musical artists.

EMOJI — choose ONE from this set:
⚾ MLB / baseball
🏈 NFL / football
🏀 basketball (any level)
⚽ soccer / MLS
🏒 hockey
🎭 theatre / play / musical / opera / burlesque
🎼 orchestra / symphony / classical / chamber
🎸 concert / live music / band / DJ / touring artist / rave / rap / rock
🎤 comedy / standup / improv
🎨 art / museum / exhibit / painting / gallery
🎪 festival / fair / carnival / outdoor community event
🍺 brewery / beer / tasting / food & drink
🏃 running / race / marathon / 5k
📅 other / unknown

ARTISTS — for music events (🎸 🎼), list the performing musical artists
named in the title. Rules:
- Include headliner and named support acts / special guests.
- Strip boilerplate: "FREE SHOW", "Tour", "presents", "w/ special guest",
  "feat.", venue names, series prefixes like "Live Music -" or
  "Jazz at the MEMO presents". Return just the artist/band names.
- Split on " / ", " w/ ", " with ", " and ", " & ", " featuring ".
- Shape example: "Band Name X Tour feat. Opener Y" -> ["Band Name", "Opener"]
- Return [] for karaoke / open mic / residency-series / cover-band nights
  (e.g. "Karaoke Mondays" -> [], "Open Mic" -> []).
- Return [] for comedy / standup / improv (🎤) — they have performers but
  often aren't on Spotify; keep the list scoped to musical acts.
- Return [] unconditionally for non-music events (theatre / art / festival
  / sports / brewery / running). Do NOT fill this field for 🎭 🎨 🎪 🍺 🏃
  ⚾ 🏈 🏀 ⚽ 🏒 📅.
- Only use names that appear in the title you are classifying — do not
  copy artist names from other events in the batch and do not invent.
- Keep capitalisation as the title has it when distinctive.

Cincinnati-specific hints (use these when they match):
- "Cyclones" at Heritage Bank Center = ECHL hockey → 🏒
- "Bengals" = NFL football → 🏈
- "Reds" = MLB baseball → ⚾
- "FC Cincinnati" = MLS soccer → ⚽
- "Bearcats" / "Musketeers" = UC/Xavier college sports (usually 🏀 or 🏈)
- Brady Music Center / Bogart's / MegaCorp Pavilion / Riverbend / MOTR Pub /
  Woodward Theater = music venues → usually 🎸 unless title clearly says
  comedy (🎤), theatre (🎭), burlesque (🎭), or orchestra (🎼)
- Playhouse in the Park / Aronoff = theatre venues → 🎭
- CSO / Music Hall = classical → 🎼

Respond with a single JSON object:
  {"events": [{"emoji": "🎸", "artists": ["Ethel Cain"]}, ...]}
One entry per input event, in the same order. No prose, no code fences, nothing else."""


def classify_batch(inputs: List[Tuple[int, str, str]]) -> Dict[int, Tuple[str, List[str]]]:
    """Classify a list of (event_id, title, venue_name) tuples in a single
    LiteLLM call. Returns {event_id: (emoji, artists)} for whichever entries
    the model returned a valid response for. Safe to call with an empty list.

    `artists` is always a list — empty when no musical artist belongs with
    the event (sports, theatre, karaoke/open-mic, non-music in general).
    """
    if not inputs or not LLM_ENABLED:
        return {}

    lines = [f'{i+1}. "{title}" @ {venue or "?"}' for i, (_, title, venue) in enumerate(inputs)]
    try:
        resp = requests.post(
            f"{LITELLM_URL}/chat/completions",
            headers={"Authorization": f"Bearer {LITELLM_KEY}", "Content-Type": "application/json"},
            json={
                "model": LLM_MODEL,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": "Events:\n" + "\n".join(lines)},
                ],
                "max_tokens": 1200,
                "temperature": 0,
            },
            timeout=60,
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"[llm] call failed: {e}")
        return {}

    content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content).strip()
    try:
        parsed = json.loads(content)
        events_out = parsed.get("events") or []
    except Exception as e:
        print(f"[llm] parse failed ({e}), raw: {content[:120]!r}")
        return {}

    out: Dict[int, Tuple[str, List[str]]] = {}
    for (event_id, _, _), row in zip(inputs, events_out):
        if not isinstance(row, dict):
            continue
        emoji = row.get("emoji") or ""
        artists = row.get("artists") or []
        if not isinstance(artists, list):
            artists = []
        # Defensive: strip, drop empties, cap at 8 to bound blast radius.
        artists = [a.strip() for a in artists if isinstance(a, str) and a.strip()][:8]
        if emoji in ALLOWED_EMOJI:
            out[event_id] = (emoji, artists)
    return out
