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
    save_message
)

load_dotenv()

bot_token = os.getenv("SLACK_BOT_TOKEN")
app_token = os.getenv("SLACK_APP_TOKEN")

if not bot_token or not app_token:
    raise ValueError("Slack tokens missing. Check your .env file.")

init_db()
slack_app = App(token=bot_token)

# Only these categories trigger a notification ("Other" is ignored).
NOTIFICATION_STYLES = {
    "🚨 Urgent": {
        "label": "🔴 URGENT",
        "color": "#E01E5A"
    },
    "📝 Exam Alert": {
        "label": "🟠 EXAM ALERT",
        "color": "#F28C28"
    },
    "📚 Academic": {
        "label": "🔵 ACADEMIC",
        "color": "#1264A3"
    },
    "🎉 Event": {
        "label": "🟢 EVENT",
        "color": "#2BAC76"
    }
}


def summarize_message(message):
    """Summarize with local Qwen. Falls back to the original message."""

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
        # Qwen3 "thinks" by default, which is slow and can exceed the
        # timeout. Turn it off so the summary comes back quickly.
        "think": False,
        "keep_alive": "10m",
        "messages": [{"role": "user", "content": prompt}],
        "options": {
            "temperature": 0.2,
            "num_predict": 150
        }
    }

    request = urllib.request.Request(
        "http://localhost:11434/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            result = json.loads(response.read().decode("utf-8"))

        summary = result.get("message", {}).get("content", "")

        # Remove any leaked reasoning block.
        summary = re.sub(
            r"<think>.*?</think>", "", summary, flags=re.DOTALL
        ).strip()

        if summary:
            return summary

    except Exception as error:
        print(f"Summarization failed, using original text: {error}")

    return message


def build_notification(style, summary):
    """Build the attachment: coloured sidebar, label, then summary."""

    text = f"*{style['label']}*\n{summary}"

    return {
        "color": style["color"],
        "fallback": f"{style['label']} — {summary}",
        "blocks": [
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": text}
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": "_Classified and summarized by CampusSignal_"
                    }
                ]
            }
        ]
    }


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
            slack_ts=slack_ts
        )

        if not saved:
            print(
                f"Duplicate of message #{message_id}: "
                "already saved, so no new notification."
            )
            return

        # 3. "Other" messages get no notification.
        style = NOTIFICATION_STYLES.get(category)

        if style is None:
            print("Category is Other: no notification needed.")
            return

        # 4. Summarize, then post ONE coloured notification.
        summary = summarize_message(message_text)
        print(f"Summary: {summary}")

        # No top-level `text`: Slack would show it as a second, plain
        # copy above the coloured card. `fallback` covers push
        # notifications and clients that can't render attachments.
        slack_app.client.chat_postMessage(
            channel=channel_id,
            attachments=[build_notification(style, summary)],
            unfurl_links=False,
            unfurl_media=False
        )

        print(f"{style['label']} notification posted.")

    except Exception:
        logger.exception("Failed to process or notify about message")


if __name__ == "__main__":
    print("CampusSignal is connecting to Slack...")
    print("Waiting for messages and notifications...")
    SocketModeHandler(slack_app, app_token).start()