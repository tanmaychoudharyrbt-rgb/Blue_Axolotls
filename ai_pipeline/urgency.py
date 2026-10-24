
import re
from datetime import datetime, timedelta, timezone

from ai_pipeline.schema import AnnouncementDigest


DEADLINE_FORMATS = (
    "%d %B %Y at %I:%M %p",
    "%d %B %Y at %I %p",
    "%d %b %Y at %I:%M %p",
    "%d %b %Y at %I %p",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%d",
)


def parse_datetime(value: str | datetime) -> datetime | None:
    """Parse a supported timestamp without guessing missing information."""

    if isinstance(value, datetime):
        return value

    if not isinstance(value, str) or not value.strip():
        return None

    value = value.strip()

    # Support ISO timestamps, including a trailing Z for UTC.
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        pass

    # Normalize common spacing mistakes, such as "at6 PM".
    value = re.sub(r"\bat\s*(?=\d)", "at ", value, flags=re.IGNORECASE)
    value = re.sub(r"\s+", " ", value)

    for date_format in DEADLINE_FORMATS:
        try:
            return datetime.strptime(value, date_format)
        except ValueError:
            continue

    return None


def rank_urgency(
    announcement: AnnouncementDigest,
    reference_timestamp: str | datetime | None = None,
) -> AnnouncementDigest:
    """
    Return a validated digest with urgency based on an explicit deadline.

    HIGH: deadline is less than 24 hours away.
    MEDIUM: deadline is at least 24 but less than 48 hours away.
    LOW: no imminent deadline is established.
    """

    # Only deadline announcements are ranked by deadline proximity.
    if announcement.announcement_type != "deadline":
        return announcement.model_copy(
            update={
                "urgency_level": "LOW",
                "ranking_reason": (
                    "No explicit deadline announcement was identified, "
                    "so imminent deadline urgency is not established."
                ),
            }
        )

    deadline_text = announcement.date_or_deadline

    if deadline_text == "Not specified":
        return announcement.model_copy(
            update={
                "urgency_level": "LOW",
                "ranking_reason": (
                    "No explicit deadline is available, so its "
                    "proximity cannot be established."
                ),
            }
        )

    deadline = parse_datetime(deadline_text)
    reference = (
        parse_datetime(reference_timestamp)
        if reference_timestamp is not None
        else None
    )

    if deadline is None or reference is None:
        return announcement.model_copy(
            update={
                "urgency_level": "LOW",
                "ranking_reason": (
                    "The deadline or reference timestamp is missing "
                    "or unsupported, so imminent urgency cannot "
                    "be established safely."
                ),
            }
        )

    # Comparing a timezone-aware timestamp with a timezone-naive
    # timestamp would be ambiguous. Do not guess the timezone.
    if (deadline.tzinfo is None) != (reference.tzinfo is None):
        return announcement.model_copy(
            update={
                "urgency_level": "LOW",
                "ranking_reason": (
                    "The deadline and reference timestamp have "
                    "incompatible timezone information."
                ),
            }
        )

    # Normalize two timezone-aware values to UTC before comparison.
    if deadline.tzinfo is not None:
        deadline = deadline.astimezone(timezone.utc)
        reference = reference.astimezone(timezone.utc)

    time_remaining = deadline - reference

    if time_remaining <= timedelta(0):
        urgency = "LOW"
        reason = "The stated deadline has already passed."
    elif time_remaining < timedelta(hours=24):
        urgency = "HIGH"
        reason = (
            "The stated deadline is less than 24 hours away."
        )
    elif time_remaining < timedelta(hours=48):
        urgency = "MEDIUM"
        reason = (
            "The stated deadline is at least 24 but less than "
            "48 hours away."
        )
    else:
        urgency = "LOW"
        reason = (
            "The stated deadline is at least 48 hours away."
        )

    return announcement.model_copy(
        update={
            "urgency_level": urgency,
            "ranking_reason": reason,
        }
    )
