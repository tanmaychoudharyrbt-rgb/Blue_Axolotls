"""
app.py — CampusSignal Dashboard (Voice Extension with Ovular Player + Calendar Sync)

Features:
  • Preserves 100% of campussignal_core: Qwen/rules classification, shared SQLite DB, Slack ingestion
  • Compact 🔊 icon at the end of each message that expands into an Ovular Player
  • Ovular Player has:
      - ▶️ Play / ⏸️ Pause / ⏹️ Stop
      - Real-time completion progress bar
      - Time run and total duration (e.g. 0:04 / 0:18)
      - Interactive speed switcher (0.75x, 1.0x, 1.25x, 1.5x, 2.0x, 3.0x)
      - Option to set chosen speed as general default for all messages
  • 📅 Add to Calendar: 1-click Google & Outlook calendar deadline creation (zero setup required)
"""

import base64
import re
import sqlite3
import streamlit as st
import streamlit.components.v1 as components

from campussignal_core import (
    DB_NAME,
    init_db,
    classify_message,
    message_exists,
    save_message,
)
from tts_kokoro import synthesize_bytes, check_kokoro_health
from calendar_integration import sync_digest_to_calendars

st.set_page_config(
    page_title="CampusSignal | Voice & Calendar Extension",
    page_icon="🔊",
    layout="wide",
)

# ── Session State ──────────────────────────────────────────────────
if "general_speed" not in st.session_state:
    st.session_state.general_speed = 1.25
if "active_player_id" not in st.session_state:
    st.session_state.active_player_id = None
if "cached_audio" not in st.session_state:
    st.session_state.cached_audio = {}  # {msg_id_or_hash: (b64, engine, speed)}

init_db()


def render_ovular_audio_player(audio_b64: str, player_key: str, initial_speed: float = 1.25):
    """
    Renders a sleek ovular pill-shaped audio player with:
      • ▶️ / ⏸️ Play/Pause toggle
      • ⏹️ Stop
      • Time run / Total duration
      • Interactive completion scrub bar
      • Instant speed selector (0.75x to 3.0x)
    """
    html_code = f"""
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="utf-8">
      <style>
        body {{
          margin: 0;
          padding: 4px 0;
          font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
          background: transparent;
        }}
        .ovular-pill {{
          display: inline-flex;
          align-items: center;
          background: linear-gradient(135deg, #0f172a, #1e293b);
          border: 1px solid #334155;
          border-radius: 9999px;
          padding: 6px 16px;
          box-shadow: 0 4px 14px rgba(0, 0, 0, 0.25);
          color: #f8fafc;
          gap: 12px;
          max-width: 100%;
          box-sizing: border-box;
          animation: expandPill 0.25s ease-out;
        }}
        @keyframes expandPill {{
          from {{ opacity: 0; transform: scale(0.95); }}
          to {{ opacity: 1; transform: scale(1); }}
        }}
        .btn-ctrl {{
          background: #3b82f6;
          border: none;
          color: white;
          width: 32px;
          height: 32px;
          border-radius: 50%;
          cursor: pointer;
          display: flex;
          align-items: center;
          justify-content: center;
          font-size: 13px;
          transition: transform 0.1s, background 0.2s;
        }}
        .btn-ctrl:hover {{
          background: #2563eb;
          transform: scale(1.06);
        }}
        .btn-stop {{
          background: #ef4444;
          border: none;
          color: white;
          width: 28px;
          height: 28px;
          border-radius: 50%;
          cursor: pointer;
          font-size: 11px;
          display: flex;
          align-items: center;
          justify-content: center;
          transition: background 0.2s;
        }}
        .btn-stop:hover {{
          background: #dc2626;
        }}
        .time-box {{
          font-size: 12px;
          font-variant-numeric: tabular-nums;
          color: #94a3b8;
          white-space: nowrap;
          min-width: 78px;
        }}
        .progress-bar-container {{
          flex-grow: 1;
          display: flex;
          align-items: center;
          min-width: 120px;
          max-width: 220px;
        }}
        .progress-bar {{
          width: 100%;
          -webkit-appearance: none;
          height: 5px;
          border-radius: 3px;
          background: #475569;
          outline: none;
          cursor: pointer;
        }}
        .progress-bar::-webkit-slider-thumb {{
          -webkit-appearance: none;
          width: 13px;
          height: 13px;
          border-radius: 50%;
          background: #38bdf8;
          cursor: pointer;
          box-shadow: 0 0 6px rgba(56, 189, 248, 0.6);
        }}
        .speed-pill-select {{
          background: #334155;
          color: #38bdf8;
          font-size: 12px;
          font-weight: bold;
          border: 1px solid #475569;
          border-radius: 12px;
          padding: 3px 8px;
          cursor: pointer;
          outline: none;
        }}
        .speed-pill-select:hover {{
          background: #1e293b;
        }}
      </style>
    </head>
    <body>
      <div class="ovular-pill" id="pill_{player_key}">
        <button class="btn-ctrl" id="playBtn" onclick="togglePlay()">▶</button>
        <button class="btn-stop" id="stopBtn" onclick="stopAudio()" title="Stop">⏹</button>
        
        <div class="time-box" id="timeBox">0:00 / 0:00</div>
        
        <div class="progress-bar-container">
          <input type="range" class="progress-bar" id="seekBar" min="0" max="100" value="0" oninput="seekAudio(this.value)">
        </div>

        <select class="speed-pill-select" id="speedSelect" onchange="changeSpeed(this.value)" title="Change Voice Speed">
          <option value="0.75" {"selected" if initial_speed==0.75 else ""}>0.75x</option>
          <option value="1.0"  {"selected" if initial_speed==1.0 else ""}>1.0x</option>
          <option value="1.25" {"selected" if initial_speed==1.25 else ""}>1.25x</option>
          <option value="1.5"  {"selected" if initial_speed==1.5 else ""}>1.5x</option>
          <option value="2.0"  {"selected" if initial_speed==2.0 else ""}>2.0x</option>
          <option value="3.0"  {"selected" if initial_speed==3.0 else ""}>3.0x</option>
        </select>
      </div>

      <audio id="audioElement" src="data:audio/mp3;base64,{audio_b64}"></audio>

      <script>
        const audio = document.getElementById("audioElement");
        const playBtn = document.getElementById("playBtn");
        const timeBox = document.getElementById("timeBox");
        const seekBar = document.getElementById("seekBar");
        const speedSelect = document.getElementById("speedSelect");

        audio.playbackRate = parseFloat(speedSelect.value);

        function formatTime(secs) {{
          if (isNaN(secs)) return "0:00";
          const m = Math.floor(secs / 60);
          const s = Math.floor(secs % 60);
          return m + ":" + (s < 10 ? "0" : "") + s;
        }}

        function togglePlay() {{
          if (audio.paused) {{
            audio.play();
            playBtn.innerText = "⏸";
          }} else {{
            audio.pause();
            playBtn.innerText = "▶";
          }}
        }}

        function stopAudio() {{
          audio.pause();
          audio.currentTime = 0;
          playBtn.innerText = "▶";
          seekBar.value = 0;
          updateTime();
        }}

        function seekAudio(percent) {{
          if (audio.duration) {{
            audio.currentTime = (percent / 100) * audio.duration;
          }}
        }}

        function changeSpeed(val) {{
          audio.playbackRate = parseFloat(val);
        }}

        function updateTime() {{
          const cur = audio.currentTime;
          const dur = audio.duration || 0;
          timeBox.innerText = formatTime(cur) + " / " + formatTime(dur);
          if (dur > 0) {{
            seekBar.value = (cur / dur) * 100;
          }}
        }}

        audio.addEventListener("timeupdate", updateTime);
        audio.addEventListener("loadedmetadata", updateTime);
        audio.addEventListener("ended", () => {{
          playBtn.innerText = "▶";
          seekBar.value = 0;
        }});

        // Auto-start on render
        window.addEventListener("DOMContentLoaded", () => {{
          audio.play().then(() => {{
            playBtn.innerText = "⏸";
          }}).catch(() => {{}});
        }});
      </script>
    </body>
    </html>
    """
    components.html(html_code, height=52)


# ── Title & Global Preferences ─────────────────────────────────────
st.title("📚 CampusSignal")
st.write("Your college communication, organized, spoken aloud, and synced to calendar.")

with st.expander("⚙️ Voice & Calendar General Settings", expanded=False):
    pref_col1, pref_col2 = st.columns(2)
    with pref_col1:
        st.session_state.general_speed = st.select_slider(
            "⚡ General Default Voice Speed (applies to all messages):",
            options=[0.75, 1.0, 1.25, 1.5, 2.0, 3.0],
            value=st.session_state.general_speed,
            format_func=lambda x: f"{x}x speed",
        )
    with pref_col2:
        if check_kokoro_health():
            st.success("🟢 **Kokoro-FastAPI Online** (Port :8880)")
        else:
            st.info("⚡ **Offline Voice Ready** (Instant Mac/Local Engine)")

col_main, col_side = st.columns([1.8, 1.2])

# ── Main Panel: Message Input ──────────────────────────────────────
with col_main:
    st.subheader("📥 Paste a college message")
    message = st.text_area(
        "Announcement text:",
        placeholder="Example: The endsem timetable is available on Moodle. Submit lab reports by 11 PM tonight.",
        height=110,
    )

    btn_row1, btn_row2 = st.columns([1, 1])
    analyze_btn = btn_row1.button("🔍 Analyze message", use_container_width=True)
    cal_main_btn = btn_row2.button("📅 Add to Calendar", use_container_width=True)

    if analyze_btn:
        if not message.strip():
            st.warning("Please enter a message.")
        else:
            clean_message = message.strip()
            if message_exists(clean_message):
                st.warning("🔁 This exact message is already saved.")
            else:
                with st.spinner("Classifying message..."):
                    category, used_ai = classify_message(clean_message)

                saved, message_id = save_message(
                    message=clean_message,
                    category=category,
                    source="dashboard",
                )

                if saved:
                    st.success("Message saved!")
                    st.write("**Category:**", category)
                    if used_ai:
                        st.caption("Classified using Qwen.")
                    else:
                        st.warning("Qwen was unavailable. Used the keyword classifier instead.")
                else:
                    st.warning("🔁 This message was saved by another process.")

    if cal_main_btn:
        if not message.strip():
            st.warning("Please enter a message first.")
        else:
            category, _ = classify_message(message.strip())
            urgency = "high" if "Urgent" in category else "medium" if "Academic" in category else "low"
            m = re.search(r"(today|tonight|tomorrow|\d{1,2}[:/]\d{2}\s*(?:am|pm)?|\d{4}-\d{2}-\d{2})", message.lower())
            deadline_hint = m.group(0) if m else "Today, 11 PM"
            payload = {
                "ranked_summary": [
                    {"title": message.strip()[:65], "summary": message.strip(), "urgency": urgency, "deadline": deadline_hint, "type": category}
                ]
            }
            results = sync_digest_to_calendars(payload, use_google=True, use_outlook=True)
            if results:
                r = results[0]
                gcal = r.get("google")
                ocal = r.get("outlook")
                st.success(f"📅 Deadline found: **{r['title']}**")
                col_g, col_o = st.columns(2)
                if gcal and gcal.get("htmlLink"):
                    col_g.markdown(f"[📅 **Open in Google Calendar**]({gcal['htmlLink']})")
                if ocal and ocal.get("webLink"):
                    col_o.markdown(f"[📧 **Open in Outlook Calendar**]({ocal['webLink']})")


# ── Side Panel: Saved Messages with Ovular TTS Icon ────────────────
with col_side:
    st.subheader("📨 Saved messages")

    with sqlite3.connect(DB_NAME) as conn:
        rows = conn.execute(
            """
            SELECT id, message, category, source, channel_id
            FROM messages
            ORDER BY id DESC
            """
        ).fetchall()

    st.write(f"Total unique messages: {len(rows)}")

    if not rows:
        st.info("No messages have been saved yet.")

    for message_id, saved_message, category, source, channel_id in rows:
        with st.container(border=True):
            # Message metadata header
            if source == "slack":
                header_text = f"#{message_id} · {category} · Slack"
                if channel_id:
                    header_text += f" ({channel_id})"
            else:
                header_text = f"#{message_id} · {category} · Dashboard"
            st.caption(header_text)

            # Message content
            st.write(saved_message)

            # ── Footer: Compact Icon expanding into Ovular Player ──
            card_footer_col1, card_footer_col2 = st.columns([1.6, 1])

            is_active = (st.session_state.active_player_id == message_id)

            with card_footer_col1:
                if not is_active:
                    # Small compact icon at the end of the message
                    if st.button(f"🔊 Listen", key=f"btn_listen_{message_id}", help="Listen to this message"):
                        with st.spinner("Generating audio..."):
                            try:
                                audio_bytes, engine_label = synthesize_bytes(
                                    text=saved_message,
                                    speed=st.session_state.general_speed,
                                )
                                b64 = base64.b64encode(audio_bytes).decode("utf-8")
                                st.session_state.cached_audio[message_id] = (b64, engine_label)
                                st.session_state.active_player_id = message_id
                                st.rerun()
                            except Exception as e:
                                st.error(f"TTS error: {e}")
                else:
                    # Expanded Ovular Player
                    cached = st.session_state.cached_audio.get(message_id)
                    if cached:
                        b64, engine_label = cached
                        render_ovular_audio_player(
                            audio_b64=b64,
                            player_key=str(message_id),
                            initial_speed=st.session_state.general_speed,
                        )
                    # Close / collapse button
                    if st.button("✖ Close player", key=f"close_{message_id}"):
                        st.session_state.active_player_id = None
                        st.rerun()

            with card_footer_col2:
                # Direct Calendar sync per message
                if st.button("📅 Add to Cal", key=f"cal_{message_id}", help="Sync this deadline to Calendar"):
                    m = re.search(r"(today|tonight|tomorrow|\d{1,2}[:/]\d{2}\s*(?:am|pm)?|\d{4}-\d{2}-\d{2})", saved_message.lower())
                    deadline_hint = m.group(0) if m else "Today"
                    res = sync_digest_to_calendars({
                        "ranked_summary": [{
                            "title": saved_message[:60],
                            "summary": saved_message,
                            "deadline": deadline_hint,
                            "urgency": "medium"
                        }]
                    })
                    if res:
                        gcal_link = res[0].get("google", {}).get("htmlLink")
                        ocal_link = res[0].get("outlook", {}).get("webLink")
                        if gcal_link:
                            st.markdown(f"[📅 Google]({gcal_link})")
                        if ocal_link:
                            st.markdown(f"[📧 Outlook]({ocal_link})")
