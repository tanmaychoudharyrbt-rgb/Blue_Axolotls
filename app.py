
import sqlite3
import streamlit as st

from campussignal_core import (
    DB_NAME,
    init_db,
    classify_message,
    message_exists,
    save_message
)
from ai_pipeline.repository import AnnouncementRepository
from ai_pipeline.service import process_announcement

st.set_page_config(
    page_title="CampusSignal",
    page_icon="📚"
)

init_db()

announcement_repo = AnnouncementRepository()
announcement_repo.initialize()
announcement_repo.delete_expired()

st.title("📚 CampusSignal")
st.write("Your college communication, organized.")
st.caption("Local AI classification powered by Qwen.")

message = st.text_area(
    "Paste a college message:",
    placeholder="Example: The endsem timetable is available on Moodle."
)

if st.button("Analyze message"):
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
                source="dashboard"
            )

            if saved:
                st.success("Message saved!")
                st.write("**Category:**", category)

                # Structured extraction is independent of legacy saving.
                try:
                    structured_saved, structured_id, digest = (
                        process_announcement(
                            clean_message,
                            source="dashboard",
                            repository=announcement_repo,
                        )
                    )
                    if structured_saved:
                        st.caption(
                            "Structured announcement saved: "
                            f"{digest.announcement_type}"
                        )
                    else:
                        st.caption(
                            "This structured announcement already exists."
                        )
                except Exception:
                    st.warning(
                        "The message was saved, but structured "
                        "extraction was unavailable. You can still "
                        "use the existing CampusSignal classification."
                    )
                    import logging
                    logging.exception(
                        "Structured dashboard extraction failed."
                    )

                if used_ai:
                    st.caption("Classified using Qwen.")
                else:
                    st.warning(
                        "Qwen was unavailable. "
                        "Used the keyword classifier instead."
                    )
            else:
                st.warning(
                    "🔁 This message was saved by another process."
                )


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
        if source == "slack":
            st.caption(
                f"Message #{message_id} · {category} · Slack"
            )

            if channel_id:
                st.caption(f"Channel ID: {channel_id}")
        else:
            st.caption(
                f"Message #{message_id} · {category} · Dashboard"
            )

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
