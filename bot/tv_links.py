"""Per-league streaming entry points for ESPN-sourced events.

Keyed off the ESPN league path (matching ``ESPN_TEAMS[*]['league']`` in
``config.py``). The ``broadcast`` text label that ESPN already provides
(a regional sports network, etc.) is shown next to the title; these chips give
the reader a clickable jump to the canonical streaming home for the
league. Per-game watch URLs aren't reliably available from ESPN's public
endpoint, so we settle for the league-wide entry point — good enough in
~80% of cases without scraping a paywalled provider.
"""

from typing import List, TypedDict


class TvLink(TypedDict):
    label: str
    url: str


_LEAGUE_TV_LINKS: dict[str, List[TvLink]] = {
    "football/nfl": [
        {"label": "NFL+", "url": "https://www.nfl.com/plus/"},
    ],
    "baseball/mlb": [
        {"label": "MLB.tv", "url": "https://www.mlb.com/tv"},
    ],
    "soccer/usa.1": [
        {"label": "MLS Season Pass", "url": "https://tv.apple.com/mls"},
    ],
    "football/college-football": [
        {"label": "ESPN+", "url": "https://plus.espn.com/"},
    ],
    "basketball/mens-college-basketball": [
        {"label": "ESPN+", "url": "https://plus.espn.com/"},
    ],
}


def for_league(league: str) -> List[TvLink]:
    """Return the canonical streaming chips for an ESPN league path.

    Unknown leagues return an empty list — caller renders nothing.
    """
    return list(_LEAGUE_TV_LINKS.get(league, []))
