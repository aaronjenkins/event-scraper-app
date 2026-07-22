import type { CincyEvent } from "../types";
import { EventCard } from "./EventCard";

interface Props {
  events: CincyEvent[];
}

function formatDayHeader(isoDate: string): string {
  // Parse YYYY-MM-DD as local-date (no TZ shift) for the heading.
  const [y, m, d] = isoDate.split("-").map(Number);
  const dt = new Date(y, m - 1, d);
  return dt.toLocaleDateString(undefined, {
    weekday: "long",
    month: "short",
    day: "numeric",
  });
}

export function Agenda({ events }: Props) {
  if (events.length === 0) {
    return <div className="empty">No upcoming events.</div>;
  }

  const groups = new Map<string, CincyEvent[]>();
  for (const e of events) {
    const list = groups.get(e.date) ?? [];
    list.push(e);
    groups.set(e.date, list);
  }
  const days = Array.from(groups.keys()).sort();

  return (
    <>
      {days.map((date) => (
        <section className="day" key={date}>
          <h2 className="day-header">{formatDayHeader(date)}</h2>
          {groups.get(date)!.map((e, i) => (
            <EventCard key={`${date}-${i}`} event={e} />
          ))}
        </section>
      ))}
    </>
  );
}
