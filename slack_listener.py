
import os
from dotenv import load_dotenv
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from campussignal_core import (
    init_db,
    classify_message,
    save_message
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


@slack_app.event("message")
def handle_message(event, logger):
    # Ignore messages sent by bots or message subtypes.
    if event.get("bot_id") or event.get("subtype"):
        return

    message_text = event.get("text", "").strip()

    if not message_text:
        return

    channel_id = event.get("channel", "")
    slack_ts = event.get("ts", "")

    try:
        # Classify the real Slack message using Qwen.
        category, used_ai = classify_message(message_text)

        # Save it in the same database used by Streamlit.
        saved, message_id = save_message(
            message=message_text,
            category=category,
            source="slack",
            channel_id=channel_id,
            slack_ts=slack_ts
        )

        if saved:
            method = "Qwen" if used_ai else "keyword fallback"

            print("\nNew Slack message processed!")
            print("Message ID:", message_id)
            print("Channel ID:", channel_id)
            print("Category:", category)
            print("Classifier:", method)
            print("Message:", message_text)

            # Do not let structured extraction failures undo or obscure
            # the legacy message that has already been saved.
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
        else:
            print("\nDuplicate message skipped.")
            print("Existing message ID:", message_id)
            print("Message:", message_text)

    except Exception:
        logger.exception("Failed to process a Slack message")


if __name__ == "__main__":
    print("CampusSignal is connecting to Slack...")
    print("Waiting for new messages...")
    SocketModeHandler(slack_app, app_token).start()
