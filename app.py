"""
app.py — CampusSignal (Voice branch)
Interactive college announcement assistant with:
  • Message classification and persistence (SQLite)
  • ▶️ Start / ⏹️ Stop TTS Voice Player
  • Variable playback speed control (0.25x – 3.0x) powered by Kokoro with local fallback
  • Mini Play/Stop controls on every saved message
"""

import sqlite3
import streamlit as st

from tts_kokoro import synthesize_stream, check_kokoro_health

st.set_page_config(
    page_title="CampusSignal | Voice Digest",
    page_icon="🔊",
    layout="wide",
)

# ── Session State for Audio Player ─────────────────────────────────
if "audio_bytes" not in st.session_state:
    st.session_state.audio_bytes = None
if "current_playing_title" not in st.session_state:
    st.session_state.current_playing_title = ""
if "engine_used" not in st.session_state:
    st.session_state.engine_used = ""

# ── Database Initialization ────────────────────────────────────────
conn = sqlite3.connect("campussignal.db", check_same_thread=False)
cursor = conn.cursor()
cursor.execute("""
    CREATE TABLE IF NOT EXISTS messages (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        message    TEXT NOT NULL,
        normalized TEXT NOT NULL,
        category   TEXT NOT NULL
    )
""")
conn.commit()


def classify_message(text: str) -> str:
    t = text.lower()
    if any(w in t for w in ["worksheet", "assignment", "notes", "lecture", "deadline", "submit", "exam", "test"]):
        return "📚 Academic"
    elif any(w in t for w in ["mandatory", "compulsory", "attendance", "urgent", "important"]):
        return "🚨 Important / Urgent"
    elif any(w in t for w in ["fest", "concert", "event", "registration", "signup", "volunteer"]):
        return "🎉 Event"
    return "💬 Other"


# ── Title & Intro ──────────────────────────────────────────────────
st.title("🔊 CampusSignal — Voice Assistant")
st.caption("Convert Slack updates into action digests with high-speed voice playback (0.25x – 3.0x).")

col_main, col_side = st.columns([2, 1])

# ── Main Input & Control Panel ─────────────────────────────────────
with col_main:
    st.subheader("📥 Announcement Input")
    message = st.text_area(
        "Paste a Slack Announcement:",
        value="Lab report submission deadline moved to tonight 11 PM. Submit via portal.",
        height=100,
    )

    # Speed control slider
    st.markdown("##### ⚡ Playback Speed (Kokoro Engine)")
    speed = st.slider(
        "Select speed multiplier:",
        min_value=0.25,
        max_value=3.0,
        value=1.5,
        step=0.25,
        help="Adjust voice tempo from relaxed (0.5x) to fast skimming (3.0x).",
    )

    # Control buttons row: Analyse, Start Voice, Stop Voice
    btn_col1, btn_col2, btn_col3 = st.columns([1.2, 1.2, 1])
    analyse_btn = btn_col1.button("🔍 Analyse & Save", use_container_width=True)
    start_tts_btn = btn_col2.button("▶️ Start Voice", type="primary", use_container_width=True)
    stop_tts_btn = btn_col3.button("⏹️ Stop Voice", use_container_width=True)

    # 1. Action: Analyse & Save
    if analyse_btn:
        if not message.strip():
            st.warning("Please enter announcement text.")
        else:
            normalized = message.lower().strip()
            cursor.execute("SELECT id FROM messages WHERE normalized = ?", (normalized,))
            if cursor.fetchone():
                st.warning("🔁 Duplicate: This announcement is already saved in the database.")
            else:
                cat = classify_message(normalized)
                cursor.execute(
                    "INSERT INTO messages (message, normalized, category) VALUES (?, ?, ?)",
                    (message.strip(), normalized, cat),
                )
                conn.commit()
                st.success(f"✅ Saved under category: **{cat}**")

    # 2. Action: Stop TTS
    if stop_tts_btn:
        st.session_state.audio_bytes = None
        st.session_state.current_playing_title = ""
        st.session_state.engine_used = ""
        st.rerun()

    # 3. Action: Start TTS
    if start_tts_btn:
        if not message.strip():
            st.warning("Please enter or paste an announcement first.")
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

    # ── Dedicated Audio Player Widget ──────────────────────────────
    if st.session_state.audio_bytes:
        st.divider()
        st.markdown(f"**Now Playing:** *\"{st.session_state.current_playing_title}...\"*")
        
        # Streamlit standard audio player with built-in play, pause, seek, volume, and stop
        st.audio(st.session_state.audio_bytes, format="audio/mp3", autoplay=True)
        st.caption(f"Engine: **{st.session_state.engine_used}** · Click **⏹️ Stop Voice** to dismiss.")


# ── Sidebar: Status & Saved Announcements ─────────────────────────
with col_side:
    st.subheader("⚙️ System Status")
    kokoro_active = check_kokoro_health()
    if kokoro_active:
        st.success("🟢 **Kokoro-FastAPI Online** (Docker :8880)")
    else:
        st.info("⚡ **Offline Voice Ready** (Instant Mac/Local Engine)")

    st.divider()
    st.subheader("📨 Saved Announcements")
    cursor.execute("SELECT id, message, category FROM messages ORDER BY id DESC LIMIT 15")
    rows = cursor.fetchall()
    st.caption(f"Total stored messages: {len(rows)}")

    for msg_id, saved_msg, cat in rows:
        with st.container(border=True):
            head_col, play_col = st.columns([3, 1])
            head_col.caption(f"#{msg_id} · {cat}")
            
            # Mini Play button on each item
            if play_col.button("▶️ Play", key=f"play_item_{msg_id}"):
                with st.spinner("Loading audio..."):
                    try:
                        buf, engine_name = synthesize_stream(
                            text=saved_msg,
                            voice="af_heart",
                            speed=speed,
                            fmt="mp3",
                        )
                        st.session_state.audio_bytes = buf.getvalue()
                        st.session_state.current_playing_title = saved_msg[:60]
                        st.session_state.engine_used = engine_name
                        st.rerun()
                    except Exception as e:
                        st.error(f"Playback error: {e}")

            st.write(saved_msg[:120] + ("…" if len(saved_msg) > 120 else ""))

conn.close()
