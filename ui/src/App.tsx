import { useEffect, useState } from "react";
import type { EventsPayload } from "./types";
import { Agenda } from "./components/Agenda";
import { StickyPost } from "./components/StickyPost";

const EVENTS_URL = "./data/events.json";

export default function App() {
  const [payload, setPayload] = useState<EventsPayload | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch(EVENTS_URL, { cache: "no-store" })
      .then((r) => {
        if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
        return r.json() as Promise<EventsPayload>;
      })
      .then(setPayload)
      .catch((e: Error) => setError(e.message));
  }, []);

  return (
    <main className="app">
      <header className="app-header">
        <h1>Local Events</h1>
        {payload && (
          <div className="meta">
            {payload.event_count} events over the next {payload.lookahead_days} days ·
            generated {new Date(payload.generated_at).toLocaleString()}
          </div>
        )}
      </header>

      {error && <div className="error">Failed to load events: {error}</div>}
      {!error && !payload && <div className="loading">Loading…</div>}
      {payload && (
        <>
          <StickyPost events={payload.events} />
          <Agenda events={payload.events} />
        </>
      )}
    </main>
  );
}
