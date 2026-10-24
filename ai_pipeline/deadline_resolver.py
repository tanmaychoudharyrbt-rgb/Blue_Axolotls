"""Resolve supported campus deadlines using the Asia/Kolkata timezone."""

import re
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from ai_pipeline.urgency import parse_datetime


CAMPUS_TIMEZONE = ZoneInfo("Asia/Kolkata")

WEEKDAYS = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}

TIME_PATTERN = (
    r"(?P<hour>0?[1-9]|1[0-2])"
    r"(?::(?P<minute>[0-5]\d))?\s*"
    r"(?P<ampm>AM|PM)\b"
)


def _reference_in_ist(
    reference_timestamp: str | datetime,
) -> datetime | None:
    """Convert a known reference timestamp to India Standard Time."""

    reference = parse_datetime(reference_timestamp)

    if reference is None:
        return None

    if reference.tzinfo is None:
        # The application's campus timestamps are interpreted as IST.
        reference = reference.replace(tzinfo=CAMPUS_TIMEZONE)

    return reference.astimezone(CAMPUS_TIMEZONE)


def _extract_time(text: str) -> tuple[time, str] | None:
    """Return a parsed 12-hour time and the text with that time removed."""

    match = re.search(TIME_PATTERN, text, re.IGNORECASE)

    if not match:
        return None

    hour = int(match.group("hour"))
    minute = int(match.group("minute") or 0)
    ampm = match.group("ampm").upper()

    if ampm == "AM":
        hour = 0 if hour == 12 else hour
    else:
        hour = 12 if hour == 12 else hour + 12

    parsed_time = time(hour, minute)
    remaining = (text[:match.start()] + " " + text[match.end():]).strip()
    remaining = re.sub(r"\s+", " ", remaining)

    # Remove a trailing "at" left behind by phrases such as
    # "tomorrow at 9 PM".
    remaining = re.sub(
        r"\s+\bat\b\s*$",
        "",
        remaining,
        flags=re.IGNORECASE,
    ).strip()

    return parsed_time, remaining


def resolve_deadline(
    value: str,
    reference_timestamp: str | datetime,
) -> datetime | None:
    """
    Resolve a supported deadline to a timezone-aware IST datetime.

    Unsupported or ambiguous phrases return None rather than guessing.
    """

    if not isinstance(value, str) or not value.strip():
        return None

    reference = _reference_in_ist(reference_timestamp)

    if reference is None:
        return None

    text = value.strip()

    # A date without a stated time is not a confirmed expiry time.
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        return None

    # First, try supported absolute dates.
    absolute = parse_datetime(text)

    if absolute is not None:
        if absolute.tzinfo is None:
            absolute = absolute.replace(tzinfo=CAMPUS_TIMEZONE)
        return absolute.astimezone(CAMPUS_TIMEZONE)

    # Separate a stated time from the relative-date phrase.
    extracted_time = _extract_time(text)

    if extracted_time is None:
        return None

    deadline_time, remaining = extracted_time
    phrase = remaining.lower().strip(" ,.")

    # Support common introductory words.
    phrase = re.sub(r"^(?:by|until|till|on)\s+", "", phrase)

    if phrase in {"today", "tonight"}:
        target_date = reference.date()

    elif phrase == "tomorrow":
        target_date = reference.date() + timedelta(days=1)

    elif phrase in {"this week", "end of this week"}:
        # Explicit project policy: "this week" means Sunday.
        days_until_sunday = (6 - reference.weekday()) % 7
        target_date = reference.date() + timedelta(
            days=days_until_sunday
        )

    else:
        # Weekday names: choose the next occurrence. If today is
        # that weekday and the specified time has passed, use next week.
        weekday_match = re.fullmatch(
            r"(?:this\s+)?(monday|tuesday|wednesday|thursday|"
            r"friday|saturday|sunday)",
            phrase,
        )

        if weekday_match is None:
            return None

        target_weekday = WEEKDAYS[weekday_match.group(1)]
        days_ahead = (target_weekday - reference.weekday()) % 7
        target_date = reference.date() + timedelta(days=days_ahead)

        candidate = datetime.combine(
            target_date, deadline_time, tzinfo=CAMPUS_TIMEZONE
        )

        if candidate <= reference:
            target_date += timedelta(days=7)

    return datetime.combine(
        target_date,
        deadline_time,
        tzinfo=CAMPUS_TIMEZONE,
    )
