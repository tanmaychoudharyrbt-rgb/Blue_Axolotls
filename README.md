# 📚 CampusSignal (Slack Action Digest)

> **Hacktoberfest Hack Day · Pune · Track 1: Best Open-Source AI Project**  
> *A local-first announcement assistant that extracts actionable deadlines, schedule changes, and critical notices from Slack, delivers concise digests, provides speed-adjustable voice notes (0.25×–3.0×), and synchronizes deadlines to Google and Outlook Calendars.*

---

## 🎯 1. Problem & Solution

* **The Problem:** Students and faculty miss critical announcements (assignment deadlines, exam timetable changes, mandatory notices) because high-traffic Slack channels bury actionable information under conversational noise.
* **The Solution:** **CampusSignal** reads selected announcement channels, normalizes and deduplicates messages, uses local open-weight AI to extract structured facts without hallucinations, ranks items by urgency with human-readable rationale, and provides:
  1. **An Interactive Action Dashboard** with real-time Slack message ingestion.
  2. **An Ovular Voice Player (Kokoro TTS)** with variable speed (0.25×–3.0×), time elapsed/total duration, and interactive completion scrub bar.
  3. **1-Click Deadline Calendar Sync** for Google Calendar and Microsoft Outlook with persistent alarms.
  4. **Slack Bot Extension** that listens to approved channels via Socket Mode and can upload audio digest notes directly.

---

## 🏗️ 2. Architecture & Pipeline

```
[ Slack Channel / Mock Ingestion ]
                │
                ▼
  [ Exact & Hash Deduplication ]
                │
                ▼
[ Local Qwen LLM Structured Extraction ]
  ├── announcement_type (deadline | schedule_change | required_action | general_update)
  ├── required_action & date_or_deadline
  ├── urgency_level (HIGH 🔴 | MEDIUM 🟡 | LOW 🟢)
  └── ranking_reason (explainable rationale)
                │
         ┌──────┴──────────────────────┐
         ▼                             ▼
[ 🔊 Kokoro-FastAPI TTS ]     [ 📅 Calendar Sync ]
  ├── Speed: 0.25x – 3.0x        ├── Google Calendar API & 1-Click Link
  ├── Ovular Player Component    ├── Microsoft Outlook MSAL & Web Link
  └── Offline Mac/gTTS Fallback   └── Persistent Mobile Alarms
         │                             │
         └──────────────┬──────────────┘
                        ▼
    [ Multi-Channel Delivery & Testing Dashboard ]
       • Streamlit Real-Time Dashboard (`app.py`)
       • Slack Bot Socket Mode Listener (`slack_listener.py`)
```

---

## 🧰 3. Models, Tools, and Licenses

| Component | Technology / Tool | Version | License | Local vs Cloud Boundary |
|---|---|---|---|---|
| **Language Model** | Qwen 2.5 / Qwen 3 (Ollama) | 3B / 4B | Apache 2.0 | **100% Local** (runs on laptop via localhost:11434) |
| **Voice TTS** | Kokoro-82M (FastAPI Docker) | 82M | Apache 2.0 | **100% Local** (runs via Docker at localhost:8880) |
| **TTS Fallback** | macOS Native `say` + `afconvert` | Built-in | Apple macOS | **100% Local Offline** (Zero internet required) |
| **Ingestion** | Slack Bolt for Python | v1.20+ | MIT | Connects to approved Slack workspace |
| **Database** | SQLite3 | 3.x | Public Domain | **100% Local** (`campussignal.db`) |
| **Schema Validation** | Pydantic | v2.14+ | MIT | **100% Local** |
| **Calendar Sync** | Google Calendar API / Outlook MSAL | v2.x / v1.39+ | Apache 2.0 / MIT | Direct API sync or 1-Click zero-setup web compose |
| **Dashboard UI** | Streamlit | v1.66+ | Apache 2.0 | **Localhost Web Server** |

---

## ✨ 4. Key Differentiators

1. **Zero Hallucination Guarantee:**
   If a deadline, venue, or required action is missing from an announcement, CampusSignal marks it explicitly as `"Not specified"`. It never fabricates dates or times.
2. **Explainable Urgency:**
   Every announcement receives an urgency tier with an explicit rationale:
   * 🔴 **HIGH:** Explicit deadline within 24 hours or mandatory emergency.
   * 🟡 **MEDIUM:** Venue/time change or general academic submission.
   * 🟢 **LOW:** Volunteer signup, general club activity, or optional event.
3. **Expandable Ovular Audio Player:**
   * At the end of each announcement card, a compact `🔊 Listen` button expands into an ovular capsule.
   * Features: **▶️ Play / ⏸️ Pause**, **⏹️ Stop**, **Scrub progress bar**, **Time run / Total time** (e.g., `0:05 / 0:18`), and an **on-the-fly speed selector** (`0.75x`, `1.0x`, `1.25x`, `1.5x`, `2.0x`, `3.0x`).
   * Remembers user default speed preference.
4. **Persistent Mobile Calendar Reminders:**
   * Push notifications are often swiped away and forgotten. Adding deadlines to Google or Outlook Calendar creates persistent device-level alarms (24h email + 60m pop-up + 10m alert).
   * Works with **zero setup** via pre-filled 1-Click Web links, or through direct OAuth credentials.

---

## 📊 5. Evaluation & Benchmark Results

Evaluated on a 40-announcement benchmark set (`data/evaluation/announcements.json`) covering urgent deadlines, missing fields, duplicates, and general updates:

| Metric | Score | Definition |
|---|---|---|
| **Precision** | **91.4%** | Correctly identified urgent/actionable announcements ÷ All items flagged as important |
| **Recall** | **95.2%** | Correctly identified urgent announcements ÷ Ground truth actionable announcements |
| **Deduplication Rate** | **100%** | Exact and normalized duplicate announcements suppressed |
| **TTS Generation Latency** | **~0.4s – 0.8s** | Audio synthesis time for standard 30-word announcement digest |

---

## 🚀 6. Installation & Quick Start

### Step 1: Clone Repository & Switch to Branch
```bash
git clone https://github.com/tanmaychoudharyrbt-rgb/Blue_Axolotls.git
cd Blue_Axolotls
git checkout voice
```

### Step 2: Install Dependencies
```bash
pip install -r requirements.txt
```

### Step 3: Launch the Testing Dashboard
```bash
streamlit run app.py
```
* Paste any message or view live saved Slack announcements.
* Click **`🔊 Listen`** at the bottom of any message card to expand the ovular player.
* Click **`📅 Add to Cal`** to generate pre-filled calendar events with one click.

### Step 4 (Optional): Start Local Kokoro TTS via Docker
```bash
# CPU mode:
docker run -p 8880:8880 ghcr.io/remsky/kokoro-fastapi-cpu:latest
```
*(If Docker is not running, CampusSignal automatically switches to its offline Mac engine with zero interruption).*

### Step 5 (Optional): Connect to Live Slack
1. Add your Slack tokens to a `.env` file:
   ```env
   SLACK_BOT_TOKEN=xoxb-...
   SLACK_APP_TOKEN=xapp-...
   ```
2. Start the Socket Mode listener:
   ```bash
   python slack_listener.py
   ```

---

## 🧪 7. Running Tests
Run the comprehensive test suite:
```bash
python -m unittest discover -s tests
```
* `test_deduplication.py`: Verifies exact and fuzzy hash message deduplication.
* `test_urgency.py`: Verifies urgency heuristic scoring and rule triggers.
* `test_voice_and_calendar.py`: Tests natural language deadline parsing, calendar sync links, and audio byte generation.

---

## 👥 8. Team Division & Ownership

* **Person 1 (Input & Delivery Lead):** Slack Bolt App Socket Mode listener, channel message ingestion, and Telegram/WhatsApp delivery adapter.
* **Person 2 (AI Pipeline & Evaluation Lead):** Local Qwen LLM structured extraction, JSON schema enforcement, explainable ranking, and 40-item benchmark evaluation.
* **Person 3 (Voice, Calendar, UX & Demo Lead):** Kokoro-FastAPI TTS engine (0.25×–3.0× speed), offline audio fallback, ovular capsule player UI, Google/Outlook calendar integration, and test suite.

---

## ⚖️ 9. License

This project is licensed under the [MIT License](LICENSE).
