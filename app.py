"""
app.py — CampusSignal Dashboard with Voice Extension
Preserves 100% of the team's core pipeline from campussignal_core:
  • Qwen / keyword classification
  • Shared SQLite database with Slack & Dashboard sources
  • Ingestion of real Slack messages and channel IDs
Seamlessly adds:
  • ▶️ Start / ⏹️ Stop TTS voice synthesis (0.25x – 3.0x speed)
  • Dedicated audio player with instant playback
  • Mini Play buttons on every Slack & Dashboard announcement
"""

import sqlite3
import streamlit as st

from campussignal_core import (
    DB_NAME,
    init_db,
    classify_message,
    message_exists,
    save_message,
)
from tts_kokoro import synthesize_stream, check_kokoro_health

st.set_page_config(
    page_title="CampusSignal | College Communication & Voice Digest",
    page_icon="📚",
    layout="wide",
)

# ── Session State for Voice Player ─────────────────────────────────
if "audio_bytes" not in st.session_state:
    st.session_state.audio_bytes = None
if "current_playing_title" not in st.session_state:
    st.session_state.current_playing_title = ""
if "engine_used" not in st.session_state:
    st.session_state.engine_used = ""

# Make sure the shared database exists
init_db()

st.title("📚 CampusSignal")
st.write("Your college communication, organized and spoken aloud.")
st.caption("Local AI classification powered by Qwen · Voice notes powered by Kokoro TTS.")

col_main, col_side = st.columns([2, 1])

# ── Main Panel: Message Input & Voice Controls ────────────────────
with col_main:
    message = st.text_area(
        "Paste a college message:",
        placeholder="Example: The endsem timetable is available on Moodle. Submit lab reports by 11 PM tonight.",
        height=110,
    )

    # Voice speed controls (0.25x – 3.0x)
    st.markdown("##### 🔊 Voice Playback Speed")
    speed = st.slider(
        "Voice speed multiplier:",
        min_value=0.25,
        max_value=3.0,
        value=1.5,
        step=0.25,
        help="Adjust voice tempo from relaxed (0.5x) to rapid skimming (3.0x).",
    )

    # Control buttons row
    btn1, btn2, btn3 = st.columns([1.3, 1.2, 1])
    analyze_btn = btn1.button("🔍 Analyze message", use_container_width=True)
    start_tts_btn = btn2.button("▶️ Start Voice", type="primary", use_container_width=True)
    stop_tts_btn = btn3.button("⏹️ Stop Voice", use_container_width=True)

    # Action 1: Analyze & Save (Friend's exact core logic)
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

    # Action 2: Stop Voice
    if stop_tts_btn:
        st.session_state.audio_bytes = None
        st.session_state.current_playing_title = ""
        st.session_state.engine_used = ""
        st.rerun()

    # Action 3: Start Voice
    if start_tts_btn:
        if not message.strip():
            st.warning("Please enter a message to listen to.")
        else:
            with st.spinner(f"🎙️ Synthesizing voice at {speed}× speed..."):
                try:
                    buf, engine_name = synthesize_stream(
                        text=message.strip(),
                        voice="af_heart",
                        speed=speed,
                        fmt="mp3",
                    )
                    st.session_state.audio_bytes = buf.getvalue()
                    st.session_state.current_playing_title = message.strip()[:80]
                    st.session_state.engine_used = engine_name
                except Exception as err:
                    st.error(f"Voice generation error: {err}")

    # Active Voice Player Widget
    if st.session_state.audio_bytes:
        st.divider()
        st.markdown(f"**Now Playing:** *\"{st.session_state.current_playing_title}...\"*")
        st.audio(st.session_state.audio_bytes, format="audio/mp3", autoplay=True)
        st.caption(f"Engine: **{st.session_state.engine_used}** · Click **⏹️ Stop Voice** to dismiss.")


# ── Side Panel: Engine Status & Saved Messages ────────────────────
with col_side:
    st.subheader("⚙️ System Status")
    if check_kokoro_health():
        st.success("🟢 **Kokoro-FastAPI Online** (Docker :8880)")
    else:
        st.info("⚡ **Offline Voice Ready** (Instant Local Engine)")

    st.divider()
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
            header_col, play_col = st.columns([3, 1])
            if source == "slack":
                header_col.caption(f"Message #{message_id} · {category} · Slack")
                if channel_id:
                    header_col.caption(f"Channel ID: {channel_id}")
            else:
                header_col.caption(f"Message #{message_id} · {category} · Dashboard")

            # Mini Play button on every message card (Slack or Dashboard)
            if play_col.button("▶️ Play", key=f"play_msg_{message_id}"):
                with st.spinner("Generating audio..."):
                    try:
                        buf, engine_name = synthesize_stream(
                            text=saved_message,
                            voice="af_heart",
                            speed=speed,
                            fmt="mp3",
                        )
                        st.session_state.audio_bytes = buf.getvalue()
                        st.session_state.current_playing_title = saved_message[:60]
                        st.session_state.engine_used = engine_name
                        st.rerun()
                    except Exception as err:
                        st.error(f"Playback error: {err}")

            st.write(saved_message)
