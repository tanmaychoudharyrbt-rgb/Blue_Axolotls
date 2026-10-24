
import os
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
    raise ValueError(
        "Slack tokens missing. Check your .env file."
    )

# Keep legacy and structured data in the same database file,
# but in separate tables.
init_db()

announcement_repo = AnnouncementRepository()
announcement_repo.initialize()
announcement_repo.delete_expired()

slack_app = App(token=bot_token)


# Categories that trigger notifications.
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
        # 1. Classify the incoming message using the existing classifier.
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

        # 3. Extract and save structured data independently.
        # A structured extraction failure must not prevent notifications.
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
                "legacy Slack message was saved."
            )

        # 4. Preserve the existing notification rules.
        style = NOTIFICATION_STYLES.get(category)

        if style is None:
            print("No notification needed.")
            return

        # 5. Put the category first in the notification.
        notification_text = (
            f"*{style['label']}*\n"
            f"{message_text}\n\n"
            "_Automatically classified by CampusSignal._"
        )

        # 6. Send a Slack message with a colored sidebar.
        slack_app.client.chat_postMessage(
            channel=channel_id,
            text=f"{style['label']} — {message_text}",
            attachments=[
                {
                    "color": style["color"],
                    "fallback": f"{style['label']} — {message_text}",
                    "text": notification_text,
                    "mrkdwn_in": ["text"],
                }
            ],
            unfurl_links=False,
            unfurl_media=False,
        )

        print(f"{style['label']} notification sent!")

    except Exception:
        logger.exception("Failed to process or notify about message")


if __name__ == "__main__":
    print("CampusSignal is connecting to Slack...")
    print("Waiting for messages and notifications...")
    SocketModeHandler(slack_app, app_token).start()
