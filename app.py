"""
app.py — CampusSignal Streamlit UI
Calendar branch: adds 📅 "Add to Calendar" button on top of main's app.py

BRANCH: calendar  (merges into main at the end)
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
from calendar_integration import sync_digest_to_calendars

st.set_page_config(page_title="CampusSignal", page_icon="📚")

init_db()

st.title("📚 CampusSignal")
st.write("Your college communication, organized.")
st.caption("Local AI classification powered by Qwen.")

message = st.text_area(
    "Paste a college message:",
    placeholder="Example: The endsem timetable is available on Moodle.",
)

col1, col2 = st.columns(2)
analyse_btn  = col1.button("Analyze message",    use_container_width=True)
calendar_btn = col2.button("📅 Add to Calendar", use_container_width=True)

# ── Analyse ───────────────────────────────────────────────────────
if analyse_btn:
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
                    st.warning(
                        "Qwen was unavailable. Used the keyword classifier instead."
                    )
            else:
                st.warning("🔁 This message was saved by another process.")

# ── Calendar sync ─────────────────────────────────────────────────
if calendar_btn:
    if not message.strip():
        st.warning("Please enter a message first.")
    else:
        # Build a minimal digest payload from the raw message
        category, _ = classify_message(message.strip())
        urgency = (
            "high"   if "Urgent" in category or "Important" in category
            else "medium" if "Academic" in category
            else "low"
        )

        # Try to extract a deadline hint from the message text
        import re
        deadline_hint = ""
        m = re.search(
            r"(today|tonight|tomorrow|\d{1,2}[:/]\d{2}\s*(?:am|pm)?|\d{4}-\d{2}-\d{2})",
            message.lower(),
        )
        if m:
            deadline_hint = m.group(0)

        payload = {
            "ranked_summary": [
                {
                    "title":    message.strip()[:80],
                    "summary":  message.strip(),
                    "urgency":  urgency,
                    "deadline": deadline_hint or "Today",
                    "type":     category,
                }
            ]
        }

        with st.spinner("📅 Syncing to Google & Outlook Calendar..."):
            try:
                results = sync_digest_to_calendars(
                    payload, use_google=True, use_outlook=True
                )
                if results:
                    for r in results:
                        st.success(f"📅 **{r['title'][:60]}** added to calendar!")
                        gcal = r.get("google")
                        ocal = r.get("outlook")
                        if gcal and gcal.get("htmlLink"):
                            st.markdown(f"[Open in Google Calendar 📅]({gcal['htmlLink']})")
                        if ocal and ocal.get("webLink"):
                            st.markdown(f"[Open in Outlook Calendar 📧]({ocal['webLink']})")
                else:
                    st.info(
                        "ℹ️ No clear deadline found in this message. "
                        "Add a time (e.g. 'by 5 PM today') for auto-calendar sync."
                    )
            except Exception as e:
                st.error(f"Calendar sync failed: {e}")

# ── Saved messages ────────────────────────────────────────────────
st.divider()
st.subheader("📨 Saved messages")

with sqlite3.connect(DB_NAME) as conn:
    rows = conn.execute(
        "SELECT id, message, category, source, channel_id FROM messages ORDER BY id DESC"
    ).fetchall()

st.write(f"Total unique messages: {len(rows)}")

if not rows:
    st.info("No messages have been saved yet.")

for message_id, saved_message, category, source, channel_id in rows:
    with st.container(border=True):
        label = f"Message #{message_id} · {category} · {'Slack' if source == 'slack' else 'Dashboard'}"
        st.caption(label)
        if channel_id:
            st.caption(f"Channel ID: {channel_id}")
        st.write(saved_message)
