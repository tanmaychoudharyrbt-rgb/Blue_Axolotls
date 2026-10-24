"""
app.py — CampusSignal Dashboard (Fully Integrated Frontend + Summarizer + Voice + Calendar)

Seamlessly integrates:
  • Person A (Slack & Core): campussignal_core, SQLite persistence, Slack Socket Mode
  • Person B (AI Pipeline): extract_announcement, AnnouncementDigest, urgency ranking, zero hallucinations
  • Person C (Voice & Calendar): Kokoro TTS with expandable ovular player, speed controls, Google/Outlook Calendar sync
"""

import base64
import re
import sqlite3
from datetime import datetime
import streamlit as st
import streamlit.components.v1 as components

from campussignal_core import (
    DB_NAME,
    init_db,
    classify_message,
    message_exists,
    save_message,
)
from ai_pipeline.extractor import extract_announcement
from ai_pipeline.schema import AnnouncementDigest
from tts_kokoro import synthesize_bytes, check_kokoro_health
from calendar_integration import sync_digest_to_calendars

st.set_page_config(
    page_title="CampusSignal | College Communication & Voice Digest",
    page_icon="📚",
    layout="wide",
)

# ── Session State ──────────────────────────────────────────────────
if "general_speed" not in st.session_state:
    st.session_state.general_speed = 1.25
if "active_player_id" not in st.session_state:
    st.session_state.active_player_id = None
if "cached_audio" not in st.session_state:
    st.session_state.cached_audio = {}
if "extracted_digests" not in st.session_state:
    st.session_state.extracted_digests = {}

init_db()


def get_summary_text_for_speech(digest: AnnouncementDigest, raw_message: str) -> str:
    """Creates a natural, high-signal spoken summary from the extracted digest."""
    parts = []
    
    # Priority announcement intro
    if digest.urgency_level == "HIGH":
        parts.append("Urgent announcement:")
    else:
        parts.append("Campus notice:")

    # Core action and title
    title = digest.summary_title.strip().rstrip(".")
    parts.append(f"{title}.")

    if digest.required_action != "Not specified":
        parts.append(f"Action required: {digest.required_action}.")

    if digest.date_or_deadline != "Not specified":
        parts.append(f"Deadline: {digest.date_or_deadline}.")

    # Ranking reason if urgent
    if digest.urgency_level in ("HIGH", "MEDIUM") and digest.ranking_reason:
        reason = digest.ranking_reason.strip().rstrip(".")
        parts.append(f"Why it matters: {reason}.")

    return " ".join(parts)


def render_ovular_audio_player(audio_b64: str, player_key: str, initial_speed: float = 1.25):
    """
    Renders an expandable ovular capsule player with:
      • ▶️ / ⏸️ Play/Pause toggle
      • ⏹️ Stop
      • Time elapsed / Total duration
      • Scrub completion bar
      • Speed selector (0.75x to 3.0x)
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


# ── Title & Preferences ─────────────────────────────────────────────
st.title("📚 CampusSignal")
st.write("Your college Slack communication, organized, summarized with local AI, spoken aloud, and synced to calendar.")

with st.expander("⚙️ System Status & Preferences", expanded=False):
    c1, c2 = st.columns(2)
    with c1:
        st.session_state.general_speed = st.select_slider(
            "⚡ General Voice Speed:",
            options=[0.75, 1.0, 1.25, 1.5, 2.0, 3.0],
            value=st.session_state.general_speed,
            format_func=lambda x: f"{x}x speed",
        )
    with c2:
        if check_kokoro_health():
            st.success("🟢 **Kokoro-FastAPI Online** (Port :8880)")
        else:
            st.info("⚡ **Offline Voice Ready** (Instant Local Engine)")

col_main, col_side = st.columns([1.7, 1.3])

# ── Main Panel: Message Input & Summarizer ─────────────────────────
with col_main:
    st.subheader("📥 Paste a college message")
    message = st.text_area(
        "Announcement text:",
        placeholder="Example: Submit the lab report by 11 PM tonight. Mandatory attendance for final lab exam.",
        height=100,
    )

    btn_row1, btn_row2 = st.columns(2)
    analyze_btn = btn_row1.button("🔍 Analyze & Summarize", use_container_width=True)
    cal_main_btn = btn_row2.button("📅 Add to Calendar", use_container_width=True)

    if analyze_btn:
        if not message.strip():
            st.warning("Please enter announcement text.")
        else:
            clean_message = message.strip()
            with st.spinner("Classifying and extracting structured summary..."):
                # 1. Person A's classification
                category, used_ai = classify_message(clean_message)
                
                # 2. Person B's structured extraction & summarizer
                digest = extract_announcement(clean_message)
                st.session_state.extracted_digests[clean_message] = digest

                # 3. Save to database
                saved, message_id = save_message(
                    message=clean_message,
                    category=category,
                    source="dashboard",
                )

            # Display Summarizer Card
            st.success("Announcement Processed!")
            
            # Urgency pill
            u_icon = "🔴" if digest.urgency_level == "HIGH" else "🟡" if digest.urgency_level == "MEDIUM" else "🟢"
            st.markdown(f"### {u_icon} {digest.summary_title}")
            
            sum_col1, sum_col2 = st.columns(2)
            with sum_col1:
                st.markdown(f"**🏷️ Type:** `{digest.announcement_type}`")
                st.markdown(f"**⚡ Action Required:** `{digest.required_action}`")
            with sum_col2:
                st.markdown(f"**⏰ Deadline:** `{digest.date_or_deadline}`")
                st.markdown(f"**🎯 Urgency:** **{digest.urgency_level}** ({digest.ranking_reason})")

            st.divider()

    if cal_main_btn:
        if not message.strip():
            st.warning("Please enter a message first.")
        else:
            clean_message = message.strip()
            # Use Person B's extractor for exact factual deadline
            digest = extract_announcement(clean_message)
            deadline_str = digest.date_or_deadline if digest.date_or_deadline != "Not specified" else "Today, 11 PM"
            
            payload = {
                "ranked_summary": [
                    {
                        "title": digest.summary_title,
                        "summary": f"Action: {digest.required_action}\n{clean_message}",
                        "urgency": digest.urgency_level.lower(),
                        "deadline": deadline_str,
                        "type": digest.announcement_type,
                    }
                ]
            }
            results = sync_digest_to_calendars(payload, use_google=True, use_outlook=True)
            if results:
                r = results[0]
                gcal = r.get("google")
                ocal = r.get("outlook")
                st.success(f"📅 Deadline found: **{r['title']}** ({deadline_str})")
                col_g, col_o = st.columns(2)
                if gcal and gcal.get("htmlLink"):
                    col_g.markdown(f"[📅 **Open in Google Calendar**]({gcal['htmlLink']})")
                if ocal and ocal.get("webLink"):
                    col_o.markdown(f"[📧 **Open in Outlook Calendar**]({ocal['webLink']})")


# ── Side Panel: Saved Messages with Summarizer Badge & Voice Player ─
with col_side:
    st.subheader("📨 Saved Messages")

    with sqlite3.connect(DB_NAME) as conn:
        rows = conn.execute(
            """
            SELECT id, message, category, source, channel_id
            FROM messages
            ORDER BY id DESC
            """
        ).fetchall()

    st.write(f"Total stored messages: {len(rows)}")

    if not rows:
        st.info("No messages saved yet.")

    for message_id, saved_message, category, source, channel_id in rows:
        with st.container(border=True):
            # Header
            src_label = f"Slack ({channel_id})" if source == "slack" and channel_id else source.capitalize()
            st.caption(f"#{message_id} · {category} · {src_label}")

            # Extract or retrieve Person B's structured summary
            if saved_message not in st.session_state.extracted_digests:
                st.session_state.extracted_digests[saved_message] = extract_announcement(saved_message)
            digest = st.session_state.extracted_digests[saved_message]

            # Structured Summary Highlights
            u_icon = "🔴" if digest.urgency_level == "HIGH" else "🟡" if digest.urgency_level == "MEDIUM" else "🟢"
            st.markdown(f"**{u_icon} {digest.summary_title}**")
            
            if digest.date_or_deadline != "Not specified":
                st.caption(f"⏰ **Deadline:** {digest.date_or_deadline} · ⚡ **Action:** {digest.required_action}")
            
            st.write(saved_message[:120] + ("…" if len(saved_message) > 120 else ""))

            # ── Action Footer: Ovular Voice Player & Calendar Sync ──
            footer_col1, footer_col2 = st.columns([1.6, 1])
            is_active = (st.session_state.active_player_id == message_id)

            with footer_col1:
                if not is_active:
                    # Compact 🔊 icon button
                    if st.button("🔊 Listen", key=f"btn_listen_{message_id}", help="Listen to this announcement summary"):
                        with st.spinner("Synthesizing voice..."):
                            try:
                                # Speak the high-signal summary extracted by Person B
                                spoken_text = get_summary_text_for_speech(digest, saved_message)
                                audio_bytes, engine_label = synthesize_bytes(
                                    text=spoken_text,
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
                    if st.button("✖ Close player", key=f"close_{message_id}"):
                        st.session_state.active_player_id = None
                        st.rerun()

            with footer_col2:
                # Add to Calendar using Person B's extracted facts
                if st.button("📅 Add to Cal", key=f"cal_{message_id}", help="Add this deadline to Google & Outlook"):
                    deadline_val = digest.date_or_deadline if digest.date_or_deadline != "Not specified" else "Today"
                    res = sync_digest_to_calendars({
                        "ranked_summary": [{
                            "title": digest.summary_title,
                            "summary": f"Action required: {digest.required_action}\nAnnouncement: {saved_message}",
                            "deadline": deadline_val,
                            "urgency": digest.urgency_level.lower(),
                        }]
                    })
                    if res:
                        gcal_link = res[0].get("google", {}).get("htmlLink")
                        ocal_link = res[0].get("outlook", {}).get("webLink")
                        if gcal_link:
                            st.markdown(f"[📅 Google]({gcal_link})")
                        if ocal_link:
                            st.markdown(f"[📧 Outlook]({ocal_link})")
