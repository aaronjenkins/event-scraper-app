# Signal digest sender

The bot and scraper post their daily digest / alerts to a webhook:

```
POST /send  { "message": "...", "group_id": "group.<id>", "api_key": "..." }
```

This folder is a minimal, self-contained implementation of that webhook on top of
[signal-cli-rest-api](https://github.com/bbernhard/signal-cli-rest-api).
`signal-webhook` (a ~40-line FastAPI shim, `webhook.py`) receives the app's
request and forwards it to signal-cli-rest-api's `/v2/send`. Both run via
`docker compose`.

You only need this if you want the Signal digest — the app runs fine without it.

## Setup

1. **Configure and start:**
   ```bash
   cp .env.example .env      # set SIGNAL_NUMBER (E.164) and SIGNAL_WEBHOOK_KEY
   docker compose up -d --build
   ```

2. **Link the sender to your Signal account** (easiest — no new number needed).
   Open the linking QR in a browser:
   ```
   http://localhost:7111/v1/qrcodelink?device_name=event-scraper
   ```
   In Signal on your phone: **Settings → Linked Devices → Link New Device**, scan
   it. `SIGNAL_NUMBER` is your phone's Signal number. (Alternatively register a
   brand-new number — see the signal-cli-rest-api docs for the captcha flow.)

3. **Find your group id.** List the account's groups:
   ```bash
   curl http://localhost:7111/v1/groups/$SIGNAL_NUMBER
   ```
   Copy the `id` field (looks like `group.<base64>`) of the target group — that's
   your `SIGNAL_GROUP_ID`.

4. **Point the app at it** — in the repo-root `.env`:
   ```
   SIGNAL_WEBHOOK_URL=http://localhost:7200
   SIGNAL_WEBHOOK_KEY=<same value as signal/.env>
   SIGNAL_GROUP_ID=group.<base64 from step 3>
   ```
   (Leave `SIGNAL_GROUP_ID` blank to send to yourself while testing.)

5. **Test it:**
   ```bash
   curl -X POST http://localhost:7200/send -H 'Content-Type: application/json' \
     -d '{"message":"hello from event-scraper-app","group_id":"'"$SIGNAL_GROUP_ID"'","api_key":"'"$SIGNAL_WEBHOOK_KEY"'"}'
   ```

## Notes

- `signal-data/` holds the linked-device state — keep it (it's gitignored).
  Losing it means re-linking.
- The shim checks `api_key` against `SIGNAL_WEBHOOK_KEY`; keep it non-empty if the
  webhook is reachable beyond localhost.
- Ports `7111` (signal-cli-rest-api) and `7200` (webhook) match the app's
  defaults — change both sides together if you remap them.
