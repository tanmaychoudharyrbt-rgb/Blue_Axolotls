import argparse
import json
from pathlib import Path

LEVEL_ICONS = {"HIGH": "🔴", "MEDIUM": "🟡", "LOW": "🟢"}

LABELS = {
    "en": {
        "header": "Your Slack digest",
        "action": "Action",
        "deadline": "Deadline",
        "why": "Why it matters",
        "source": "Source",
        "note": "Note",
        "none": "Not specified",
    },
    "hi": {
        "header": "आपका स्लैक डाइजेस्ट",
        "action": "कार्रवाई",
        "deadline": "समय सीमा",
        "why": "यह क्यों जरूरी है",
        "source": "स्रोत",
        "note": "नोट",
        "none": "निर्दिष्ट नहीं",
    },
    "mr": {
        "header": "तुमचा स्लॅक डायजेस्ट",
        "action": "कृती",
        "deadline": "मुदत",
        "why": "हे का महत्त्वाचे आहे",
        "source": "स्रोत",
        "note": "टीप",
        "none": "नमूद नाही",
    },
}


def pick(item, *keys):
    """Return the first non-empty value among the given keys, else None."""
    for key in keys:
        value = item.get(key)
        if value:
            return str(value).strip()
    return None


def format_item(number, item, labels):
    if not isinstance(item, dict):
        item = {"summary": str(item)}

    level = (pick(item, "urgency", "urgency_level", "priority") or "").upper()
    icon = LEVEL_ICONS.get(level, "⚪")
    level = level or "INFO"

    kind = pick(item, "type", "category")
    title = pick(item, "title")
    summary = pick(item, "summary")
    headline = title or summary or labels["none"]

    head = f"{number}. {icon} {level}"
    if kind:
        head += f" · {kind}"
    head += f" — {headline}"

    lines = [head]
    if title and summary and summary != title:
        lines.append(f"   {summary}")

    # Never invent: missing fields are shown as "Not specified"
    lines.append(f"   {labels['action']}: {pick(item, 'action', 'required_action') or labels['none']}")
    lines.append(f"   {labels['deadline']}: {pick(item, 'deadline', 'date') or labels['none']}")

    reason = pick(item, "urgency_reason", "reason")
    if reason:
        lines.append(f"   {labels['why']}: {reason}")

    lines.append(f"   {labels['source']}: {pick(item, 'source_url', 'source', 'link') or labels['none']}")

    note = pick(item, "note", "uncertainty", "uncertainty_note")
    if note:
        lines.append(f"   {labels['note']}: {note}")

    return "\n".join(lines)


def format_text_digest(payload, lang="en"):
    """Build the written digest (for Telegram or the terminal)."""
    labels = LABELS.get(lang, LABELS["en"])
    items = payload.get("ranked_summary", [])
    if isinstance(items, (str, dict)):
        items = [items]

    blocks = [labels["header"]]
    for i, item in enumerate(items, 1):
        blocks.append(format_item(i, item, labels))
    return "\n\n".join(blocks)


def main():
    parser = argparse.ArgumentParser(description="Format a text digest from JSON")
    parser.add_argument("input", help="JSON file with ranked_summary")
    parser.add_argument("--lang", default="en", choices=["en", "hi", "mr"])
    args = parser.parse_args()
    payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    print(format_text_digest(payload, args.lang))


if __name__ == "__main__":
    main()
