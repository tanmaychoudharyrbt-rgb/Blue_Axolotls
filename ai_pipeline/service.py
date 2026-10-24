"""Integration service for structured campus announcements."""

from datetime import datetime, timezone

from ai_pipeline.deadline_resolver import resolve_deadline
from ai_pipeline.extractor import extract_announcement
from ai_pipeline.repository import AnnouncementRepository
from ai_pipeline.schema import AnnouncementDigest


def slack_timestamp_to_datetime(
    slack_ts: str | None,
) -> datetime | None:
    """Convert Slack's epoch timestamp to an aware UTC datetime."""
    if not slack_ts:
        return None

    try:
        return datetime.fromtimestamp(float(slack_ts), tz=timezone.utc)
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def process_announcement(
    message: str,
    *,
    source: str = "dashboard",
    channel_id: str | None = None,
    slack_ts: str | None = None,
    source_url: str = "",
    received_at: datetime | None = None,
    repository: AnnouncementRepository | None = None,
    extractor_fn=None,
) -> tuple[bool, int | None, AnnouncementDigest]:
    """
    Extract and store a structured announcement.

    This function does not modify the legacy messages table.
    Only a confirmed, resolvable deadline receives an expiry time.
    Extraction and database errors are allowed to propagate so the
    caller can log them without disrupting legacy message storage.
    """
    if not message or not message.strip():
        raise ValueError("Message cannot be empty.")

    received_at = received_at or datetime.now(timezone.utc)

    if received_at.tzinfo is None:
        raise ValueError("received_at must include timezone information.")

    # Slack messages must use their original timestamp. If it is missing
    # or invalid, do not substitute the processing time and guess.
    if source == "slack":
        reference = slack_timestamp_to_datetime(slack_ts)
    else:
        reference = received_at

    reference_timestamp = (
        reference.isoformat() if reference is not None else None
    )

    if extractor_fn is None:
        extractor_fn = extract_announcement

    digest = extractor_fn(
        message.strip(),
        source_url=source_url,
        reference_timestamp=reference_timestamp,
    )

    deadline_at = None

    # A schedule change is not automatically a task deadline.
    if (
        digest.announcement_type == "deadline"
        and reference_timestamp is not None
        and digest.date_or_deadline != "Not specified"
    ):
        deadline_at = resolve_deadline(
            digest.date_or_deadline,
            reference_timestamp,
        )

    repo = repository or AnnouncementRepository()
    repo.initialize()

    saved, announcement_id = repo.save(
        message.strip(),
        digest,
        received_at=received_at,
        deadline_at=deadline_at,
        source=source,
        channel_id=channel_id,
        slack_ts=slack_ts,
    )

    return saved, announcement_id, digest
