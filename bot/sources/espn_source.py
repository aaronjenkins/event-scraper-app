"""ESPN public schedule source.

Queries ESPN's unauthenticated JSON schedule endpoint per (league_path, team_id)
configured in config.ESPN_TEAMS. Offseason teams return zero events and are
silently skipped.
"""
from datetime import datetime, timezone
from typing import List

import requests

import tv_links
from classify import classify_espn
from config import ESPN_TEAMS
from .base import Event

API = "https://site.api.espn.com/apis/site/v2/sports/{league}/teams/{team_id}/schedule"


def _is_home(comp: dict, team_id: str) -> bool:
    for c in comp.get("competitors") or []:
        if str(c.get("id")) == str(team_id):
            return c.get("homeAway") == "home"
    return False


def _pick_broadcast(comp: dict, is_home_game: bool) -> str:
    """Pick the most relevant TV/streaming broadcast label for a competition.

    ESPN returns broadcasts[] with each entry shaped:
      {"type": {"shortName": "TV"|"Streaming"|"Radio"},
       "market": {"type": "National"|"Home"|"Away"},
       "media": {"shortName": "WXIX FOX19"}}

    Preference order (prefer the channel someone in Cincinnati can actually watch on):
      1. Home-market TV
      2. National TV (ESPN, FOX, TBS for post-season)
      3. Home-market streaming (e.g. MLB.TV blackout-free home feed)
      4. National streaming
    Away-market entries (visiting team's regional network) are always skipped
    because they'd be blacked out locally.
    """
    broadcasts = comp.get("broadcasts") or []
    priorities = {
        ("TV", "Home"): 0,
        ("TV", "National"): 1,
        ("Streaming", "Home"): 2,
        ("Streaming", "National"): 3,
    }
    best_rank = 99
    best_label = ""
    for b in broadcasts:
        btype = ((b.get("type") or {}).get("shortName")) or ""
        market = ((b.get("market") or {}).get("type")) or ""
        key = (btype, market)
        if key not in priorities:
            continue
        rank = priorities[key]
        if rank < best_rank:
            label = ((b.get("media") or {}).get("shortName")) or ""
            if label:
                best_rank = rank
                best_label = label
    return best_label


def _fetch_team(label: str, league: str, team_id: str, home_only: bool) -> List[Event]:
    url = API.format(league=league, team_id=team_id)
    try:
        resp = requests.get(url, timeout=20, headers={
            "User-Agent": "Mozilla/5.0 (compatible; bot/1.0)",
        })
        resp.raise_for_status()
        payload = resp.json()
    except Exception as e:
        print(f"[espn:{label}] fetch failed: {e}")
        return []

    team_name = (payload.get("team") or {}).get("displayName", label)
    league_tv_links = tv_links.for_league(league)
    out: List[Event] = []
    skipped_away = 0
    for e in payload.get("events") or []:
        try:
            dt_str = e.get("date")
            if not dt_str:
                continue
            comp = (e.get("competitions") or [{}])[0]
            if home_only and not _is_home(comp, team_id):
                skipped_away += 1
                continue
            start = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
            name = e.get("name") or e.get("shortName") or "Game"
            venue = ((comp.get("venue") or {}).get("fullName")) or ""
            is_home = _is_home(comp, team_id)
            out.append(Event(
                title=name,
                start=start,
                venue=venue,
                url=(e.get("links") or [{}])[0].get("href", ""),
                source=f"espn:{label}",
                emoji=classify_espn(league),
                broadcast=_pick_broadcast(comp, is_home),
                tv_links=list(league_tv_links),
            ))
        except Exception as ex:
            print(f"[espn:{label}] skipping event: {ex}")
    if out or skipped_away:
        print(f"[espn:{label}] {team_name}: {len(out)} home, {skipped_away} away skipped")
    return out


def fetch() -> List[Event]:
    if not ESPN_TEAMS:
        return []
    out: List[Event] = []
    for entry in ESPN_TEAMS:
        out.extend(_fetch_team(
            entry["label"],
            entry["league"],
            entry["team_id"],
            entry.get("home_only", False),
        ))
    return out
