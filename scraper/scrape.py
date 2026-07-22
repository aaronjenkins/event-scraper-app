"""scraper — DB-driven scheduled scraper.

A single systemd timer fires `scrape.py` every 5 minutes. It reads
events.venues, checks each row's cron schedule against last_fetched_at,
fetches anything that is due, writes the raw page into the snapshot path, and
logs the result. No per-venue timers, no hand-written site modules.
"""
import argparse
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional
from zoneinfo import ZoneInfo

import os

import requests
from croniter import croniter

from db import Venue, list_venues, record_fetch, upsert_events, set_event_emoji, set_event_artists, get_event, set_parsed_count
from llm import classify_batch
from parsers import PARSERS

DEFAULT_CACHE_ROOT = Path("/var/cache/eventscraper")
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; scraper/1.0; scheduled archiver)",
    "Accept": "text/html,application/xhtml+xml,text/calendar,*/*",
}

RENDER_URL = os.environ.get("RENDER_URL", "http://localhost:7250")
RENDER_API_KEY = os.environ.get("RENDER_API_KEY", "changeme")
RENDER_TIMEOUT_MS = int(os.environ.get("RENDER_TIMEOUT_MS", "60000"))

# Parser-collapse alert target: an optional Signal-sending webhook. Creds come
# from the environment; alerts are silently skipped if they're unset.
SIGNAL_WEBHOOK_URL = os.environ.get("SIGNAL_WEBHOOK_URL", "http://localhost:7200")
SIGNAL_WEBHOOK_KEY = os.environ.get("SIGNAL_WEBHOOK_KEY", "")
SIGNAL_GROUP_ID = os.environ.get("SIGNAL_GROUP_ID", "")


def _signal_creds():
    """Return (api_key, group_id) from the environment, or (None, None)."""
    if SIGNAL_WEBHOOK_KEY and SIGNAL_GROUP_ID:
        return SIGNAL_WEBHOOK_KEY, SIGNAL_GROUP_ID
    return None, None


def post_to_signal(message: str) -> None:
    """Fire-and-forget Signal post via the Signal webhook. Alerts never block the scrape."""
    key, gid = _signal_creds()
    if not key or not gid:
        print("[scraper] the Signal webhook creds not available, skipping Signal alert", file=sys.stderr)
        return
    try:
        requests.post(
            f"{SIGNAL_WEBHOOK_URL}/send",
            json={"message": message, "api_key": key, "group_id": gid, "priority": 3},
            timeout=10,
        )
    except requests.RequestException as e:
        print(f"[scraper] the Signal webhook /send failed: {e}", file=sys.stderr)


def snapshot_path_for(v: Venue) -> Path:
    if v.snapshot_path:
        return Path(v.snapshot_path)
    return DEFAULT_CACHE_ROOT / v.slug / "latest.html"


def is_due(v: Venue, now: datetime) -> bool:
    base = v.last_fetched_at or datetime.fromtimestamp(0, tz=timezone.utc)
    try:
        nxt = croniter(v.schedule, base).get_next(datetime)
    except Exception as e:
        print(f"[scraper:{v.slug}] bad schedule {v.schedule!r}: {e}", file=sys.stderr)
        return False
    return nxt <= now


# Substitutes ${VAR} tokens in the venue URL with environment values at
# fetch time. Lets us store API-keyed endpoints (SerpAPI etc.) in the
# venues table without writing the secret into the DB. Unknown vars are
# left literal so missing-key misconfigurations show up loudly in the
# fetch_log instead of silently producing a malformed URL.
_URL_VAR_RE = re.compile(r"\$\{(\w+)\}")


def _expand_url(url: str) -> str:
    return _URL_VAR_RE.sub(lambda m: os.environ.get(m.group(1), m.group(0)), url)


def _fetch_static(v: Venue) -> bytes:
    resp = requests.get(_expand_url(v.url), headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.content


def _fetch_browser(v: Venue) -> bytes:
    resp = requests.post(
        f"{RENDER_URL}/render",
        json={
            "url": v.url,
            "api_key": RENDER_API_KEY,
            "wait_for": v.render_wait_selector,
            "timeout_ms": RENDER_TIMEOUT_MS,
        },
        timeout=(RENDER_TIMEOUT_MS // 1000) + 10,
    )
    resp.raise_for_status()
    payload = resp.json()
    return payload["html"].encode("utf-8")


def _fetch_capture(v: Venue) -> bytes:
    """Navigate to v.url in a real browser, wait for an XHR whose URL
    contains v.render_capture_match, return that XHR's response body.

    Used for SPAs that build their data payload via a session-authenticated
    XHR we can't easily reproduce by hand. See the render service /capture."""
    if not v.render_capture_match:
        raise RuntimeError("render_mode='capture' requires render_capture_match")
    resp = requests.post(
        f"{RENDER_URL}/capture",
        json={
            "url": v.url,
            "match_url": v.render_capture_match,
            "api_key": RENDER_API_KEY,
            "timeout_ms": RENDER_TIMEOUT_MS,
            "wait_after_load_ms": 15000,
        },
        timeout=(RENDER_TIMEOUT_MS // 1000) + 30,
    )
    resp.raise_for_status()
    payload = resp.json()
    if payload.get("body_is_base64"):
        import base64
        return base64.b64decode(payload["body"])
    return payload["body"].encode("utf-8")


def fetch_one(v: Venue) -> tuple[bool, int, int, Optional[str]]:
    if not v.url:
        return False, 0, 0, "no url configured"
    start = time.monotonic()
    try:
        if v.render_mode == "capture":
            body = _fetch_capture(v)
        elif v.render_mode == "browser":
            body = _fetch_browser(v)
        else:
            body = _fetch_static(v)
    except Exception as e:
        duration = int((time.monotonic() - start) * 1000)
        return False, 0, duration, str(e)[:500]

    duration = int((time.monotonic() - start) * 1000)
    target = snapshot_path_for(v)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(body)
    return True, len(body), duration, None


def run_due(force_slugs: Optional[List[str]] = None) -> int:
    now = datetime.now(timezone.utc)
    venues = list_venues()
    to_run: List[Venue] = []
    for v in venues:
        if force_slugs:
            if v.slug in force_slugs:
                to_run.append(v)
        elif is_due(v, now):
            to_run.append(v)

    if not to_run:
        print(f"[scraper] nothing due (checked {len(venues)} venues)")
        return 0

    errors = 0
    # (slug, name, previous_count, current_count) for venues whose parser
    # produced 0 OR sharply fewer rows this run vs the prior successful run.
    # Collapses (->0) and sharp drops (-50%) surface under the same alert.
    collapses: List[tuple] = []
    stuck: List[Venue] = []

    for v in to_run:
        ok, size, duration, err = fetch_one(v)
        if ok:
            print(f"[scraper:{v.slug}] wrote {size} bytes in {duration}ms -> {snapshot_path_for(v)}")
        else:
            errors += 1
            print(f"[scraper:{v.slug}] FAILED in {duration}ms: {err}", file=sys.stderr)
        record_fetch(v.id, ok=ok, bytes_=size, duration_ms=duration, error=err)
        if ok:
            try:
                count = parse_and_upsert(v)
            except Exception as e:
                print(f"[scraper:{v.slug}] parse/upsert crashed: {e}", file=sys.stderr)
                count = None
            if count is not None:
                prev = v.last_parsed_count
                if _is_sharp_drop(prev, count):
                    collapses.append((v.slug, v.name, prev, count))
                elif _is_stuck_at_zero(v, prev, count):
                    stuck.append(v)
                set_parsed_count(v.id, count)

    if collapses:
        lines = ["📉 scraper parser drop alert:"]
        for slug, name, prev, cur in collapses:
            arrow = "→" if cur > 0 else "→ 0"
            lines.append(f"- {name} ({slug}): {prev} {arrow}{'' if cur == 0 else f' {cur}'}")
        lines.append("")
        lines.append("Site likely redesigned, partially broken, or the parser regressed. Check the snapshot at /var/cache/eventscraper/<slug>/latest.html against the parser.")
        post_to_signal("\n".join(lines))
        print(f"[scraper] parser-drop alert sent for {len(collapses)} venue(s)")

    if stuck:
        lines = ["🕳️ scraper parsers stuck at zero:"]
        for v in stuck:
            lines.append(f"- {v.name} ({v.slug}): fetched OK, `{v.parser}` parsed 0")
        lines.append("")
        lines.append("These fetched fine but produced nothing, so the run still looks green. Usually the site was redesigned out from under the parser, or the listings moved to another URL. Compare /var/cache/eventscraper/<slug>/latest.html against the parser.")
        lines.append("")
        lines.append("If the source is legitimately empty (e.g. off-season), silence it with:")
        lines.append("UPDATE events.venues SET allow_zero_parse = true WHERE slug = '<slug>';")
        post_to_signal("\n".join(lines))
        print(f"[scraper] stuck-at-zero alert sent for {len(stuck)} venue(s)")

    try:
        write_status_page()
    except Exception as e:
        print(f"[scraper] status page write failed (non-fatal): {e}", file=sys.stderr)

    return 1 if errors else 0


WIKI_ENABLED = os.environ.get("SCRAPER_WIKI_STATUS", "1") != "0"
OUTPUTS_WRITE_BIN = os.environ.get("OUTPUTS_WRITE_BIN", "/opt/eventscraper/outputs-write.sh")
# Path under outputs.git root. Renders at /outputs/scraper/status/ once
# docs-viewer's refresh.sh picks up the new commit.
WIKI_TARGET = "scraper/status.md"
LOCAL_TZ = ZoneInfo("America/New_York")


def _humanise_age(dt: Optional[datetime], now: datetime) -> str:
    """Render an age like '4h ago' / '3d ago' / 'never' for the status table."""
    if dt is None:
        return "never"
    delta = now - dt
    secs = int(delta.total_seconds())
    if secs < 60:
        return f"{secs}s ago"
    if secs < 3600:
        return f"{secs // 60}m ago"
    if secs < 86400:
        return f"{secs // 3600}h ago"
    return f"{secs // 86400}d ago"


def _build_status_markdown() -> str:
    now = datetime.now(timezone.utc)
    now_local = now.astimezone(LOCAL_TZ)
    venues = list_venues(enabled_only=False)

    lines = [
        "---",
        f"updated: {now_local.strftime('%Y-%m-%d %H:%M %Z')}",
        "---",
        "",
        "# scraper status",
        "",
        "Auto-generated at the end of every `scrape.py` tick. Last-parsed count and last fetch age per venue. Disabled venues and venues that have never been fetched surface here too — silent never-fires would otherwise fade out of attention.",
        "",
        f"_Updated {now_local.strftime('%b %d, %Y at %-I:%M %p %Z')} by the scraper._",
        "",
        "| Venue | Parser | Mode | Enabled | Last fetched | Last count |",
        "|---|---|---|---|---|---|",
    ]
    total = 0
    for v in venues:
        name_cell = f"[{v.name}]({v.url})" if v.url else v.name
        enabled = "✓" if v.enabled else "—"
        fetched = _humanise_age(v.last_fetched_at, now)
        count = "—" if v.last_parsed_count is None else str(v.last_parsed_count)
        if v.last_parsed_count:
            total += v.last_parsed_count
        lines.append(
            f"| {name_cell} | `{v.parser}` | {v.render_mode} | {enabled} | {fetched} | {count} |"
        )
    lines.append("")
    lines.append(f"**Total events across all venues on their last successful parse: {total}.**")
    return "\n".join(lines)


def write_status_page() -> None:
    """Commit scraper/status.md into outputs.git via outputs-write.sh.

    Replaces the docker-cp/docker-exec OtterWiki path that was retired on
    2026-04-25. Never fatal — failures print to stderr, scrape.py exits
    normally so a wiki blip doesn't take the scrape down."""
    if not WIKI_ENABLED:
        return
    md = _build_status_markdown()
    try:
        result = subprocess.run(
            [
                OUTPUTS_WRITE_BIN, WIKI_TARGET, "-",
                "scraper: status refresh",
                "scraper@localhost", "scraper",
            ],
            input=md, capture_output=True, text=True, timeout=120,
        )
        if result.returncode != 0:
            print(
                f"[scraper] outputs-write failed (rc={result.returncode}): "
                f"{result.stderr[:300]}",
                file=sys.stderr,
            )
    except (OSError, subprocess.SubprocessError) as e:
        print(f"[scraper] outputs-write error: {e}", file=sys.stderr)


def _is_sharp_drop(prev: Optional[int], current: int) -> bool:
    """Should the current parse trigger a drop alert?

    Fires when:
      - prior run produced >0 events, AND
      - this run produced <=0 events (hard collapse), OR
      - this run produced <50% of prior AND the absolute drop is >=5.

    The >=5 floor keeps small venues (Ensemble: 3 events) from
    triggering on every week-to-week minor shuffle. The <50% keeps
    established venues (NYC: 30 events) from suppressing a real
    regression when they drift to a handful of rows.
    """
    if prev is None or prev <= 0:
        return False
    if current <= 0:
        return True
    if current < prev * 0.5 and (prev - current) >= 5:
        return True
    return False


def _is_stuck_at_zero(v: Venue, prev: Optional[int], current: int) -> bool:
    """Should this parse trigger a stuck-at-zero nag?

    _is_sharp_drop only fires on the >0 -> 0 transition, so a venue that
    stays broken goes quiet after a single alert and can sit dead for
    months — the fetch still succeeds, the run still exits 0, and
    Healthchecks stays green. CSO and Ensemble both hid that way.

    This covers the flat-zero case _is_sharp_drop deliberately skips:
      - prev == 0: still broken since some earlier run.
      - prev is None: never parsed anything since being added, which
        _is_sharp_drop also can't see (it returns False on None).

    The two are mutually exclusive by construction, so a venue is never
    reported by both in the same tick.
    """
    if v.allow_zero_parse:
        return False
    if current > 0:
        return False
    return prev is None or prev == 0


def parse_and_upsert(v: Venue) -> Optional[int]:
    """Parse the venue's cached snapshot and upsert. Returns the number of
    rows the parser produced this run (or None if the parser could not be
    run — snapshot missing, parser unregistered, parser raised). Used by
    run_due to detect parser-collapse transitions."""
    parser = PARSERS.get(v.parser)
    if parser is None:
        print(f"[parse:{v.slug}] no parser registered for {v.parser!r}")
        return None
    path = snapshot_path_for(v)
    try:
        body = path.read_bytes()
    except OSError as e:
        print(f"[parse:{v.slug}] snapshot read failed: {e}")
        return None
    try:
        rows = parser(v, body)
    except Exception as e:
        print(f"[parse:{v.slug}] parser crashed: {e}")
        return None

    inserted, updated, deleted = upsert_events(v.id, rows)
    print(
        f"[parse:{v.slug}] {len(rows)} parsed → "
        f"+{len(inserted)} new, ~{len(updated)} refreshed, -{len(deleted)} stale"
    )

    if inserted:
        classify_inputs = []
        for eid in inserted:
            row = get_event(eid)
            if row:
                classify_inputs.append((eid, row["title"], row["venue_name"]))
        classifications = classify_batch(classify_inputs)
        for eid, (emoji, artists) in classifications.items():
            set_event_emoji(eid, emoji)
            set_event_artists(eid, artists)
        if classifications:
            artist_count = sum(1 for _, a in classifications.values() if a)
            print(f"[parse:{v.slug}] classified {len(classifications)}/{len(inserted)} new events ({artist_count} with artists)")

    return len(rows)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--slug", action="append", help="force-fetch this venue (may repeat); ignores schedule")
    parser.add_argument("--list", action="store_true", help="list venues and their next-due time then exit")
    args = parser.parse_args()

    if args.list:
        now = datetime.now(timezone.utc)
        for v in list_venues(enabled_only=False):
            base = v.last_fetched_at or datetime.fromtimestamp(0, tz=timezone.utc)
            try:
                nxt = croniter(v.schedule, base).get_next(datetime)
                nxt_str = nxt.isoformat()
            except Exception as e:
                nxt_str = f"BAD ({e})"
            enabled = "on " if v.enabled else "off"
            last = v.last_fetched_at.isoformat() if v.last_fetched_at else "never"
            print(f"{enabled} {v.slug:<22} parser={v.parser:<16} schedule={v.schedule:<12} last={last} next={nxt_str}")
        return 0

    return run_due(force_slugs=args.slug)


if __name__ == "__main__":
    sys.exit(main())
