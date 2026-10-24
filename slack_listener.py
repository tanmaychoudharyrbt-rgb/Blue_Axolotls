
import os
from dotenv import load_dotenv
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from campussignal_core import (
    init_db,
    classify_message,
    save_message
)

load_dotenv()

bot_token = os.getenv("SLACK_BOT_TOKEN")
app_token = os.getenv("SLACK_APP_TOKEN")

if not bot_token or not app_token:
    raise ValueError(
        "Slack tokens missing. Check your .env file."
    )

# Make sure the shared database exists.
init_db()

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
