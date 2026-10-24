
import json
import os
import re
import socket
import sqlite3
import urllib.request
import urllib.error

DB_NAME = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "campussignal.db"
)

MODEL = "qwen3:4b"

URGENT_WORDS = [
    "urgent", "urgently", "emergency", "immediately",
    "asap", "action required", "mandatory", "compulsory",
    "must attend", "attendance is compulsory",
    "attendance is mandatory", "strictly mandatory",
    "final reminder", "last reminder", "last chance",
    "final warning", "deadline today", "due today",
    "submit today", "report immediately", "no extension",
    "deadline extended", "deadline approaching",
    "last date", "last date to submit", "overdue",
    "cancelled", "canceled", "postponed", "rescheduled",
    "suspended", "important notice", "critical notice",
    "immediate action", "time sensitive", "time-sensitive",
    "failure to comply", "attendance required",
    "registration closes today", "closes tonight"
]

EXAM_WORDS = [
    "exam", "exams", "examination", "examinations",
    "endsem", "end-sem", "end sem", "end semester",
    "midsem", "mid-sem", "mid sem", "mid semester",
    "midterm", "mid-term", "finals", "final exam",
    "unit test", "class test", "surprise test",
    "test", "quiz", "mock test", "practice test",
    "assessment", "internal assessment", "evaluation",
    "viva", "practical exam", "lab exam",
    "exam timetable", "exam schedule", "date sheet",
    "hall ticket", "admit card", "exam form",
    "exam registration", "exam postponed",
    "exam cancelled", "exam canceled",
    "exam rescheduled", "exam syllabus",
    "question paper", "previous year questions",
    "pyq", "answer key", "results declared",
    "exam results", "revaluation", "backlog exam",
    "supplementary exam", "retake", "grading"
]

ACADEMIC_WORDS = [
    "assignment", "assignments", "homework",
    "coursework", "worksheet", "worksheets",
    "problem set", "practice set", "tutorial sheet",
    "lecture", "lectures", "lecture notes",
    "notes", "slides", "ppt", "pdf notes",
    "syllabus", "curriculum", "study material",
    "reference material", "textbook", "reading material",
    "chapter", "unit", "module", "lab", "laboratory",
    "experiment", "lab manual", "lab record",
    "practical", "submission", "submit", "due date",
    "moodle", "classroom", "attendance",
    "timetable", "time table", "lecture recording",
    "project", "project report", "research paper",
    "grades", "marks", "results", "credits",
    "academic calendar", "course registration",
    "department notice", "faculty notice",
    "office hours", "tutorial", "doubt session"
]

EVENT_WORDS = [
    "fest", "festival", "concert", "hackathon",
    "workshop", "seminar", "conference", "contest",
    "competition", "coding contest", "coding competition",
    "tournament", "sports day", "auditions",
    "orientation", "freshers", "farewell",
    "club recruitment", "club induction", "club meeting",
    "registration open", "register now", "sign up",
    "guest speaker", "open mic", "exhibition",
    "showcase", "meetup", "annual day",
    "cultural night", "robotics event", "volunteer",
    "volunteering", "networking event", "webinar",
    "ideathon", "quiz competition", "prize distribution",
    "certificate ceremony", "award ceremony",
    "technical event", "non-technical event",
    "event registration", "event venue"
]


def normalize_message(message):
    return re.sub(r"\s+", " ", message.strip().lower())


def init_db():
    """Create the table and safely upgrade an existing database."""
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message TEXT NOT NULL,
                normalized TEXT NOT NULL,
                category TEXT NOT NULL
            )
        """)

        columns = {
            row[1]
            for row in conn.execute(
                "PRAGMA table_info(messages)"
            ).fetchall()
        }

        # Add these columns without deleting existing messages.
        if "source" not in columns:
            conn.execute("""
                ALTER TABLE messages
                ADD COLUMN source TEXT NOT NULL DEFAULT 'dashboard'
            """)

        if "channel_id" not in columns:
            conn.execute("""
                ALTER TABLE messages
                ADD COLUMN channel_id TEXT
            """)

        if "slack_ts" not in columns:
            conn.execute("""
                ALTER TABLE messages
                ADD COLUMN slack_ts TEXT
            """)


def contains_any(text, words):
    for word in words:
        pattern = r"(?<!\w)" + re.escape(word) + r"(?!\w)"
        if re.search(pattern, text):
            return True
    return False


def classify_with_rules(message):
    text = message.lower()

    # Urgency always takes priority.
    if contains_any(text, URGENT_WORDS):
        return "🚨 Urgent"

    # Exam-related messages get their own category.
    if contains_any(text, EXAM_WORDS):
        return "📝 Exam Alert"

    if contains_any(text, ACADEMIC_WORDS):
        return "📚 Academic"

    if contains_any(text, EVENT_WORDS):
        return "🎉 Event"

    return "💬 Other"



def classify_with_qwen(message):
    categories = [
        "Academic",
        "Urgent",
        "Exam Alert",
        "Event",
        "Other"
    ]

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
            "num_predict": 40,
            "temperature": 0
        },
        "messages": [
            {
                "role": "system",
                "content": (
                    "Classify this college message into exactly one category.\n\n"

                    "Urgent: Messages requiring immediate attention or action, "
                    "emergencies, compulsory attendance, immediate deadlines, "
                    "critical notices, cancellations, postponements, and "
                    "important changes requiring prompt action.\n"

                    "Exam Alert: Exam announcements, exam schedules, "
                    "midsems, endsems, midterms, tests, quizzes, mock tests, "
                    "vivas, practical exams, exam forms, hall tickets, "
                    "exam results, and exam-related instructions.\n"

                    "Academic: Assignments, homework, worksheets, lecture "
                    "notes, slides, labs, projects, syllabus, study material, "
                    "submissions, timetables, grades, and regular coursework.\n"

                    "Event: Hackathons, contests, competitions, fests, "
                    "seminars, workshops, club activities, tournaments, "
                    "auditions, and event registrations.\n"

                    "Other: Casual conversation and general messages "
                    "that do not fit the categories above.\n\n"

                    "PRIORITY RULES:\n"
                    "1. If immediate action is required, classify as Urgent, "
                    "even if the message concerns an exam or assignment.\n"
                    "2. Otherwise, classify exam-related announcements as "
                    "Exam Alert, not Academic.\n"
                    "3. Classify academic coursework as Academic.\n"
                    "4. Classify events and competitions as Event, unless "
                    "immediate action makes them Urgent.\n"
                    "5. Do not assume a message is urgent merely because "
                    "it mentions an exam, deadline, or important topic. "
                    "Consider the full context.\n"
                    "6. Understand synonyms, abbreviations, and informal "
                    "college language. Return only the required category."
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
        "Exam Alert": "📝 Exam Alert",
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
        TimeoutError,
        socket.timeout,
        ValueError,
        KeyError,
        TypeError
    ):
        return classify_with_rules(message), False


def message_exists(message):
    normalized = normalize_message(message)

    with sqlite3.connect(DB_NAME) as conn:
        row = conn.execute(
            "SELECT id FROM messages WHERE normalized = ? LIMIT 1",
            (normalized,)
        ).fetchone()

    return row is not None


def save_message(
    message,
    category,
    source="dashboard",
    channel_id=None,
    slack_ts=None
):
    """Save a unique message and return (was_saved, message_id)."""
    normalized = normalize_message(message)

    with sqlite3.connect(DB_NAME) as conn:
        existing = conn.execute(
            "SELECT id FROM messages WHERE normalized = ? LIMIT 1",
            (normalized,)
        ).fetchone()

        if existing:
            return False, existing[0]

        cursor = conn.execute(
            """
            INSERT INTO messages (
                message, normalized, category, source,
                channel_id, slack_ts
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                message.strip(),
                normalized,
                category,
                source,
                channel_id,
                slack_ts
            )
        )

        return True, cursor.lastrowid
