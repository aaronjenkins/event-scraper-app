import type { CincyEvent } from "../types";
import { downloadIcs } from "../lib/ics";

interface Props {
  event: CincyEvent;
}

type ReplyGroup = {
  kind: "tv" | "spotify" | "youtube";
  items: { label: string; href: string }[];
};

export function EventCard({ event }: Props) {
  const groups: ReplyGroup[] = [
    {
      kind: "tv" as const,
      items: event.tv_links.map((tv) => ({ label: tv.label, href: tv.url })),
    },
    {
      kind: "spotify" as const,
      items: event.spotify_searches.map((s) => ({ label: s.name, href: s.url })),
    },
    {
      kind: "youtube" as const,
      items: event.youtube_searches.map((y) => ({ label: y.name, href: y.url })),
    },
  ].filter((g) => g.items.length > 0);

  return (
    <div className="thread">
      <div className="post op">
        <div className="post-meta">
          <span className="subject">{event.title}</span>
        </div>
        <div className="post-body">
          {event.emoji && <div className="post-image">{event.emoji}</div>}
          {(event.time || event.venue) && (
            <div className="greentext">
              {[event.time, event.venue && `@ ${event.venue}`]
                .filter(Boolean)
                .join(" ")}
            </div>
          )}
          {event.broadcast && <div className="greentext">📺 {event.broadcast}</div>}
          {event.url && (
            <div className="post-link-row">
              <a href={event.url} target="_blank" rel="noreferrer">
                {event.url}
              </a>
            </div>
          )}
        </div>
      </div>

      <div className="post reply">
        <div className="post-body">
          <div className="post-link-list">
            <button
              type="button"
              className="post-action cal"
              onClick={() => downloadIcs(event)}
            >
              Add to calendar
            </button>
          </div>
        </div>
      </div>

      {groups.map((g) => {
        const subject =
          g.kind === "spotify"
            ? "Spotify"
            : g.kind === "youtube"
              ? "YouTube"
              : "Watch here";
        return (
          <div className="post reply" key={g.kind}>
            <div className="post-meta">
              <span className="subject">{subject}</span>
            </div>
            <div className="post-body">
              <div className="post-link-list">
                {g.items.map((item) => (
                  <a
                    key={item.href}
                    className={`post-action ${g.kind}`}
                    href={item.href}
                    target="_blank"
                    rel="noreferrer"
                  >
                    {item.label}
                  </a>
                ))}
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
