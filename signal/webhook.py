"""Minimal Signal-sending webhook for event-scraper-app.

The bot and scraper post their digest / alerts to a webhook with the contract
``POST /send {message, group_id, api_key}``. This shim implements that on top
of signal-cli-rest-api (https://github.com/bbernhard/signal-cli-rest-api),
forwarding to its ``/v2/send`` endpoint.

Env:
  SIGNAL_API_URL      base URL of signal-cli-rest-api (default the compose service)
  SIGNAL_NUMBER       the linked Signal account number, e.g. +15551234567 (required)
  SIGNAL_WEBHOOK_KEY  shared secret callers must send as api_key (optional)
"""
import os

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

SIGNAL_API_URL = os.environ.get("SIGNAL_API_URL", "http://signal-cli-rest-api:8080")
SIGNAL_NUMBER = os.environ["SIGNAL_NUMBER"]
WEBHOOK_KEY = os.environ.get("SIGNAL_WEBHOOK_KEY", "")

app = FastAPI(title="signal-webhook")


class SendRequest(BaseModel):
    message: str
    group_id: str = ""      # signal-cli group id ("group.<base64>") or a phone number
    api_key: str = ""
    platform: str = "signal"
    priority: int = 3


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/send")
def send(req: SendRequest):
    if WEBHOOK_KEY and req.api_key != WEBHOOK_KEY:
        raise HTTPException(status_code=401, detail="bad api_key")
    # No group_id -> send to the account's own number (a note-to-self).
    recipient = req.group_id or SIGNAL_NUMBER
    try:
        resp = httpx.post(
            f"{SIGNAL_API_URL}/v2/send",
            json={"message": req.message, "number": SIGNAL_NUMBER, "recipients": [recipient]},
            timeout=30,
        )
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"signal-cli-rest-api unreachable: {e}")
    if resp.status_code >= 300:
        raise HTTPException(status_code=502, detail=f"signal-cli-rest-api {resp.status_code}: {resp.text[:200]}")
    return {"sent": True}
