"""Zoho Meeting API - same calls as the tested script in 'zoho testing/create_meeting.py'.

Settings come from environment variables (.env next to manage.py locally,
PythonAnywhere environment / .env on the server):
    ZOHO_CLIENT_ID, ZOHO_CLIENT_SECRET, ZOHO_REFRESH_TOKEN,
    ZOHO_ZSOID, ZOHO_PRESENTER_ID, ZOHO_ZSOURCE
"""

import os
import threading
import time

import requests

ACCOUNTS_URL = "https://accounts.zoho.in"
MEETING_API_URL = "https://meeting.zoho.in/api/v2"
MEETING_TIMEZONE = "Asia/Calcutta"
TIMEOUT = 30

REQUIRED = (
    "ZOHO_CLIENT_ID",
    "ZOHO_CLIENT_SECRET",
    "ZOHO_REFRESH_TOKEN",
    "ZOHO_ZSOID",
    "ZOHO_PRESENTER_ID",
    "ZOHO_ZSOURCE",
)


class ZohoError(Exception):
    """Message is safe to show to the admin."""


_token_lock = threading.Lock()
_token = {"value": None, "expires": 0.0}


def _config():
    missing = [key for key in REQUIRED if not os.environ.get(key)]
    if missing:
        raise ZohoError(
            "Zoho settings are missing on the server: " + ", ".join(missing)
            + ". Add them to the .env file and restart/reload the backend."
        )
    return {key: os.environ[key] for key in REQUIRED}


def _post_token(cfg):
    try:
        response = requests.post(
            f"{ACCOUNTS_URL}/oauth/v2/token",
            params={
                "refresh_token": cfg["ZOHO_REFRESH_TOKEN"],
                "client_id": cfg["ZOHO_CLIENT_ID"],
                "client_secret": cfg["ZOHO_CLIENT_SECRET"],
                "grant_type": "refresh_token",
            },
            timeout=TIMEOUT,
        )
    except requests.RequestException as exc:
        raise ZohoError(f"Could not connect to Zoho login server ({exc.__class__.__name__}).") from exc

    try:
        data = response.json()
    except ValueError:
        data = {}
    if response.status_code != 200 or "error" in data or not data.get("access_token"):
        reason = data.get("error") or f"HTTP {response.status_code}"
        raise ZohoError(f"Zoho login failed ({reason}). Check the client ID, secret and refresh token.")
    return data


def get_access_token():
    """Access tokens last 1 hour; reuse one until shortly before it expires."""
    cfg = _config()
    with _token_lock:
        if _token["value"] and time.time() < _token["expires"]:
            return _token["value"]
        data = _post_token(cfg)
        _token["value"] = data["access_token"]
        _token["expires"] = time.time() + int(data.get("expires_in", 3600)) - 300
        return _token["value"]


def _payload(topic, agenda, start_dt, duration_ms, participants=None):
    cfg = _config()
    payload = {
        "session": {
            "topic": topic,
            "agenda": agenda,
            "presenter": int(cfg["ZOHO_PRESENTER_ID"]),
            # Format Zoho expects: "Nov 14, 2026 03:00 PM" (in MEETING_TIMEZONE)
            "startTime": start_dt.strftime("%b %d, %Y %I:%M %p"),
            "duration": duration_ms,
            "timezone": MEETING_TIMEZONE,
        }
    }
    if participants:
        # Zoho REPLACES the participant list with this one (people left out are
        # removed), so always pass every registrant. People already on the list
        # are not invited again; newcomers get Zoho's invitation + calendar entry.
        payload["session"]["participants"] = [{"email": email} for email in participants]
    return payload


def _error_text(data, status_code):
    if isinstance(data, dict):
        err = data.get("error")
        if isinstance(err, dict) and err.get("message"):
            return err["message"]
        if isinstance(err, str):
            return err
        if data.get("message"):
            return str(data["message"])
    return f"HTTP {status_code}"


def _send(method, url, payload):
    cfg = _config()
    headers = {
        "Authorization": f"Zoho-oauthtoken {get_access_token()}",
        "X-ZSOURCE": cfg["ZOHO_ZSOURCE"],
        "Content-Type": "application/json;charset=UTF-8",
    }
    try:
        response = requests.request(method, url, headers=headers, json=payload, timeout=TIMEOUT)
    except requests.RequestException as exc:
        raise ZohoError(f"Could not connect to Zoho Meeting ({exc.__class__.__name__}).") from exc

    try:
        data = response.json()
    except ValueError:
        data = None

    if response.status_code in (200, 201) and isinstance(data, dict) and "session" in data:
        return data["session"]
    raise ZohoError(f"Zoho Meeting returned an error: {_error_text(data, response.status_code)}")


def create_meeting(topic, agenda, start_dt, duration_ms):
    """Returns the Zoho session dict (meetingKey, joinLink, startLink, ...)."""
    cfg = _config()
    session = _send(
        "POST",
        f"{MEETING_API_URL}/{cfg['ZOHO_ZSOID']}/sessions.json",
        _payload(topic, agenda, start_dt, duration_ms),
    )
    if not session.get("meetingKey") or not session.get("joinLink"):
        raise ZohoError("Zoho created the meeting but did not return the meeting key or join link.")
    return session


def update_meeting(meeting_key, topic, agenda, start_dt, duration_ms, participants=None):
    """Changes the existing meeting; the join link normally stays the same.
    participants: the full list of participant emails (None = leave them as they are)."""
    cfg = _config()
    return _send(
        "PUT",
        f"{MEETING_API_URL}/{cfg['ZOHO_ZSOID']}/sessions/{meeting_key}.json",
        _payload(topic, agenda, start_dt, duration_ms, participants),
    )
