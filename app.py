
import streamlit as st
import sqlite3

st.set_page_config(page_title="CampusSignal", page_icon="📚")

# Connect to the database (creates it automatically)
conn = sqlite3.connect("campussignal.db")
cursor = conn.cursor()

cursor.execute("""
    CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        message TEXT NOT NULL,
        normalized TEXT NOT NULL,
        category TEXT NOT NULL
    )
""")
conn.commit()

def classify_message(text):
    if any(word in text for word in ["worksheet", "assignment", "notes", "lecture"]):
        return "📚 Academic"
    elif any(word in text for word in ["mandatory", "compulsory", "attendance", "urgent"]):
        return "🚨 Important / Urgent"
    elif any(word in text for word in ["fest", "concert", "event", "registration"]):
        return "🎉 Event"
    return "💬 Other"

st.title("📚 CampusSignal")
st.write("Your college communication, organized.")

message = st.text_area(
    "Paste a college Slack message here:",
    placeholder="Example: Register for the college fest!"
)

if st.button("Analyze message"):
    if not message.strip():
        st.warning("Please enter a message.")
    else:
        normalized = message.lower().strip()

        cursor.execute(
            "SELECT id FROM messages WHERE normalized = ?",
            (normalized,)
        )
        existing = cursor.fetchone()

        if existing:
            st.warning("🔁 Duplicate detected! This message is already in the database.")
        else:
            category = classify_message(normalized)

            cursor.execute(
                "INSERT INTO messages (message, normalized, category) VALUES (?, ?, ?)",
                (message.strip(), normalized, category)
            )
            conn.commit()

            st.success("New message saved!")
            st.write("**Category:**", category)

st.divider()
st.subheader("📨 Saved messages")

cursor.execute("SELECT id, message, category FROM messages ORDER BY id DESC")
rows = cursor.fetchall()

st.write(f"Total unique messages: {len(rows)}")

for message_id, saved_message, category in rows:
    with st.container(border=True):
        st.caption(f"Message #{message_id} · {category}")
        st.write(saved_message)

conn.close()
