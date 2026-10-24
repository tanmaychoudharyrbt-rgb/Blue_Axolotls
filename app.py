
import streamlit as st
import sqlite3
import json
import urllib.request
import urllib.error
import socket
import re

st.set_page_config(page_title="CampusSignal", page_icon="📚")

DB_NAME = "campussignal.db"
MODEL = "qwen3:4b"

# Expanded vocabulary for the fallback classifier
URGENT_WORDS = [
    "mandatory", "compulsory", "urgent", "immediately",
    "asap", "must attend", "action required",
    "final reminder", "emergency", "critical notice",
    "cancelled", "canceled", "postponed", "rescheduled",
    "deadline today", "submit today", "report immediately"
]

ACADEMIC_WORDS = [
    "worksheet", "assignment", "homework", "coursework",
    "problem set", "practice set", "tutorial sheet",
    "notes", "lecture", "slides", "syllabus", "curriculum",
    "exam", "examination", "test", "quiz", "midsem",
    "mid-sem", "mid semester", "endsem", "end-sem",
    "finals", "lab", "laboratory", "practical", "experiment",
    "viva", "submission", "due date", "timetable",
    "time table", "question paper", "pyq", "study material",
    "grades", "marks", "results", "moodle", "semester",
    "internal assessment", "lecture recording"
]

EVENT_WORDS = [
    "fest", "festival", "concert", "event", "hackathon",
    "workshop", "seminar", "conference", "competition",
    "contest", "tournament", "auditions", "orientation",
    "freshers", "farewell", "club recruitment", "club induction",
    "register now", "sign up", "guest speaker", "open mic",
    "exhibition", "showcase", "meetup", "sports day",
    "annual day", "cultural night", "coding competition",
    "robotics event", "volunteer for", "tickets available"
]


def contains_any(text, words):
    for word in words:
        pattern = r"(?<!\w)" + re.escape(word) + r"(?!\w)"
        if re.search(pattern, text):
            return True
    return False


def classify_with_rules(message):
    text = message.lower()

    if contains_any(text, URGENT_WORDS):
        return "🚨 Urgent"
    if contains_any(text, ACADEMIC_WORDS):
        return "📚 Academic"
    if contains_any(text, EVENT_WORDS):
        return "🎉 Event"

    return "💬 Other"


def classify_with_qwen(message):
    categories = ["Academic", "Urgent", "Event", "Other"]

    payload = {
        "model": MODEL,
        "stream": False,
        "think": False,
        "keep_alive": "10m",
        "format": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "enum": categories
                }
            },
            "required": ["category"]
        },
        "options": {
            "num_predict": 30,
            "temperature": 0
        },
        "messages": [
            {
                "role": "system",
                "content": (
                    "Classify this college message into one category. "
                    "Academic: assignments, worksheets, exams, labs, "
                    "lectures, notes, submissions, midsems, endsems, "
                    "PYQs, timetables and grades. "
                    "Urgent: emergencies, compulsory attendance, "
                    "immediate action, cancellations and critical notices. "
                    "Event: fests, concerts, hackathons, workshops, "
                    "seminars, competitions, club activities and registrations. "
                    "Other: general information and casual conversation. "
                    "Understand synonyms, abbreviations and informal wording. "
                    "Use the whole message, not just keywords. "
                    "Return only the required category in JSON."
                )
            },
            {
                "role": "user",
                "content": message
            }
        ]
    }

    request = urllib.request.Request(
        "http://localhost:11434/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    with urllib.request.urlopen(request, timeout=45) as response:
        result = json.loads(response.read().decode("utf-8"))

    answer = json.loads(result["message"]["content"])
    category = answer["category"]

    labels = {
        "Academic": "📚 Academic",
        "Urgent": "🚨 Urgent",
        "Event": "🎉 Event",
        "Other": "💬 Other"
    }

    if category not in labels:
        raise ValueError("Invalid category from Qwen")

    return labels[category]


def classify_message(message):
    try:
        return classify_with_qwen(message), True
    except (
        urllib.error.URLError,
        urllib.error.HTTPError,
        TimeoutError,
        socket.timeout,
        ValueError,
        KeyError,
        json.JSONDecodeError
    ):
        return classify_with_rules(message), False


# Create database without deleting existing records
with sqlite3.connect(DB_NAME) as conn:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            message TEXT NOT NULL,
            normalized TEXT NOT NULL,
            category TEXT NOT NULL
        )
    """)


st.title("📚 CampusSignal")
st.write("Your college communication, organized.")
st.caption("Local AI classification powered by Qwen.")

message = st.text_area(
    "Paste a college Slack message:",
    placeholder="Example: The endsem timetable is available on Moodle."
)

if st.button("Analyze message"):
    if not message.strip():
        st.warning("Please enter a message.")
    else:
        clean_message = message.strip()
        normalized = clean_message.lower()

        with sqlite3.connect(DB_NAME) as conn:
            existing = conn.execute(
                "SELECT id FROM messages WHERE normalized = ?",
                (normalized,)
            ).fetchone()

        if existing:
            st.warning("🔁 This exact message is already saved.")
        else:
            with st.spinner("Classifying message..."):
                category, used_ai = classify_message(clean_message)

            with sqlite3.connect(DB_NAME) as conn:
                conn.execute(
                    """
                    INSERT INTO messages (message, normalized, category)
                    VALUES (?, ?, ?)
                    """,
                    (clean_message, normalized, category)
                )

            st.success("Message saved!")
            st.write("**Category:**", category)

            if used_ai:
                st.caption("Classified using Qwen.")
            else:
                st.warning(
                    "Qwen did not respond in time. "
                    "Used the keyword classifier instead."
                )


st.divider()
st.subheader("📨 Saved messages")

with sqlite3.connect(DB_NAME) as conn:
    rows = conn.execute(
        "SELECT id, message, category FROM messages ORDER BY id DESC"
    ).fetchall()

st.write(f"Total unique messages: {len(rows)}")

for message_id, saved_message, category in rows:
    with st.container(border=True):
        st.caption(f"Message #{message_id} · {category}")
        st.write(saved_message)
