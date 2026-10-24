"""
app.py — CampusSignal Streamlit UI
Updated: Kokoro TTS playback (speed 0.25x–3.0x) + Google & Outlook Calendar sync
"""

import json
import sqlite3

import streamlit as st

from tts_kokoro import synthesize_stream, check_kokoro_health
from digest_format import format_text_digest

st.set_page_config(page_title="CampusSignal", page_icon="📚", layout="wide")

# ──────────────────────────────────────────────────────────────────
# Database setup
# ──────────────────────────────────────────────────────────────────
conn   = sqlite3.connect("campussignal.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
    CREATE TABLE IF NOT EXISTS messages (
        id        INTEGER PRIMARY KEY AUTOINCREMENT,
        message   TEXT NOT NULL,
        normalized TEXT NOT NULL,
        category  TEXT NOT NULL
    )
""")
conn.commit()


# ──────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────
def classify_message(text: str) -> str:
    t = text.lower()
    if any(w in t for w in ["worksheet", "assignment", "notes", "lecture", "deadline", "submit"]):
        return "📚 Academic"
    elif any(w in t for w in ["mandatory", "compulsory", "attendance", "urgent", "important"]):
        return "🚨 Important / Urgent"
    elif any(w in t for w in ["fest", "concert", "event", "registration", "signup"]):
        return "🎉 Event"
    return "💬 Other"


def urgency_from_category(cat: str) -> str:
    if "Urgent" in cat or "Important" in cat:
        return "high"
    if "Academic" in cat:
        return "medium"
    return "low"


def build_simple_payload(message: str, category: str) -> dict:
    """Wrap a single message into the ranked_summary format."""
    return {
        "ranked_summary": [
            {
                "title":   message[:60],
                "summary": message,
                "urgency": urgency_from_category(category),
                "type":    category,
            }
        ]
    }


# ──────────────────────────────────────────────────────────────────
# UI
# ──────────────────────────────────────────────────────────────────
st.title("📚 CampusSignal")
st.caption("Your college Slack communication — organized, summarised, and spoken aloud.")

col_main, col_side = st.columns([2, 1])

# ── Left: message input ───────────────────────────────────────────
with col_main:
    st.subheader("📥 Paste a Slack Message")
    message = st.text_area(
        "Message:",
        placeholder="Example: Register for the college fest by Friday 5 PM!",
        height=120,
    )

    # TTS speed slider
    st.markdown("**🔊 Voice Speed**")
    speed = st.slider(
        "Playback speed (1.0 = normal, max 3.0x)",
        min_value=0.25,
        max_value=3.0,
        value=1.0,
        step=0.25,
        help="Powered by Kokoro TTS — adjustable from slow (0.25×) to 3× speed",
    )

    btn_col1, btn_col2, btn_col3 = st.columns(3)
    analyze_btn  = btn_col1.button("🔍 Analyse Message", use_container_width=True)
    tts_btn      = btn_col2.button("🔊 Listen (TTS)",    use_container_width=True)
    calendar_btn = btn_col3.button("📅 Add to Calendar", use_container_width=True)

    # ── Analyse ───────────────────────────────────────────────────
    if analyze_btn:
        if not message.strip():
            st.warning("Please enter a message first.")
        else:
            normalized = message.lower().strip()
            cursor.execute("SELECT id FROM messages WHERE normalized = ?", (normalized,))
            if cursor.fetchone():
                st.warning("🔁 Duplicate detected — this message is already saved.")
            else:
                category = classify_message(normalized)
                cursor.execute(
                    "INSERT INTO messages (message, normalized, category) VALUES (?, ?, ?)",
                    (message.strip(), normalized, category),
                )
                conn.commit()
                st.success(f"✅ Saved!  Category: **{category}**")

    # ── TTS: Listen ───────────────────────────────────────────────
    if tts_btn:
        if not message.strip():
            st.warning("Please enter a message to listen to.")
        else:
            if not check_kokoro_health():
                st.error(
                    "❌ Kokoro TTS server is not running.\n\n"
                    "Start it with Docker:\n"
                    "```\ndocker run -p 8880:8880 ghcr.io/remsky/kokoro-fastapi-cpu:latest\n```"
                )
            else:
                with st.spinner(f"🎙️ Generating speech at {speed}× speed..."):
                    try:
                        audio_buf = synthesize_stream(
                            text=message.strip(),
                            voice="af_heart",
                            speed=speed,
                            fmt="mp3",
                        )
                        st.audio(audio_buf, format="audio/mp3")
                        st.caption(f"Speed: {speed}× · Voice: Kokoro af_heart")
                    except Exception as e:
                        st.error(f"TTS failed: {e}")

    # ── Calendar sync ─────────────────────────────────────────────
    if calendar_btn:
        if not message.strip():
            st.warning("Please enter a message first.")
        else:
            category = classify_message(message.lower().strip())
            payload  = build_simple_payload(message.strip(), category)
            with st.spinner("📅 Syncing to Google & Outlook Calendar..."):
                try:
                    from calendar_integration import sync_digest_to_calendars
                    results = sync_digest_to_calendars(payload, use_google=True, use_outlook=True)
                    if results:
                        for r in results:
                            gcal_link = r["google"].get("htmlLink") if r.get("google") else None
                            ocal_link = r["outlook"].get("webLink") if r.get("outlook") else None
                            st.success(f"📅 **{r['title']}** added to calendar!")
                            if gcal_link:
                                st.markdown(f"[Open in Google Calendar 📅]({gcal_link})")
                            if ocal_link:
                                st.markdown(f"[Open in Outlook Calendar 📧]({ocal_link})")
                    else:
                        st.info(
                            "ℹ️ No deadline found in this message.\n\n"
                            "Include a deadline (e.g. 'by 5 PM today') for auto-calendar sync."
                        )
                except Exception as e:
                    st.error(f"Calendar sync failed: {e}")


# ── Right: server status + saved messages ─────────────────────────
with col_side:
    st.subheader("⚙️ Status")
    kokoro_ok = check_kokoro_health()
    if kokoro_ok:
        st.success("🟢 Kokoro TTS server online")
    else:
        st.error("🔴 Kokoro TTS offline")
        st.code("docker run -p 8880:8880 ghcr.io/remsky/kokoro-fastapi-cpu:latest", language="bash")

    st.divider()
    st.subheader("📨 Saved Messages")
    cursor.execute("SELECT id, message, category FROM messages ORDER BY id DESC LIMIT 20")
    rows = cursor.fetchall()
    st.caption(f"Total unique messages: {len(rows)}")
    for msg_id, saved_msg, cat in rows:
        with st.container(border=True):
            st.caption(f"#{msg_id} · {cat}")
            st.write(saved_msg[:120] + ("…" if len(saved_msg) > 120 else ""))

conn.close()
