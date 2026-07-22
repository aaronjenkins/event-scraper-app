import type { CincyEvent } from "../types";

const DEFAULT_DURATION_MIN = 120;
const TZID = "America/New_York";

const VTIMEZONE = [
  "BEGIN:VTIMEZONE",
  `TZID:${TZID}`,
  "BEGIN:DAYLIGHT",
  "TZOFFSETFROM:-0500",
  "TZOFFSETTO:-0400",
  "TZNAME:EDT",
  "DTSTART:19700308T020000",
  "RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=2SU",
  "END:DAYLIGHT",
  "BEGIN:STANDARD",
  "TZOFFSETFROM:-0400",
  "TZOFFSETTO:-0500",
  "TZNAME:EST",
  "DTSTART:19701101T020000",
  "RRULE:FREQ=YEARLY;BYMONTH=11;BYDAY=1SU",
  "END:STANDARD",
  "END:VTIMEZONE",
];

function escapeText(s: string): string {
  return s
    .replace(/\\/g, "\\\\")
    .replace(/\n/g, "\\n")
    .replace(/,/g, "\\,")
    .replace(/;/g, "\\;");
}

function pad(n: number): string {
  return n < 10 ? `0${n}` : String(n);
}

function parseTime(time: string): { hour: number; minute: number } | null {
  const m = time.trim().match(/^(\d{1,2}):(\d{2})\s*(AM|PM)?$/i);
  if (!m) return null;
  let hour = parseInt(m[1], 10);
  const minute = parseInt(m[2], 10);
  const mer = m[3]?.toUpperCase();
  if (mer === "PM" && hour < 12) hour += 12;
  if (mer === "AM" && hour === 12) hour = 0;
  return { hour, minute };
}

function localStamp(date: string, hour: number, minute: number): string {
  const [y, mo, d] = date.split("-");
  return `${y}${mo}${d}T${pad(hour)}${pad(minute)}00`;
}

function dateOnly(date: string): string {
  return date.replaceAll("-", "");
}

function addDays(date: string, n: number): string {
  const d = new Date(`${date}T00:00:00`);
  d.setDate(d.getDate() + n);
  return `${d.getFullYear()}${pad(d.getMonth() + 1)}${pad(d.getDate())}`;
}

function uid(event: CincyEvent): string {
  const slug = `${event.date}-${event.time ?? "allday"}-${event.title}`
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");
  return `${slug}@events`;
}

function nowStamp(): string {
  const d = new Date();
  return (
    `${d.getUTCFullYear()}${pad(d.getUTCMonth() + 1)}${pad(d.getUTCDate())}` +
    `T${pad(d.getUTCHours())}${pad(d.getUTCMinutes())}${pad(d.getUTCSeconds())}Z`
  );
}

export function buildIcs(event: CincyEvent): string {
  const parsed = event.time ? parseTime(event.time) : null;

  const lines: string[] = [
    "BEGIN:VCALENDAR",
    "VERSION:2.0",
    "PRODID:-//events//EN",
    "CALSCALE:GREGORIAN",
  ];
  if (parsed) lines.push(...VTIMEZONE);
  lines.push(
    "BEGIN:VEVENT",
    `UID:${uid(event)}`,
    `DTSTAMP:${nowStamp()}`,
  );

  if (parsed) {
    const start = localStamp(event.date, parsed.hour, parsed.minute);
    const endDate = new Date(`${event.date}T00:00:00`);
    endDate.setHours(parsed.hour, parsed.minute + DEFAULT_DURATION_MIN);
    const end =
      `${endDate.getFullYear()}${pad(endDate.getMonth() + 1)}${pad(endDate.getDate())}` +
      `T${pad(endDate.getHours())}${pad(endDate.getMinutes())}00`;
    lines.push(`DTSTART;TZID=${TZID}:${start}`, `DTEND;TZID=${TZID}:${end}`);
  } else {
    lines.push(
      `DTSTART;VALUE=DATE:${dateOnly(event.date)}`,
      `DTEND;VALUE=DATE:${addDays(event.date, 1)}`,
    );
  }

  lines.push(`SUMMARY:${escapeText((event.emoji ? event.emoji + " " : "") + event.title)}`);
  if (event.venue) lines.push(`LOCATION:${escapeText(event.venue)}`);
  if (event.url) lines.push(`URL:${event.url}`);

  const descParts: string[] = [];
  if (event.broadcast) descParts.push(`Broadcast: ${event.broadcast}`);
  if (event.url) descParts.push(event.url);
  if (descParts.length) {
    lines.push(`DESCRIPTION:${escapeText(descParts.join("\n"))}`);
  }

  lines.push("END:VEVENT", "END:VCALENDAR");
  return lines.join("\r\n");
}

export function downloadIcs(event: CincyEvent): void {
  const ics = buildIcs(event);
  const blob = new Blob([ics], { type: "text/calendar;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const slug = event.title
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "")
    .slice(0, 60);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${event.date}-${slug || "event"}.ics`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
