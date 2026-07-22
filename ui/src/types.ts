export interface SpotifySearch {
  name: string;
  url: string;
}

export interface YoutubeSearch {
  name: string;
  url: string;
}

export interface TvLink {
  label: string;
  url: string;
}

export interface CincyEvent {
  date: string;          // YYYY-MM-DD (local)
  time: string | null;   // "7:30 PM" or null for all-day / TBA
  title: string;
  venue: string;
  url: string;           // event page; may be ""
  emoji: string;         // 🎸 🎼 ⚾ 🎭 ...
  source: string;        // espn:<team>, venue:<slug>, serpapi, ...
  broadcast: string;     // free-text channel label from ESPN (may be "")
  tv_links: TvLink[];    // canonical streaming entry points for sports
  spotify_searches: SpotifySearch[];
  youtube_searches: YoutubeSearch[];
}

export interface EventsPayload {
  generated_at: string;     // ISO timestamp
  lookahead_days: number;
  event_count: number;
  events: CincyEvent[];
}
