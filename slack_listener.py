import os
import re
import json
import urllib.request

from dotenv import load_dotenv
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from campussignal_core import (
    MODEL,
    init_db,
    classify_message,
    save_message,
)
from ai_pipeline.repository import AnnouncementRepository
from ai_pipeline.service import process_announcement

load_dotenv()

bot_token = os.getenv("SLACK_BOT_TOKEN")
app_token = os.getenv("SLACK_APP_TOKEN")

if not bot_token or not app_token:
    raise ValueError("Slack tokens missing. Check your .env file.")

# Keep legacy and structured data in the same database file,
# but in separate tables.
init_db()

announcement_repo = AnnouncementRepository()
announcement_repo.initialize()
announcement_repo.delete_expired()

slack_app = App(token=bot_token)

# Only these categories trigger a notification ("Other" is ignored).
NOTIFICATION_STYLES = {
    "🚨 Urgent": {
        "label": "🔴 URGENT",
        "color": "#E01E5A",
    },
    "📝 Exam Alert": {
        "label": "🟠 EXAM ALERT",
        "color": "#F28C28",
    },
    "📚 Academic": {
        "label": "🔵 ACADEMIC",
        "color": "#1264A3",
    },
    "🎉 Event": {
        "label": "🟢 EVENT",
        "color": "#2BAC76",
    },
}


REASONING_MARKERS = (
    "the user wants", "the user is asking", "looking at the",
    "i need to", "i should", "let me", "hmm,", "okay, so",
    "the rules say", "i'll ", "first, i",
)


def looks_like_reasoning(text):
    """True if the model leaked its chain-of-thought instead of a summary."""
    lowered = text.strip().lower()
    return lowered.startswith(REASONING_MARKERS) or any(
        marker in lowered[:200] for marker in REASONING_MARKERS[:3]
    )


def fallback_summary(message, limit=140):
    """Short, safe summary used whenever the AI output can't be trusted."""
    cleaned = " ".join(message.split())
    return cleaned if len(cleaned) <= limit else cleaned[:limit].rstrip() + "…"


def summarize_message(message):
    """Summarize a Slack message using local Qwen through Ollama."""

    prompt = f"""Summarize this college Slack message into its most important information.

Rules:
- Use 1-2 short sentences (under 25 words total).
- Preserve important facts, dates, times, locations and deadlines.
- Do not invent information or change the meaning.
- For exam notices, clearly state the exam and any date or change.
- For urgent notices, clearly state the issue and required action.
- Remove greetings, repetition and unnecessary details.
- Return ONLY the summary. No explanation, no preamble.

Message:
{message}
"""

    payload = {
        "model": MODEL,
        "stream": False,
        # Qwen3 "thinks" by default; its reasoning must never be posted.
        "think": False,
        "keep_alive": "10m",
        "messages": [{"role": "user", "content": prompt}],
        "options": {
            "temperature": 0.2,
            "num_predict": 150,
        },
    }

    request = urllib.request.Request(
        "http://localhost:11434/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            result = json.loads(response.read().decode("utf-8"))

        # Cut off mid-generation -> the summary is incomplete, don't post it.
        if result.get("done_reason") == "length":
            print("Summary truncated by token limit; using fallback.")
            return fallback_summary(message)

        summary = result.get("message", {}).get("content", "")

        # Remove any leaked reasoning block (closed or unclosed).
        summary = re.sub(r"<think>.*?</think>", "", summary, flags=re.DOTALL)
        summary = re.sub(r"<think>.*", "", summary, flags=re.DOTALL).strip()

        if summary and not looks_like_reasoning(summary):
            return summary

        print("Model returned reasoning instead of a summary; using fallback.")

    except Exception as error:
        print(f"Summarization failed, using original text: {error}")

    # Keep notifications working if Ollama is unavailable or misbehaves.
    return fallback_summary(message)


def post_notification(channel_id, style, summary):
    """Post ONE short notification.

    `text` is what phone push notifications / lock-screen bubbles show,
    so it holds only the label + the summary. `blocks` is what the
    channel displays, so there is no duplicate copy.
    """

    mention = os.getenv("NOTIFY_USER_ID", "").strip()  # e.g. U012ABCDEF
    prefix = f"<@{mention}> " if mention else ""
    push_text = f"{prefix}{style['label']} — {summary}"

    slack_app.client.chat_postMessage(
        channel=channel_id,
        text=push_text,
        blocks=[
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"{prefix}*{style['label']}*\n{summary}",
                },
            },
            {
                "type": "context",
                "elements": [
                    {"type": "mrkdwn", "text": "_Summarized by CampusSignal_"}
                ],
            },
        ],
        unfurl_links=False,
        unfurl_media=False,
    )


@slack_app.event("message")
def handle_message(event, logger):
    # Ignore bot messages (including our own), edits and other subtypes.
    if event.get("bot_id") or event.get("subtype"):
        return

    message_text = event.get("text", "").strip()

    if not message_text:
        return

    channel_id = event.get("channel", "")
    slack_ts = event.get("ts", "")

    try:
        # 1. Classify.
        category, used_ai = classify_message(message_text)
        method = "Qwen" if used_ai else "keyword fallback"
        print(f"Classified as {category} ({method})")

        # 2. Save. Exact duplicates are not saved or notified again.
        saved, message_id = save_message(
            message=message_text,
            category=category,
            source="slack",
            channel_id=channel_id,
            slack_ts=slack_ts,
        )

        if not saved:
            print(
                f"Duplicate of message #{message_id}: "
                "already saved, so no new notification."
            )
            return

        print(f"New message classified: {category} ({method})")
        print("Message ID:", message_id)
        print("Channel ID:", channel_id)
        print("Message:", message_text)

        # 3. Extract structured data independently.
        # Extraction failures must not prevent notifications.
        try:
            structured_saved, structured_id, digest = (
                process_announcement(
                    message_text,
                    source="slack",
                    channel_id=channel_id,
                    slack_ts=slack_ts,
                    repository=announcement_repo,
                )
            )

            if structured_saved:
                print(
                    "Structured announcement saved:",
                    structured_id,
                    digest.announcement_type,
                )
            else:
                print("Duplicate structured announcement skipped.")

        except Exception:
            logger.exception(
                "Structured extraction failed; "
                "legacy message was saved."
            )

        # 4. Only notify for the tracked categories.
        style = NOTIFICATION_STYLES.get(category)

        if style is None:
            print("Category is Other: no notification needed.")
            return

        # 5. Summarize, then post ONE short notification.
        summary = summarize_message(message_text)
        print(f"Summary: {summary}")

        post_notification(channel_id, style, summary)

        print(f"{style['label']} notification posted.")

    except Exception:
        logger.exception("Failed to process or notify about message")


if __name__ == "__main__":
    print("CampusSignal is connecting to Slack...")
    print("Waiting for messages and notifications...")
    SocketModeHandler(slack_app, app_token).start()