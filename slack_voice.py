"""
slack_voice.py — Voice extension helper for Slack Bolt App.
Allows the Slack bot to upload synthesized audio directly to Slack channels.
"""

import os
from typing import Optional
from tts_kokoro import synthesize

def upload_voice_to_slack(
    client,
    channel_id: str,
    text: str,
    thread_ts: Optional[str] = None,
    speed: float = 1.25,
    title: str = "Announcement Audio Digest",
) -> bool:
    """
    Synthesize text using Kokoro (or offline fallback) and upload the audio
    file directly to the Slack channel / thread as a voice note.
    """
    if not client or not channel_id:
        return False

    temp_audio = "slack_voice_note.mp3"
    try:
        audio_path = synthesize(text, out_file=temp_audio, speed=speed)
        
        # Upload via Slack Bolt API
        client.files_upload_v2(
            channel=channel_id,
            thread_ts=thread_ts,
            file=audio_path,
            title=title,
            initial_comment=f"🔊 *Voice Note ({speed}× speed)*:\n> _{text[:100]}..._",
        )
        return True
    except Exception as e:
        print(f"[warn] Failed to upload audio to Slack channel {channel_id}: {e}")
        return False
    finally:
        if os.path.exists(temp_audio):
            try:
                os.remove(temp_audio)
            except OSError:
                pass
