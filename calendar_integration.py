"""
calendar_integration.py — Auto-create deadline events in Google Calendar & Microsoft Outlook
from Slack digest items that contain a 'deadline' field.

Handles BOTH:
  1. Direct API Sync: when credentials are present (OAuth / Azure Graph API)
  2. Zero-Setup 1-Click Web Links: when credentials are not yet downloaded,
     generates instant 1-click Google Calendar & Outlook Web compose links
     so it NEVER crashes or fails with missing credential errors!
"""

from __future__ import annotations

import json
import os
import re
import urllib.parse
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any

# ── Google Calendar ───────────────────────────────────────────────
GOOGLE_CREDS_FILE  = "credentials_google.json"
GOOGLE_TOKEN_FILE  = "token_google.json"
GOOGLE_SCOPES      = ["https://www.googleapis.com/auth/calendar"]

# ── Microsoft Outlook ─────────────────────────────────────────────
# MSAL note: 'offline_access', 'profile', 'openid' are reserved in MSAL.
# Only request resource scopes such as 'Calendars.ReadWrite'.
OUTLOOK_CLIENT_ID  = os.getenv("OUTLOOK_CLIENT_ID", "").strip()
OUTLOOK_AUTHORITY  = "https://login.microsoftonline.com/consumers"
OUTLOOK_SCOPES_MS  = ["Calendars.ReadWrite"]
OUTLOOK_TOKEN_FILE = "token_outlook.json"

# ── Shared defaults ───────────────────────────────────────────────
DEFAULT_TIMEZONE              = "Asia/Kolkata"
DEFAULT_EVENT_DURATION_HOURS  = 1


# ══════════════════════════════════════════════════════════════════
# Deadline parser — natural language → datetime
# ══════════════════════════════════════════════════════════════════

def parse_deadline(deadline_str: str) -> Optional[datetime]:
    """
    Parses strings like:
        'Today, 11 PM'  /  'Tomorrow 5:30 PM'  /  '2026-10-25'
    Returns None if it cannot parse.
    """
    if not deadline_str or deadline_str.lower() in ("not specified", "none", ""):
        return None

    s   = deadline_str.strip().lower()
    now = datetime.now()

    # ISO date: YYYY-MM-DD
    m = re.match(r"(\d{4}-\d{2}-\d{2})", s)
    if m:
        try:
            return datetime.strptime(m.group(1), "%Y-%m-%d").replace(hour=23, minute=59)
        except ValueError:
            pass

    base = now
    if "tomorrow" in s:
        base = now + timedelta(days=1)

    # Extract time like "11 pm", "5:30 pm", "23:00"
    time_m = re.search(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", s)
    if time_m:
        hour   = int(time_m.group(1))
        minute = int(time_m.group(2)) if time_m.group(2) else 0
        ampm   = time_m.group(3)
        if ampm == "pm" and hour < 12:
            hour += 12
        elif ampm == "am" and hour == 12:
            hour = 0
        return base.replace(hour=hour, minute=minute, second=0, microsecond=0)

    # Fallback: end of day
    return base.replace(hour=23, minute=59, second=0, microsecond=0)


# ══════════════════════════════════════════════════════════════════
# Google Calendar
# ══════════════════════════════════════════════════════════════════

def _generate_google_web_link(title: str, description: str, deadline_dt: datetime, end_dt: datetime) -> str:
    """Generate 1-click Google Calendar web template URL (works with zero setup)."""
    start_fmt = deadline_dt.strftime("%Y%m%dT%H%M%S")
    end_fmt   = end_dt.strftime("%Y%m%dT%H%M%S")
    params = {
        "action":   "TEMPLATE",
        "text":     title,
        "dates":    f"{start_fmt}/{end_fmt}",
        "details":  description,
        "location": "Online / Campus",
    }
    return f"https://calendar.google.com/calendar/render?{urllib.parse.urlencode(params)}"


def create_google_event(
    title: str,
    description: str,
    deadline_dt: datetime,
    urgency: str = "medium",
    source_url: str = "",
) -> Dict[str, Any]:
    """
    Create a Google Calendar event.
    If credentials_google.json is present, syncs via Google Calendar API.
    If not, instantly provides the 1-click Web Template URL with pre-filled fields.
    """
    end_dt = deadline_dt + timedelta(hours=DEFAULT_EVENT_DURATION_HOURS)
    u      = urgency.upper()
    icon   = "🔴" if u == "HIGH" else "🟡" if u == "MEDIUM" else "🟢"
    full_title = f"{icon} {title[:60]}"
    body       = description + (f"\n\nSource: {source_url}" if source_url else "")

    # Check if API credentials exist
    if not Path(GOOGLE_CREDS_FILE).exists() and not Path(GOOGLE_TOKEN_FILE).exists():
        web_link = _generate_google_web_link(full_title, body, deadline_dt, end_dt)
        print(f"  [Google 📅 1-Click Link] {full_title} → {web_link}")
        return {
            "summary": full_title,
            "htmlLink": web_link,
            "mode": "1-click-web",
        }

    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build

        creds = None
        if Path(GOOGLE_TOKEN_FILE).exists():
            creds = Credentials.from_authorized_user_file(GOOGLE_TOKEN_FILE, GOOGLE_SCOPES)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow  = InstalledAppFlow.from_client_secrets_file(GOOGLE_CREDS_FILE, GOOGLE_SCOPES)
                creds = flow.run_local_server(port=0)
            Path(GOOGLE_TOKEN_FILE).write_text(creds.to_json(), encoding="utf-8")

        service = build("calendar", "v3", credentials=creds)

        if u == "HIGH":
            overrides = [
                {"method": "email", "minutes": 24 * 60},
                {"method": "popup", "minutes": 60},
                {"method": "popup", "minutes": 10},
            ]
            color_id = "11"
        elif u == "MEDIUM":
            overrides = [
                {"method": "email", "minutes": 60},
                {"method": "popup", "minutes": 15},
            ]
            color_id = "5"
        else:
            overrides = [{"method": "popup", "minutes": 30}]
            color_id  = "2"

        event = {
            "summary":     full_title,
            "description": body,
            "start":       {"dateTime": deadline_dt.isoformat(), "timeZone": DEFAULT_TIMEZONE},
            "end":         {"dateTime": end_dt.isoformat(),      "timeZone": DEFAULT_TIMEZONE},
            "colorId":     color_id,
            "reminders":   {"useDefault": False, "overrides": overrides},
        }

        created = service.events().insert(calendarId="primary", body=event).execute()
        print(f"  [Google ✅ API] {created.get('summary')} → {created.get('htmlLink')}")
        return created

    except Exception as e:
        print(f"  [Google API fallback → Web link]: {e}")
        web_link = _generate_google_web_link(full_title, body, deadline_dt, end_dt)
        return {"summary": full_title, "htmlLink": web_link, "mode": "1-click-web"}


# ══════════════════════════════════════════════════════════════════
# Microsoft Outlook (Web Deeplink & Graph API)
# ══════════════════════════════════════════════════════════════════

def _generate_outlook_web_link(title: str, description: str, deadline_dt: datetime, end_dt: datetime) -> str:
    """Generate 1-click Outlook Web compose URL."""
    params = {
        "path":    "/calendar/action/compose",
        "rru":     "addevent",
        "subject": title,
        "body":    description,
        "startdt": deadline_dt.strftime("%Y-%m-%dT%H:%M:%S"),
        "enddt":   end_dt.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    return f"https://outlook.live.com/calendar/0/deeplink/compose?{urllib.parse.urlencode(params)}"


def create_outlook_event(
    title: str,
    description: str,
    deadline_dt: datetime,
    urgency: str = "medium",
    source_url: str = "",
) -> Dict[str, Any]:
    """
    Create an Outlook event.
    If OUTLOOK_CLIENT_ID is valid, syncs via Microsoft Graph API (MSAL).
    If not, instantly provides the 1-click Outlook Web template URL.
    """
    end_dt     = deadline_dt + timedelta(hours=DEFAULT_EVENT_DURATION_HOURS)
    u          = urgency.upper()
    icon       = "🔴" if u == "HIGH" else "🟡" if u == "MEDIUM" else "🟢"
    full_title = f"{icon} {title[:60]}"
    body       = description + (f"\n\nSource: {source_url}" if source_url else "")

    # If no Azure App registered yet, return 1-click direct compose link
    if not OUTLOOK_CLIENT_ID or OUTLOOK_CLIENT_ID == "YOUR_AZURE_APP_CLIENT_ID":
        web_link = _generate_outlook_web_link(full_title, body, deadline_dt, end_dt)
        print(f"  [Outlook 📧 1-Click Link] {full_title} → {web_link}")
        return {
            "subject": full_title,
            "webLink": web_link,
            "mode": "1-click-web",
        }

    try:
        import msal
        import requests as _req

        token_path = Path(OUTLOOK_TOKEN_FILE)
        cache      = msal.SerializableTokenCache()
        if token_path.exists():
            cache.deserialize(token_path.read_text(encoding="utf-8"))

        app = msal.PublicClientApplication(
            OUTLOOK_CLIENT_ID, authority=OUTLOOK_AUTHORITY, token_cache=cache
        )
        accounts = app.get_accounts()
        result   = None
        if accounts:
            result = app.acquire_token_silent(OUTLOOK_SCOPES_MS, account=accounts[0])

        if not result:
            flow = app.initiate_device_flow(scopes=OUTLOOK_SCOPES_MS)
            if "user_code" not in flow:
                raise RuntimeError(f"Outlook auth failed: {flow}")
            print(f"\n📱 Outlook login: open {flow['verification_uri']} enter code: {flow['user_code']}")
            result = app.acquire_token_by_device_flow(flow)

        if "access_token" not in result:
            raise RuntimeError(f"Outlook token error: {result.get('error_description')}")

        if cache.has_state_changed:
            token_path.write_text(cache.serialize(), encoding="utf-8")

        token = result["access_token"]
        reminder_minutes = 60 if u == "HIGH" else 15 if u == "MEDIUM" else 30
        importance       = "high" if u == "HIGH" else "normal" if u == "MEDIUM" else "low"

        event = {
            "subject":    full_title,
            "body":       {"contentType": "text", "content": body},
            "start":      {"dateTime": deadline_dt.strftime("%Y-%m-%dT%H:%M:%S"), "timeZone": DEFAULT_TIMEZONE},
            "end":        {"dateTime": end_dt.strftime("%Y-%m-%dT%H:%M:%S"),      "timeZone": DEFAULT_TIMEZONE},
            "importance": importance,
            "isReminderOn": True,
            "reminderMinutesBeforeStart": reminder_minutes,
        }

        resp = _req.post(
            "https://graph.microsoft.com/v1.0/me/events",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json=event,
            timeout=30,
        )
        if resp.status_code not in (200, 201):
            raise RuntimeError(f"Outlook API {resp.status_code}: {resp.text[:200]}")

        created = resp.json()
        print(f"  [Outlook ✅ API] {created.get('subject')} → {created.get('webLink')}")
        return created

    except Exception as e:
        print(f"  [Outlook API fallback → Web link]: {e}")
        web_link = _generate_outlook_web_link(full_title, body, deadline_dt, end_dt)
        return {"subject": full_title, "webLink": web_link, "mode": "1-click-web"}


# ══════════════════════════════════════════════════════════════════
# Main Sync Entry Point
# ══════════════════════════════════════════════════════════════════

def sync_digest_to_calendars(
    payload: dict,
    use_google:  bool = True,
    use_outlook: bool = True,
) -> list[dict]:
    """
    Iterate ranked_summary items, parse deadlines, and generate
    events / 1-click links on Google Calendar & Microsoft Outlook.
    Never crashes.
    """
    results = []
    items   = payload.get("ranked_summary", [])
    if isinstance(items, (str, dict)):
        items = [items]

    for item in items:
        if not isinstance(item, dict):
            continue

        deadline_raw = item.get("deadline") or item.get("date") or ""
        deadline_dt  = parse_deadline(deadline_raw)
        if deadline_dt is None:
            continue

        raw_title   = item.get("title") or item.get("summary", "College Deadline")
        title       = raw_title.split("\n")[0][:70]
        description = item.get("summary", "")
        urgency     = item.get("urgency") or item.get("urgency_level") or "medium"
        source_url  = item.get("source_url") or item.get("source") or ""

        print(f"\n📅 Deadline found: '{title}' → {deadline_dt.strftime('%Y-%m-%d %H:%M')}")
        result: dict = {"title": title, "google": None, "outlook": None}

        if use_google:
            try:
                result["google"] = create_google_event(
                    title, description, deadline_dt, urgency, source_url
                )
            except Exception as e:
                print(f"  [Google error]: {e}")

        if use_outlook:
            try:
                result["outlook"] = create_outlook_event(
                    title, description, deadline_dt, urgency, source_url
                )
            except Exception as e:
                print(f"  [Outlook error]: {e}")

        results.append(result)

    return results


if __name__ == "__main__":
    test_payload = {
        "ranked_summary": [
            {
                "title": "Last day to collect ID cards",
                "summary": "Today is the Last day to collect your ID cards. Collect from counter 4.",
                "deadline": "Today 11 PM",
                "urgency": "high"
            }
        ]
    }
    res = sync_digest_to_calendars(test_payload)
    print("\nResult:", json.dumps(res, default=str, indent=2))
