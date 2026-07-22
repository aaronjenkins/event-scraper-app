import type { CincyEvent } from "../types";

interface Props {
  events: CincyEvent[];
}

function sourceLabel(src: string, events: CincyEvent[]): string {
  if (src.startsWith("venue:")) {
    const evt = events.find((e) => e.source === src && e.venue);
    if (evt?.venue) return evt.venue;
  }
  if (src.startsWith("espn:")) {
    const team = src.slice(5);
    return `ESPN — ${team.charAt(0).toUpperCase()}${team.slice(1)}`;
  }
  if (src === "serpapi") return "Search (SerpAPI)";
  return src;
}

export function StickyPost({ events }: Props) {
  const counts = new Map<string, number>();
  for (const e of events) {
    const key = e.source || "unknown";
    counts.set(key, (counts.get(key) ?? 0) + 1);
  }
  const sorted = Array.from(counts.entries())
    .map(([src, n]) => ({ src, label: sourceLabel(src, events), n }))
    .sort((a, b) => b.n - a.n || a.label.localeCompare(b.label));

  return (
    <div className="thread sticky">
      <div className="post op">
        <div className="post-meta">
          <span className="subject">Sources</span>{" "}
          <span className="sticky-tag">[Sticky]</span>
        </div>
        <details className="sticky-body">
          <summary>show / hide</summary>
          <ul className="source-list">
            {sorted.map(({ src, label, n }) => (
              <li key={src}>
                <span className="source-name">{label}</span>
                <span className="source-count"> ({n})</span>
              </li>
            ))}
          </ul>
        </details>
      </div>
    </div>
  );
}
