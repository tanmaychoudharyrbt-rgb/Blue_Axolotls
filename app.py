"""
app.py — CampusSignal  |  voice branch
- Analyse & save messages
- 🔊 Listen button: speaks any message aloud
  • Uses Kokoro TTS (Docker) when available → speed 0.25x–3.0x
  • Falls back to gTTS automatically when Docker is not running
"""

import sqlite3
import io

import streamlit as st

from tts_kokoro import synthesize_stream, check_kokoro_health

st.set_page_config(page_title="CampusSignal", page_icon="📚", layout="wide")

# ── Database ──────────────────────────────────────────────────────
conn   = sqlite3.connect("campussignal.db", check_same_thread=False)
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


# ── Header ────────────────────────────────────────────────────────
st.title("📚 CampusSignal")
st.caption("Your college Slack communication — organized and spoken aloud.")

col_main, col_side = st.columns([2, 1])

# ── Main panel ────────────────────────────────────────────────────
with col_main:
    st.subheader("📥 Paste a Slack Message")
    message = st.text_area(
        "Message:",
        placeholder="Example: Submit the lab report by 11 PM tonight!",
        height=130,
    )

    # ── Speed slider (shown always, used by Kokoro when available) ──
    st.markdown("**🔊 Voice Speed**")
    speed = st.slider(
        "Playback speed  (1.0 = normal, up to 3×)",
        min_value=0.25,
        max_value=3.0,
        value=1.0,
        step=0.25,
        help="Speed control works with Kokoro TTS. gTTS fallback always plays at normal speed.",
    )

    # ── Buttons ─────────────────────────────────────────────────────
    btn1, btn2 = st.columns(2)
    analyse_btn = btn1.button("🔍 Analyse Message", use_container_width=True)
    tts_btn     = btn2.button("🔊 Listen",          use_container_width=True)

    # ── Analyse ─────────────────────────────────────────────────────
    if analyse_btn:
        if not message.strip():
            st.warning("Please enter a message first.")
        else:
            normalized = message.lower().strip()
            cursor.execute("SELECT id FROM messages WHERE normalized = ?", (normalized,))
            if cursor.fetchone():
                st.warning("🔁 Duplicate — this message is already saved.")
            else:
                category = classify_message(normalized)
                cursor.execute(
                    "INSERT INTO messages (message, normalized, category) VALUES (?, ?, ?)",
                    (message.strip(), normalized, category),
                )
                conn.commit()
                st.success(f"✅ Saved!  Category: **{category}**")

    # ── 🔊 Listen ────────────────────────────────────────────────────
    if tts_btn:
        if not message.strip():
            st.warning("Please enter a message to listen to.")
        else:
            kokoro_on = check_kokoro_health()
            engine_label = f"Kokoro ({speed}×)" if kokoro_on else "gTTS (fallback, normal speed)"

            with st.spinner(f"🎙️ Generating speech via {engine_label} ..."):
                try:
                    audio_buf, engine_used = synthesize_stream(
                        text=message.strip(),
                        voice="af_heart",
                        speed=speed,
                        fmt="mp3",
                    )
                    st.audio(audio_buf, format="audio/mp3")
                    st.caption(f"🔊 Played via **{engine_used}**")

                    if not kokoro_on:
                        st.info(
                            "💡 **Tip:** Start Kokoro with Docker for better voice quality "
                            "and speed control up to 3×:\n\n"
                            "```\ndocker run -p 8880:8880 ghcr.io/remsky/kokoro-fastapi-cpu:latest\n```"
                        )
                except Exception as e:
                    st.error(f"TTS error: {e}")


# ── Side panel: status + saved messages ──────────────────────────
with col_side:
    st.subheader("⚙️ TTS Status")
    if check_kokoro_health():
        st.success("🟢 Kokoro online — speed control active")
    else:
        st.warning("🟡 Kokoro offline — using gTTS fallback")
        with st.expander("Upgrade to Kokoro (optional)"):
            st.code(
                "docker run -p 8880:8880 "
                "ghcr.io/remsky/kokoro-fastapi-cpu:latest",
                language="bash",
            )

    st.divider()
    st.subheader("📨 Saved Messages")
    cursor.execute("SELECT id, message, category FROM messages ORDER BY id DESC LIMIT 20")
    rows = cursor.fetchall()
    st.caption(f"{len(rows)} unique message(s) saved")

    for msg_id, saved_msg, cat in rows:
        with st.container(border=True):
            st.caption(f"#{msg_id} · {cat}")
            # 🔊 mini listen button per saved message
            if st.button("🔊", key=f"play_{msg_id}", help="Listen to this message"):
                kokoro_on = check_kokoro_health()
                with st.spinner("Generating audio..."):
                    try:
                        audio_buf, engine_used = synthesize_stream(
                            text=saved_msg,
                            voice="af_heart",
                            speed=speed,
                            fmt="mp3",
                        )
                        st.audio(audio_buf, format="audio/mp3")
                        st.caption(f"via {engine_used}")
                    except Exception as e:
                        st.error(f"TTS error: {e}")
            st.write(saved_msg[:120] + ("…" if len(saved_msg) > 120 else ""))

conn.close()
