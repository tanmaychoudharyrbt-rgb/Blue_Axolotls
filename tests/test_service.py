from datetime import datetime, timezone

import pytest

from ai_pipeline.repository import AnnouncementRepository
from ai_pipeline.schema import AnnouncementDigest
from ai_pipeline.service import process_announcement


def make_digest(
    announcement_type="deadline",
    date_or_deadline="2026-10-25T18:00:00+05:30",
):
    return AnnouncementDigest(
        announcement_type=announcement_type,
        summary_title="Campus announcement",
        required_action="Submit the form",
        date_or_deadline=date_or_deadline,
        urgency_level="MEDIUM",
        ranking_reason="Test announcement.",
        confidence_score=0.9,
        source_url="",
    )


def test_slack_deadline_uses_original_message_timestamp(tmp_path):
    repo = AnnouncementRepository(tmp_path / "service.db")
    received = datetime(2026, 10, 24, 13, tzinfo=timezone.utc)
    original = datetime(2026, 10, 24, 12, tzinfo=timezone.utc)
    captured = {}

    def fake_extractor(message, **kwargs):
        captured.update(kwargs)
        return make_digest()

    saved, row_id, digest = process_announcement(
        "Submit the form by tomorrow at 6 PM.",
        source="slack",
        channel_id="C_TEST",
        slack_ts=str(original.timestamp()),
        received_at=received,
        repository=repo,
        extractor_fn=fake_extractor,
    )

    assert saved is True
    assert row_id is not None
    assert captured["reference_timestamp"] == original.isoformat()

    rows = repo.list_active(received)
    assert len(rows) == 1
    assert rows[0][10] == "slack"
    assert rows[0][11] == "C_TEST"


def test_schedule_change_does_not_receive_expiry(tmp_path):
    repo = AnnouncementRepository(tmp_path / "schedule.db")

    def fake_extractor(message, **kwargs):
        return make_digest(
            announcement_type="schedule_change",
            date_or_deadline="2026-10-25T18:00:00+05:30",
        )

    saved, _, _ = process_announcement(
        "The lecture has been postponed until tomorrow at 6 PM.",
        source="dashboard",
        received_at=datetime(2026, 10, 24, 12, tzinfo=timezone.utc),
        repository=repo,
        extractor_fn=fake_extractor,
    )

    assert saved is True

    with repo._connect() as conn:
        row = conn.execute(
            "SELECT deadline_at, expires_at FROM structured_announcements"
        ).fetchone()

    assert row == (None, None)


def test_invalid_slack_timestamp_does_not_guess_expiry(tmp_path):
    repo = AnnouncementRepository(tmp_path / "invalid_ts.db")
    captured = {}

    def fake_extractor(message, **kwargs):
        captured.update(kwargs)
        return make_digest()

    process_announcement(
        "Submit the form by tomorrow at 6 PM.",
        source="slack",
        slack_ts="not-a-timestamp",
        received_at=datetime(2026, 10, 24, 12, tzinfo=timezone.utc),
        repository=repo,
        extractor_fn=fake_extractor,
    )

    assert captured["reference_timestamp"] is None

    with repo._connect() as conn:
        row = conn.execute(
            "SELECT deadline_at, expires_at FROM structured_announcements"
        ).fetchone()

    assert row == (None, None)


def test_extraction_failure_propagates_to_caller(tmp_path):
    repo = AnnouncementRepository(tmp_path / "failure.db")

    def failing_extractor(message, **kwargs):
        raise RuntimeError("Extractor unavailable")

    with pytest.raises(RuntimeError, match="Extractor unavailable"):
        process_announcement(
            "Submit the form.",
            received_at=datetime(2026, 10, 24, 12, tzinfo=timezone.utc),
            repository=repo,
            extractor_fn=failing_extractor,
        )


def test_date_only_deadline_is_not_resolved():
    from ai_pipeline.deadline_resolver import resolve_deadline

    result = resolve_deadline(
        "2026-10-25",
        "2026-10-24T12:00:00+05:30",
    )

    assert result is None
