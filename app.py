
import sqlite3
import streamlit as st

from campussignal_core import (
    DB_NAME,
    init_db,
    classify_message,
    message_exists,
    save_message
)

st.set_page_config(
    page_title="CampusSignal",
    page_icon="📚"
)

init_db()

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
