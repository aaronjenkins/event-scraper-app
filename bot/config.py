"""Runtime config for bot. Edit lists here to expand coverage."""
import os

LOOKAHEAD_DAYS = int(os.environ.get("LOOKAHEAD_DAYS", "7"))

CITY = "Your City"
STATE_CODE = "XX"

SERPAPI_ENABLED = bool(os.environ.get("SERP_API_KEY"))

# Venue registry lives in events.venues (Postgres). scraper fetches
# snapshots on schedule; sources.dispatch reads those snapshots and dispatches
# to parser-by-name. Add venues via SQL INSERT, not this file.

# ESPN public schedule endpoints. Offseason teams return zero events and are
# silently skipped. Set home_only=True to drop away games.
#   NFL           -> football/nfl
#   MLB           -> baseball/mlb
#   MLS           -> soccer/usa.1
#   NCAA FB       -> football/college-football
#   NCAA MBB      -> basketball/mens-college-basketball
# Your city's teams. team_id comes from the ESPN team-page URL
# (e.g. espn.com/nfl/team/_/name/cin -> 4). home_only drops away games.
ESPN_TEAMS = [
    # {"label": "my-nfl-team", "league": "football/nfl", "team_id": "0", "home_only": True},
    # {"label": "my-mlb-team", "league": "baseball/mlb", "team_id": "0", "home_only": True},
]

# Keyword filters (case-insensitive substring match on title+venue).
# Empty lists disable the filter.
KEYWORDS_ALLOW = []   # if non-empty, event must match at least one
KEYWORDS_BLOCK = []   # event is dropped if it matches any

# Fuzzy dedupe threshold (0-100). Higher = stricter.
DEDUPE_TITLE_THRESHOLD = 88
