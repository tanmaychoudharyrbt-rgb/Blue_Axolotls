"""
calendar_integration.py — Auto-create deadline events in Google Calendar & Microsoft Outlook
from Slack digest items that have a 'deadline' field.

──────────────────────────────────────────────────────────────────
SETUP (one-time)
──────────────────────────────────────────────────────────────────
Google Calendar:
  1. Go to https://console.cloud.google.com/
  2. Create a project → Enable "Google Calendar API"
  3. APIs & Services → Credentials → Create OAuth Client ID (Desktop App)
  4. Download → rename to  credentials_google.json  in this folder
  5. pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib

Microsoft Outlook:
  1. Go to https://portal.azure.com/ → Azure Active Directory → App registrations
  2. New registration → Platform: Mobile/Desktop → Redirect: http://localhost
  3. API Permissions → Microsoft Graph → Calendars.ReadWrite
  4. Copy the Application (client) ID → paste as OUTLOOK_CLIENT_ID below
  5. pip install msal requests

──────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

# ── Google Calendar ───────────────────────────────────────────────
GOOGLE_CREDS_FILE  = "credentials_google.json"   # OAuth client secret JSON
GOOGLE_TOKEN_FILE  = "token_google.json"          # Auto-created on first login
GOOGLE_SCOPES      = ["https://www.googleapis.com/auth/calendar"]

# ── Microsoft Outlook ─────────────────────────────────────────────
OUTLOOK_CLIENT_ID  = os.getenv("OUTLOOK_CLIENT_ID", "YOUR_AZURE_APP_CLIENT_ID")
OUTLOOK_AUTHORITY  = "https://login.microsoftonline.com/consumers"
OUTLOOK_SCOPES_MS  = ["Calendars.ReadWrite", "offline_access"]
OUTLOOK_TOKEN_FILE = "token_outlook.json"

# ── Shared defaults ───────────────────────────────────────────────
DEFAULT_TIMEZONE   = "Asia/Kolkata"   # Change to your local timezone
DEFAULT_EVENT_DURATION_HOURS = 1


# ══════════════════════════════════════════════════════════════════
# Deadline parser — converts natural language → datetime
# ══════════════════════════════════════════════════════════════════

def parse_deadline(deadline_str: str) -> Optional[datetime]:
    """
    Convert strings like  'Today, 11 PM'  /  'Tomorrow 5:00 PM'  /
    '2024-12-31'  into an aware datetime (local naive for simplicity).

    Returns None if it cannot parse.
    """
    if not deadline_str or deadline_str.lower() in ("not specified", "none", ""):
        return None

    s = deadline_str.strip().lower()
    now = datetime.now()

    # ISO date: 2024-12-31
    m = re.match(r"(\d{4}-\d{2}-\d{2})", s)
    if m:
        try:
            return datetime.strptime(m.group(1), "%Y-%m-%d").replace(hour=23, minute=59)
        except ValueError:
            pass

    # "today" or "tonight"
    base = now
    if "tomorrow" in s:
        base = now + timedelta(days=1)
    elif "today" in s or "tonight" in s:
        base = now

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

    # Fallback: end of today
    return base.replace(hour=23, minute=59, second=0, microsecond=0)


# ══════════════════════════════════════════════════════════════════
# Google Calendar
# ══════════════════════════════════════════════════════════════════

def _get_google_service():
    """Authenticate and return a Google Calendar service object."""
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
    except ImportError:
        raise ImportError(
            "Missing Google libs. Run:\n"
            "  pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib"
        )

    creds = None
    if Path(GOOGLE_TOKEN_FILE).exists():
        creds = Credentials.from_authorized_user_file(GOOGLE_TOKEN_FILE, GOOGLE_SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not Path(GOOGLE_CREDS_FILE).exists():
                raise FileNotFoundError(
                    f"Google credentials file not found: {GOOGLE_CREDS_FILE}\n"
                    "Download it from Google Cloud Console → APIs & Services → Credentials."
                )
            flow = InstalledAppFlow.from_client_secrets_file(GOOGLE_CREDS_FILE, GOOGLE_SCOPES)
            creds = flow.run_local_server(port=0)
        Path(GOOGLE_TOKEN_FILE).write_text(creds.to_json(), encoding="utf-8")

    return build("calendar", "v3", credentials=creds)


def create_google_event(
    title: str,
    description: str,
    deadline_dt: datetime,
    urgency: str = "medium",
    source_url: str = "",
) -> dict:
    """
    Create a Google Calendar event with reminders based on urgency level.

    Reminder schedule:
        HIGH   → 24h email + 60min popup + 10min popup
        MEDIUM → 60min email + 15min popup
        LOW    → 30min popup
    """
    service = _get_google_service()

    end_dt = deadline_dt + timedelta(hours=DEFAULT_EVENT_DURATION_HOURS)

    # Urgency-based reminders
    urgency_upper = urgency.upper()
    if urgency_upper == "HIGH":
        overrides = [
            {"method": "email",  "minutes": 24 * 60},
            {"method": "popup",  "minutes": 60},
            {"method": "popup",  "minutes": 10},
        ]
    elif urgency_upper == "MEDIUM":
        overrides = [
            {"method": "email",  "minutes": 60},
            {"method": "popup",  "minutes": 15},
        ]
    else:  # LOW / INFO
        overrides = [
            {"method": "popup",  "minutes": 30},
        ]

    body_text = description
    if source_url:
        body_text += f"\n\nSource: {source_url}"

    event = {
        "summary":     f"{'🔴' if urgency_upper=='HIGH' else '🟡' if urgency_upper=='MEDIUM' else '🟢'} {title}",
        "description": body_text,
        "start": {
            "dateTime": deadline_dt.isoformat(),
            "timeZone": DEFAULT_TIMEZONE,
        },
        "end": {
            "dateTime": end_dt.isoformat(),
            "timeZone": DEFAULT_TIMEZONE,
        },
        "reminders": {
            "useDefault": False,
            "overrides":  overrides,
        },
        # Colorize by urgency (Google Calendar color IDs)
        "colorId": "11" if urgency_upper == "HIGH" else "5" if urgency_upper == "MEDIUM" else "2",
    }

    created = service.events().insert(
        calendarId="primary",
        body=event,
        sendUpdates="none",
    ).execute()

    print(f"  [Google ✅] Created: {created.get('summary')}  → {created.get('htmlLink')}")
    return created


# ══════════════════════════════════════════════════════════════════
# Microsoft Outlook (Graph API)
# ══════════════════════════════════════════════════════════════════

def _get_outlook_token() -> str:
    """Get or refresh an Outlook OAuth token via MSAL device-code flow."""
    try:
        import msal
    except ImportError:
        raise ImportError("Missing msal. Run:  pip install msal")

    import requests as _req

    token_path = Path(OUTLOOK_TOKEN_FILE)
    cache = msal.SerializableTokenCache()

    if token_path.exists():
        cache.deserialize(token_path.read_text(encoding="utf-8"))

    app = msal.PublicClientApplication(
        OUTLOOK_CLIENT_ID,
        authority=OUTLOOK_AUTHORITY,
        token_cache=cache,
    )

    # Try silent first
    accounts = app.get_accounts()
    result = None
    if accounts:
        result = app.acquire_token_silent(OUTLOOK_SCOPES_MS, account=accounts[0])

    if not result:
        # Device-code flow (works in VS Code terminal)
        flow = app.initiate_device_flow(scopes=OUTLOOK_SCOPES_MS)
        if "user_code" not in flow:
            raise RuntimeError(f"Outlook auth failed: {flow}")
        print("\n📱 Outlook login required:")
        print(f"   Open  {flow['verification_uri']}")
        print(f"   Enter code:  {flow['user_code']}\n")
        result = app.acquire_token_by_device_flow(flow)

    if "access_token" not in result:
        raise RuntimeError(f"Could not get Outlook token: {result.get('error_description')}")

    # Save updated cache
    if cache.has_state_changed:
        token_path.write_text(cache.serialize(), encoding="utf-8")

    return result["access_token"]


def create_outlook_event(
    title: str,
    description: str,
    deadline_dt: datetime,
    urgency: str = "medium",
    source_url: str = "",
) -> dict:
    """
    Create a Microsoft Outlook Calendar event via MS Graph API.
    Reminders match the same urgency schedule as Google Calendar.
    """
    import requests as _req

    token = _get_outlook_token()
    end_dt = deadline_dt + timedelta(hours=DEFAULT_EVENT_DURATION_HOURS)

    # MS Graph reminder in minutes before start
    urgency_upper = urgency.upper()
    if urgency_upper == "HIGH":
        reminder_minutes = 60
    elif urgency_upper == "MEDIUM":
        reminder_minutes = 15
    else:
        reminder_minutes = 30

    body_text = description
    if source_url:
        body_text += f"\n\nSource: {source_url}"

    urgency_flag = "high" if urgency_upper == "HIGH" else "normal" if urgency_upper == "MEDIUM" else "low"

    event = {
        "subject": f"{'🔴' if urgency_upper=='HIGH' else '🟡' if urgency_upper=='MEDIUM' else '🟢'} {title}",
        "body": {
            "contentType": "text",
            "content":     body_text,
        },
        "start": {
            "dateTime": deadline_dt.strftime("%Y-%m-%dT%H:%M:%S"),
            "timeZone": DEFAULT_TIMEZONE,
        },
        "end": {
            "dateTime": end_dt.strftime("%Y-%m-%dT%H:%M:%S"),
            "timeZone": DEFAULT_TIMEZONE,
        },
        "isReminderOn":     True,
        "reminderMinutesBeforeStart": reminder_minutes,
        "importance":       urgency_flag,
    }

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type":  "application/json",
    }
    resp = _req.post(
        "https://graph.microsoft.com/v1.0/me/events",
        headers=headers,
        json=event,
        timeout=30,
    )

    if resp.status_code not in (200, 201):
        raise RuntimeError(f"Outlook API error {resp.status_code}: {resp.text[:300]}")

    created = resp.json()
    print(f"  [Outlook ✅] Created: {created.get('subject')}  → {created.get('webLink')}")
    return created


# ══════════════════════════════════════════════════════════════════
# Main entry point — process a full digest payload
# ══════════════════════════════════════════════════════════════════

def sync_digest_to_calendars(
    payload: dict,
    use_google: bool = True,
    use_outlook: bool = True,
) -> list[dict]:
    """
    Iterate over ranked_summary items, find those with a 'deadline' field,
    and create calendar events on Google Calendar and/or Outlook.

    Returns a list of result dicts:
        {"title": ..., "google": ..., "outlook": ...}
    """
    results = []
    items = payload.get("ranked_summary", [])
    if isinstance(items, (str, dict)):
        items = [items]

    for item in items:
        if not isinstance(item, dict):
            continue

        deadline_raw = item.get("deadline") or item.get("date") or ""
        deadline_dt  = parse_deadline(deadline_raw)

        if deadline_dt is None:
            continue  # No parseable deadline → skip

        title       = item.get("title") or item.get("summary", "Slack Digest Event")
        description = item.get("summary", "")
        urgency     = item.get("urgency") or item.get("urgency_level") or "medium"
        source_url  = item.get("source_url") or item.get("source") or ""

        print(f"\n📅 Processing deadline: '{title}' → {deadline_dt.strftime('%Y-%m-%d %H:%M')}")

        result: dict = {"title": title, "google": None, "outlook": None}

        if use_google:
            try:
                result["google"] = create_google_event(
                    title, description, deadline_dt, urgency, source_url
                )
            except Exception as e:
                print(f"  [Google ❌] {e}")

        if use_outlook:
            try:
                result["outlook"] = create_outlook_event(
                    title, description, deadline_dt, urgency, source_url
                )
            except Exception as e:
                print(f"  [Outlook ❌] {e}")

        results.append(result)

    return results


# ══════════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Sync digest deadlines → Google & Outlook Calendar")
    parser.add_argument("--input", default="sample_digest.json", help="JSON digest file")
    parser.add_argument("--no-google",  action="store_true", help="Skip Google Calendar")
    parser.add_argument("--no-outlook", action="store_true", help="Skip Outlook Calendar")
    args = parser.parse_args()

    with open(args.input, encoding="utf-8") as f:
        payload = json.load(f)

    results = sync_digest_to_calendars(
        payload,
        use_google  = not args.no_google,
        use_outlook = not args.no_outlook,
    )

    print(f"\n✅ Done — {len(results)} deadline(s) synced to calendar(s).")
