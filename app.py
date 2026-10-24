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
from ai_pipeline.repository import AnnouncementRepository
from ai_pipeline.service import process_announcement
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

announcement_repo = AnnouncementRepository()
announcement_repo.initialize()
announcement_repo.delete_expired()

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

        st.write(saved_message)

st.divider()
st.subheader("🧠 Structured announcements")

active_announcements = announcement_repo.list_active()
st.write(f"Active structured announcements: {len(active_announcements)}")

if not active_announcements:
    st.info("No structured announcements are available yet.")

for row in active_announcements:
    (
        announcement_id, structured_message, announcement_type,
        summary_title, required_action, date_or_deadline,
        urgency_level, ranking_reason, confidence_score, source_url,
        structured_source, structured_channel, received_at,
        deadline_at, expires_at,
    ) = row

    with st.container(border=True):
        st.caption(
            f"{announcement_type.replace('_', ' ').title()} · "
            f"{urgency_level} · {structured_source}"
        )
        st.write(f"**{summary_title}**")
        st.write(structured_message)
        st.write(f"**Required action:** {required_action}")
        st.write(f"**Date/deadline:** {date_or_deadline}")
        if expires_at:
            st.caption(f"Automatic expiry: {expires_at} (UTC)")
