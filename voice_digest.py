"""
voice_digest.py — Kokoro-FastAPI TTS digest builder.

Changes from original (Piper):
  • tts.py  (Piper)  →  tts_kokoro.py  (Kokoro-FastAPI)
  • Speed range: 0.25x – 3.0x
  • Audio format: mp3 (Kokoro native)

NOTE: Calendar integration lives separately in the `calendar` branch.
      It will be merged into main at the end.
"""

import argparse
import json
from pathlib import Path

import yaml

from tts_kokoro import synthesize, check_kokoro_health
from digest_format import format_text_digest

CONFIG_PATH = Path("config.yaml")

PHRASES = {
    "en": {
        "intro":    "Here is your digest.",
        "ordinals": ["First", "Second", "Third", "Fourth", "Fifth"],
        "next":     "Next",
        "urgent":   "This is urgent because {reason}.",
        "short":    "In short, {reason}.",
    },
    "hi": {
        "intro":    "यह आपका आज का डाइजेस्ट है।",
        "ordinals": ["पहला", "दूसरा", "तीसरा", "चौथा", "पांचवां"],
        "next":     "अगला",
        "urgent":   "यह जरूरी है क्योंकि {reason}।",
        "short":    "संक्षेप में, {reason}।",
    },
    "mr": {
        "intro":    "हा तुमचा आजचा डायजेस्ट आहे.",
        "ordinals": ["पहिली", "दुसरी", "तिसरी", "चौथी", "पाचवी"],
        "next":     "पुढची",
        "urgent":   "हे महत्त्वाचे आहे कारण {reason}.",
        "short":    "थोडक्यात, {reason}.",
    },
}

DEMO_PAYLOADS = {
    "en": {
        "ranked_summary": [
            {
                "title":          "Lab report deadline",
                "type":           "Deadline",
                "urgency":        "high",
                "summary":        "Submit the lab report by 11 PM tonight.",
                "action":         "Upload the report on the course portal",
                "deadline":       "Today, 11 PM",
                "urgency_reason": "explicit deadline within 24 hours",
                "source_url":     "https://example.com/mock-slack/lab-report",
            },
            {
                "summary":        "Guest lecture on Friday is now in Hall B.",
                "urgency_reason": "the venue changed",
            },
            {
                "summary": "Cultural fest volunteer signup is open this week.",
            },
        ],
        "urgency_reason": "one deadline is due tonight",
    },
    "hi": {
        "ranked_summary": [
            {
                "summary":        "लैब रिपोर्ट जमा करने की अंतिम तारीख आज रात ग्यारह बजे है।",
                "urgency_reason": "समय सीमा बारह घंटे से कम में खत्म हो रही है",
            },
            {
                "summary":        "शुक्रवार का अतिथि व्याख्यान अब हॉल बी में होगा।",
                "urgency_reason": "स्थान बदल गया है",
            },
            {"summary": "सांस्कृतिक महोत्सव के लिए स्वयंसेवक पंजीकरण इस सप्ताह खुला है।"},
        ],
        "urgency_reason": "आज रात एक समय सीमा खत्म हो रही है",
    },
    "mr": {
        "ranked_summary": [
            {
                "summary":        "लॅब रिपोर्ट सादर करण्याची अंतिम मुदत आज रात्री अकरा वाजता आहे.",
                "urgency_reason": "मुदत बारा तासांपेक्षा कमी वेळात संपत आहे",
            },
            {
                "summary":        "शुक्रवारचे पाहुणे व्याख्यान आता हॉल बी मध्ये होईल.",
                "urgency_reason": "ठिकाण बदलले आहे",
            },
            {"summary": "सांस्कृतिक महोत्सवासाठी स्वयंसेवक नोंदणी या आठवड्यात सुरू आहे."},
        ],
        "urgency_reason": "आज रात्री एक मुदत संपत आहे",
    },
}

SENTENCE_ENDS = (".", "!", "?", "।")

# Kokoro voice IDs per language
KOKORO_VOICES = {
    "en": "af_heart",
    "hi": "af_heart",   # Kokoro doesn't have native Hindi yet; English voice used
    "mr": "af_heart",
}


def load_config(path=CONFIG_PATH):
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def build_spoken_text(payload, lang="en"):
    """Convert the ranked_summary JSON into natural spoken sentences."""
    p     = PHRASES.get(lang, PHRASES["en"])
    items = payload.get("ranked_summary", [])
    if isinstance(items, str):
        items = [items]

    parts = [p["intro"]]
    for i, item in enumerate(items):
        if isinstance(item, dict):
            summary = item.get("summary") or item.get("title") or ""
            reason  = item.get("urgency_reason")
        else:
            summary, reason = str(item), None

        summary = summary.lstrip("-*• ").strip()
        if not summary:
            continue
        if not summary.endswith(SENTENCE_ENDS):
            summary += "."

        label = p["ordinals"][i] if i < len(p["ordinals"]) else p["next"]
        line  = f"{label}: {summary}"
        if reason:
            line += " " + p["urgent"].format(reason=reason)
        parts.append(line)

    if payload.get("urgency_reason"):
        parts.append(p["short"].format(reason=payload["urgency_reason"]))
    return " ".join(parts)


def trim_to_duration(text, max_sec, speed):
    """Roughly 2.5 spoken words per second; cut at a sentence end."""
    max_words = int(2.5 * max_sec * speed)
    words     = text.split()
    if len(words) <= max_words:
        return text
    trimmed = " ".join(words[:max_words])
    last    = max(trimmed.rfind(c) for c in SENTENCE_ENDS)
    return trimmed[: last + 1] if last > 0 else trimmed


def make_digest(payload, prefs):
    """
    Returns:
        {
            "text":       <formatted text digest>,
            "spoken":     <raw spoken string>,
            "audio_path": <saved audio path or None>,
        }

    Calendar sync is intentionally NOT here — lives in the `calendar` branch.
    """
    lang   = prefs.get("preferred_language", "en")
    text   = build_spoken_text(payload, lang)
    result = {
        "text":       format_text_digest(payload, lang),
        "spoken":     text,
        "audio_path": None,
    }

    if prefs.get("digest_mode", "hybrid") == "text_only":
        return result

    if not check_kokoro_health():
        print(
            "[warn] Kokoro server not reachable — skipping audio.\n"
            "       Start Docker: docker run -p 8880:8880 ghcr.io/remsky/kokoro-fastapi-cpu:latest"
        )
        return result

    try:
        voice    = KOKORO_VOICES.get(lang, "af_heart")
        speed    = max(0.25, min(3.0, float(prefs.get("voice_speed", 1.0))))
        spoken   = trim_to_duration(text, prefs.get("max_duration_sec", 30), speed)
        fmt      = prefs.get("audio_format", "mp3")
        out_file = f"digest.{fmt}"
        result["audio_path"] = synthesize(
            spoken, voice=voice, out_file=out_file, speed=speed, fmt=fmt
        )
    except Exception as e:
        print(f"[warn] Kokoro TTS failed, falling back to text only: {e}")

    return result


def main():
    parser = argparse.ArgumentParser(description="Create a text + Kokoro voice digest")
    parser.add_argument("--input",  help="JSON file with ranked_summary / urgency_reason")
    parser.add_argument("--mode",   choices=["text_only", "voice_only", "hybrid"])
    parser.add_argument("--lang",   choices=["en", "hi", "mr"])
    parser.add_argument("--speed",  type=float,
                        help="Voice speed multiplier: 0.25 (slow) to 3.0 (fast)")
    parser.add_argument("--format", choices=["mp3", "wav", "ogg"])
    args = parser.parse_args()

    config = load_config()
    prefs  = config["user_preferences"]

    if args.mode:
        prefs["digest_mode"] = args.mode
    if args.lang:
        prefs["preferred_language"] = args.lang
    if args.speed:
        prefs["voice_speed"] = args.speed
    if args.format:
        prefs["audio_format"] = args.format

    payload = (
        json.loads(Path(args.input).read_text(encoding="utf-8"))
        if args.input
        else DEMO_PAYLOADS.get(prefs.get("preferred_language", "en"), DEMO_PAYLOADS["en"])
    )

    result = make_digest(payload, prefs)

    print("\n── TEXT DIGEST ─────────────────────────────────────────")
    print(result["text"])

    if result["audio_path"]:
        size_kb = Path(result["audio_path"]).stat().st_size / 1024
        print(f"\n── AUDIO ───────────────────────────────────────────────")
        print(f"   {result['audio_path']} ({size_kb:.0f} KB)")
    else:
        print("\n── AUDIO: none (text only or Kokoro unavailable) ───────")


if __name__ == "__main__":
    main()
