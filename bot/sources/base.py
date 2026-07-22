from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, TypedDict


class TvLink(TypedDict):
    label: str
    url: str


@dataclass
class Event:
    title: str
    start: datetime
    venue: str = ""
    end: Optional[datetime] = None
    url: str = ""
    source: str = ""
    time_display: Optional[str] = None  # overrides start.strftime in the digest
    emoji: str = ""
    broadcast: str = ""  # TV network / streaming label shown next to the title (ESPN-sourced)
    artists: List[str] = field(default_factory=list)  # musical artists for 🎸/🎼/🎤 events; empty otherwise
    tv_links: List[TvLink] = field(default_factory=list)  # canonical streaming chips for sports events

    def day_key(self) -> str:
        return self.start.strftime("%Y-%m-%d")
