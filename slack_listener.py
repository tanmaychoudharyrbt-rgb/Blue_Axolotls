
import os
from dotenv import load_dotenv
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

load_dotenv()

bot_token = os.getenv("SLACK_BOT_TOKEN")
app_token = os.getenv("SLACK_APP_TOKEN")

if not bot_token or not app_token:
    raise ValueError(
        "Slack tokens missing. Check your .env file."
    )

slack_app = App(token=bot_token)


@slack_app.event("message")
def handle_message(event, logger):
    # Ignore messages sent by bots, including our own.
    if event.get("bot_id") or event.get("subtype"):
        return

    message_text = event.get("text", "")
    channel_id = event.get("channel", "")
    user_id = event.get("user", "")

    print("\nNew Slack message received!")
    print("Channel:", channel_id)
    print("User:", user_id)
    print("Message:", message_text)


if __name__ == "__main__":
    print("CampusSignal is connecting to Slack...")
    SocketModeHandler(slack_app, app_token).start()
