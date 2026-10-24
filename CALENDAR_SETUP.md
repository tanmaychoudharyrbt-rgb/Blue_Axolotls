# 📅 Calendar Branch — Setup Guide

## What this branch adds
- `calendar_integration.py` — auto-creates Google + Outlook Calendar events from Slack digest deadlines
- `app.py` — adds "📅 Add to Calendar" button to the UI
- `requirements.txt` — adds `google-api-python-client`, `google-auth-oauthlib`, `msal`

---

## Google Calendar setup (one-time)

1. Go to https://console.cloud.google.com/
2. Create a project → Enable **Google Calendar API**
3. **APIs & Services → Credentials → OAuth Client ID** (Desktop App)
4. Download the JSON → rename to **`credentials_google.json`** in project root
5. Run once — browser opens for login, creates `token_google.json` automatically

---

## Microsoft Outlook setup (one-time)

1. https://portal.azure.com/ → **Azure AD → App registrations → New registration**
2. Platform: Mobile/Desktop → Redirect URI: `http://localhost`
3. **API Permissions → Microsoft Graph → Calendars.ReadWrite** → Grant consent
4. Copy **Application (client) ID** → paste into `OUTLOOK_CLIENT_ID` in `calendar_integration.py`
   or set env var: `export OUTLOOK_CLIENT_ID=your-id-here`
5. First run shows a device code — open the URL and enter the code in browser

---

## Install dependencies

```bash
pip install -r requirements.txt
```

---

## Usage

```bash
# CLI — sync deadlines from a digest JSON
python calendar_integration.py --input data/evaluation/announcements.json

# Google only
python calendar_integration.py --no-outlook

# Outlook only
python calendar_integration.py --no-google

# UI — launch Streamlit
streamlit run app.py
# → Click "📅 Add to Calendar" on any message
```

---

## Notification schedule

| Urgency | Google Calendar | Outlook |
|---|---|---|
| 🔴 HIGH | email 24h + popup 60min + popup 10min | reminder 60min before |
| 🟡 MEDIUM | email 60min + popup 15min | reminder 15min before |
| 🟢 LOW / INFO | popup 30min | reminder 30min before |

> Google Calendar reminders **persist on mobile** even if the user dismisses all notifications — they fire from the calendar event itself, which is exactly what we need.
