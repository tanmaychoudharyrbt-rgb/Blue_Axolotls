
import os
import json
import urllib.request

from dotenv import load_dotenv
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from campussignal_core import (
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

MODEL = "qwen3:4b"

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


def summarize_message(message):
    """Summarize a Slack message using local Qwen through Ollama."""

    prompt = f"""
Summarize this college Slack message into its most important information.

Rules:
- Use 1-2 short sentences.
- Preserve important facts, dates, times, locations and deadlines.
- Do not invent information or change the meaning.
- For exam notices, clearly state the exam and any date or change.
- For urgent notices, clearly state the issue and required action.
- Remove greetings, repetition and unnecessary details.
- Return only the summary.

Message:
{message}
"""

    payload = {
        "model": MODEL,
        "stream": False,
        "messages": [
            {
                "role": "user",
                "content": prompt,
            }
        ],
        "options": {
            "temperature": 0.2,
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

        summary = result.get("message", {}).get("content", "").strip()

        if summary:
            return summary

    except Exception as error:
        print(f"Summarization failed: {error}")

    # Keep notifications working if Ollama is unavailable.
    return message


@slack_app.event("message")
def handle_message(event, logger):
    # Ignore bot messages, edits, and other message subtypes.
    if event.get("bot_id") or event.get("subtype"):
        return

    message_text = event.get("text", "").strip()

    if not message_text:
        return

    channel_id = event.get("channel", "")
    slack_ts = event.get("ts", "")

    try:
        # 1. Preserve the existing classification workflow.
        category, used_ai = classify_message(message_text)

        # 2. Save the legacy message and skip exact duplicates.
        saved, message_id = save_message(
            message=message_text,
            category=category,
            source="slack",
            channel_id=channel_id,
            slack_ts=slack_ts,
        )

        if not saved:
            print(f"Duplicate skipped: message #{message_id}")
            return

        method = "Qwen" if used_ai else "keyword fallback"

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

        # 4. Preserve the existing notification category rules.
        style = NOTIFICATION_STYLES.get(category)

        if style is None:
            print("No notification needed.")
            return

        # 5. Summarize notifications with local Qwen.
        summary = summarize_message(message_text)
        print("Summary:", summary)

        # 6. Post the category and summary in the original channel.
        notification_text = (
            f"*{style['label']}*\n"
            f"{summary}\n\n"
            "_Summarized by CampusSignal._"
        )

        slack_app.client.chat_postMessage(
            channel=channel_id,
            text=f"{style['label']} — {summary}",
            attachments=[
                {
                    "color": style["color"],
                    "fallback": f"{style['label']} — {summary}",
                    "text": notification_text,
                    "mrkdwn_in": ["text"],
                }
            ],
            unfurl_links=False,
            unfurl_media=False,
        )

        print(f"{style['label']} summary posted!")

    except Exception:
        logger.exception("Failed to process or notify about message")


if __name__ == "__main__":
    print("CampusSignal is connecting to Slack...")
    print("Waiting for messages and notifications...")
    SocketModeHandler(slack_app, app_token).start()
