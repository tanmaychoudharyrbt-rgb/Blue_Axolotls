cat > voice_digest.py << 'EOF'
import argparse
import json
from pathlib import Path

import yaml

from tts import synthesize

CONFIG_PATH = Path("config.yaml")
ORDINALS = ["First", "Second", "Third", "Fourth", "Fifth"]

DEMO_PAYLOAD = {
    "ranked_summary": [
        {"summary": "Lab report submission moved to tonight 11 PM.",
         "urgency_reason": "the deadline is within 12 hours"},
        {"summary": "Guest lecture on Friday is now in Hall B.",
         "urgency_reason": "the venue changed"},
        {"summary": "Cultural fest volunteer signup is open this week."},
    ],
    "urgency_reason": "one deadline is due tonight",
}


def load_config(path=CONFIG_PATH):
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def build_spoken_text(payload):
    """Convert the ranked_summary JSON into natural spoken sentences."""
    items = payload.get("ranked_summary", [])
    if isinstance(items, str):
        items = [items]

    parts = ["Here is your digest."]
    for i, item in enumerate(items):
        if isinstance(item, dict):
            summary = item.get("summary") or item.get("title") or ""
            reason = item.get("urgency_reason")
        else:
            summary, reason = str(item), None

        summary = summary.lstrip("-*• ").strip()
        if not summary:
            continue
        if not summary.endswith((".", "!", "?")):
            summary += "."

        label = ORDINALS[i] if i < len(ORDINALS) else "Next"
        line = f"{label}: {summary}"
        if reason:
            line += f" This is urgent because {reason}."
        parts.append(line)

    if payload.get("urgency_reason"):
        parts.append(f"In short, {payload['urgency_reason']}.")
    return " ".join(parts)


def trim_to_duration(text, max_sec, speed):
    """Roughly 2.5 spoken words per second; cut at a sentence end."""
    max_words = int(2.5 * max_sec * speed)
    words = text.split()
    if len(words) <= max_words:
        return text
    trimmed = " ".join(words[:max_words])
    last = max(trimmed.rfind("."), trimmed.rfind("!"), trimmed.rfind("?"))
    return trimmed[: last + 1] if last > 0 else trimmed


def make_digest(payload, prefs, voices):
    """Returns {"text": ..., "audio_path": ... or None}."""
    text = build_spoken_text(payload)
    result = {"text": text, "audio_path": None}

    if prefs["digest_mode"] == "text_only":
        return result

    try:
        voice = voices[prefs["preferred_language"]]
        spoken = trim_to_duration(text, prefs["max_duration_sec"], prefs["voice_speed"])
        out_file = f"digest.{prefs['audio_format']}"
        result["audio_path"] = synthesize(
            spoken, voice=voice, out_file=out_file, speed=prefs["voice_speed"]
        )
    except Exception as e:
        print(f"[warn] Audio failed, falling back to text only: {e}")
    return result


def main():
    parser = argparse.ArgumentParser(description="Create a text + voice digest")
    parser.add_argument("--input", help="JSON file with ranked_summary / urgency_reason")
    parser.add_argument("--mode", choices=["text_only", "voice_only", "hybrid"])
    parser.add_argument("--lang", choices=["en", "hi", "mr"])
    parser.add_argument("--speed", type=float)
    parser.add_argument("--format", choices=["ogg", "wav"])
    args = parser.parse_args()

    config = load_config()
    prefs = config["user_preferences"]
    voices = config["voices"]

    # CLI flags override config.yaml (handy for live demos)
    if args.mode:
        prefs["digest_mode"] = args.mode
    if args.lang:
        prefs["preferred_language"] = args.lang
    if args.speed:
        prefs["voice_speed"] = args.speed
    if args.format:
        prefs["audio_format"] = args.format

    if args.input:
        payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    else:
        payload = DEMO_PAYLOAD

    result = make_digest(payload, prefs, voices)
    print("\nTEXT DIGEST:\n" + result["text"])
    if result["audio_path"]:
        size_kb = Path(result["audio_path"]).stat().st_size / 1024
        print(f"\nAUDIO: {result['audio_path']} ({size_kb:.0f} KB)")
    else:
        print("\nAUDIO: none (text only)")


if __name__ == "__main__":
    main()
