# 🔊 Voice + Calendar Feature — Setup Guide

## What was added (your part of the project)

| File | What it does |
|---|---|
| `tts_kokoro.py` | Kokoro-FastAPI TTS engine (replaces Piper). Speed 0.25×–3.0× |
| `calendar_integration.py` | Auto-creates deadline events in Google Calendar + Outlook |
| `voice_digest.py` | Updated to use Kokoro + optional `--calendar` flag |
| `app.py` | Updated Streamlit UI with TTS playback & Calendar sync buttons |
| `config.yaml` | Updated for Kokoro settings |

---

## Step 1 — Start Kokoro TTS (Docker)

```bash
# CPU only (recommended for hackathon demo):
docker run -p 8880:8880 ghcr.io/remsky/kokoro-fastapi-cpu:latest

# GPU (if you have NVIDIA GPU + CUDA):
docker run --gpus all -p 8880:8880 ghcr.io/remsky/kokoro-fastapi:latest
```

Verify it's running:
```bash
python tts_kokoro.py --check
# ✅ Kokoro server is running!
```

---

## Step 2 — Install Python dependencies

```bash
pip install -r requirements.txt
```

---

## Step 3 — Google Calendar setup (one-time)

1. Go to https://console.cloud.google.com/
2. Create a project → Enable **Google Calendar API**
3. **APIs & Services → Credentials → Create OAuth Client ID** (Desktop App)
4. Download the JSON file → rename it to `credentials_google.json` in this folder
5. First run will open a browser for login → creates `token_google.json` automatically

---

## Step 4 — Microsoft Outlook setup (one-time)

1. Go to https://portal.azure.com/ → **Azure Active Directory → App registrations**
2. **New registration** → Platform: Mobile/Desktop → Redirect: `http://localhost`
3. **API Permissions → Microsoft Graph → Calendars.ReadWrite** → Grant admin consent
4. Copy the **Application (client) ID**
5. Open `calendar_integration.py` and paste your Client ID into `OUTLOOK_CLIENT_ID`
   — or set env var: `export OUTLOOK_CLIENT_ID=your-id-here`
6. First run will show a device code to authenticate in your browser

---

## Running the app

```bash
# Full Streamlit UI (with TTS + Calendar buttons):
streamlit run app.py

# CLI: TTS only
python voice_digest.py --input sample_digest.json --speed 1.5

# CLI: TTS + Calendar sync
python voice_digest.py --input sample_digest.json --speed 1.5 --calendar

# CLI: Calendar only, no audio
python voice_digest.py --input sample_digest.json --mode text_only --calendar

# Direct calendar sync from JSON
python calendar_integration.py --input sample_digest.json --no-outlook  # Google only
```

---

## Speed reference

| Speed | Effect |
|---|---|
| 0.25× | Very slow (accessible) |
| 0.75× | Slightly slower |
| 1.0× | Normal |
| 1.5× | Slightly faster |
| 2.0× | Fast |
| 3.0× | Maximum speed |

---

## Calendar notification behaviour

| Urgency | Google Calendar | Outlook |
|---|---|---|
| 🔴 HIGH | Email 24h before + popup 60min + popup 10min | Reminder 60min before |
| 🟡 MEDIUM | Email 60min before + popup 15min | Reminder 15min before |
| 🟢 LOW | Popup 30min before | Reminder 30min before |

> **Note:** Google Calendar reminders survive even if the user clears all notifications on mobile — they reappear from the calendar event itself.
