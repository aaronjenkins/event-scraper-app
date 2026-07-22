"""LLM-backed event classifier via LiteLLM.

ESPN events already have an accurate emoji from league metadata, so this only
re-classifies non-ESPN events (SerpAPI, ICS) where keyword matching is lossy.
One call per run; on any failure we keep the existing keyword classification.
"""
import json
import os
import re
from typing import List

import requests

from sources.base import Event

LITELLM_URL = os.environ.get("LITELLM_URL", "http://localhost:4000")
LITELLM_KEY = os.environ.get("LITELLM_KEY", "changeme")
LLM_MODEL = os.environ.get("BOT_LLM_MODEL", "claude-haiku")
LLM_ENABLED = os.environ.get("BOT_LLM", "1") != "0"

ALLOWED_EMOJI = ["⚾","🏈","🏀","⚽","🏒","🎭","🎼","🎸","🎤","🎨","🎪","🍺","🏃","📅"]

SYSTEM_PROMPT = """You classify Cincinnati-area events for a daily digest.
For each event, choose ONE emoji from this set:
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

Respond with a single JSON object: {"emojis": ["🎭","⚾",...]}. One entry per
input event, in the same order. No prose, no code fences, nothing else."""


def _reclassify(events: List[Event]) -> None:
    if not events:
        return
    lines = [f'{i+1}. "{e.title}"' + (f" @ {e.venue}" if e.venue else "") for i, e in enumerate(events)]
    user = "Events:\n" + "\n".join(lines)

    try:
        resp = requests.post(
            f"{LITELLM_URL}/chat/completions",
            headers={"Authorization": f"Bearer {LITELLM_KEY}", "Content-Type": "application/json"},
            json={
                "model": LLM_MODEL,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user},
                ],
                "max_tokens": 512,
                "temperature": 0,
            },
            timeout=30,
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"[llm] call failed, keeping keyword emojis: {e}")
        return

    # Strip optional code fences the model sometimes adds anyway.
    content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content).strip()
    try:
        payload = json.loads(content)
        emojis = payload.get("emojis") or []
    except Exception as e:
        print(f"[llm] parse failed ({e}), raw: {content[:120]!r}")
        return

    if len(emojis) != len(events):
        # Apply what we got to the matching positions and leave the rest on
        # their keyword fallback. Dropping everything on a single off-by-one
        # used to blank the whole digest.
        print(f"[llm] count mismatch: got {len(emojis)} for {len(events)} events, applying partial")

    for event, emoji in zip(events, emojis):
        if emoji in ALLOWED_EMOJI:
            event.emoji = emoji


def reclassify_non_espn(events: List[Event]) -> None:
    """Re-stamp emoji on events whose source is not ESPN. ESPN events keep
    their league-based emoji which is always correct."""
    if not LLM_ENABLED:
        return
    targets = [e for e in events if not e.source.startswith("espn:")]
    _reclassify(targets)
