"""Event -> emoji classification."""
import re

DEFAULT_EMOJI = "📅"

# ESPN league path prefix -> emoji (matched via startswith).
ESPN_LEAGUE_EMOJI = {
    "baseball/mlb":                          "⚾",
    "football/nfl":                          "🏈",
    "football/college-football":             "🏈",
    "basketball/mens-college-basketball":    "🏀",
    "basketball/womens-college-basketball":  "🏀",
    "basketball/nba":                        "🏀",
    "soccer":                                "⚽",
    "hockey":                                "🏒",
}

# Keyword -> emoji. Order matters: first match wins. Keys are case-insensitive
# word-boundary regex fragments; values are the emoji to stamp.
KEYWORD_RULES = [
    (r"\b(symphony|orchestra|philharmonic)\b",                        "🎼"),
    (r"\b(theatre|theater|playhouse|broadway|musical|play|opera)\b",  "🎭"),
    (r"\b(comedy|comedian|standup|stand[- ]up|improv)\b",             "🎤"),
    (r"\b(concert|band|tour|live music|dj|rap|rock|pop|jazz|blues)\b","🎸"),
    (r"\b(art|museum|exhibit|gallery|contemporary arts)\b",           "🎨"),
    (r"\b(festival|fair|carnival|fest)\b",                            "🎪"),
    (r"\b(brewery|beer|tasting|wine|distillery|cider)\b",             "🍺"),
    (r"\b(marathon|5k|10k|race|run|running)\b",                       "🏃"),
    (r"\b(baseball|reds|mlb)\b",                                      "⚾"),
    (r"\b(football|bengals|nfl)\b",                                   "🏈"),
    (r"\b(basketball|bearcats|musketeers|nba|ncaa)\b",                "🏀"),
    (r"\b(soccer|mls)\b",                                             "⚽"),
    (r"\b(hockey|nhl|ice)\b",                                         "🏒"),
]

_COMPILED = [(re.compile(p, re.IGNORECASE), e) for p, e in KEYWORD_RULES]


def classify_by_source(source: str) -> str:
    """Return an emoji for structured sources that already know the category."""
    if source.startswith("espn:"):
        return DEFAULT_EMOJI  # caller should use classify_espn instead
    return ""


def classify_espn(league: str) -> str:
    for prefix, emoji in ESPN_LEAGUE_EMOJI.items():
        if league.startswith(prefix):
            return emoji
    return DEFAULT_EMOJI


def classify_text(text: str) -> str:
    """Keyword-match a title/venue blob for SerpAPI and ICS events."""
    if not text:
        return DEFAULT_EMOJI
    for pat, emoji in _COMPILED:
        if pat.search(text):
            return emoji
    return DEFAULT_EMOJI
