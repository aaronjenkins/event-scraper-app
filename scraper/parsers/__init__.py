from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional


@dataclass
class ParsedEvent:
    """Output of a parser. Not the same as bot's Event — this type
    is the contract for what scraper writes to events.events.
    """
    title: str
    start: datetime
    url: str
    end: Optional[datetime] = None
    venue_display: str = ""   # sub-venue override (e.g. a room inside a multi-space venue)
    raw_source: str = ""      # parser key or sub-identifier for debugging
    time_known: bool = True   # False when only a date was parseable — renderers should show "TBA"


from . import ics_parser
from . import json_ld
from . import espn_json
from . import serpapi_search

PARSERS = {
    "ics":            ics_parser.parse,
    "json_ld":        json_ld.parse,
    "espn_json":      espn_json.parse,
    "serpapi_search": serpapi_search.parse,
}

__all__ = ["ParsedEvent", "PARSERS"]
