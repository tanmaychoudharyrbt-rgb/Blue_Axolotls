from datetime import datetime, timedelta, timezone

from ai_pipeline.repository import AnnouncementRepository
from ai_pipeline.schema import AnnouncementDigest


def make_digest():
    return AnnouncementDigest(
        announcement_type="deadline",
        summary_title="Assignment submission",
        required_action="Submit your assignment",
        date_or_deadline="25 October 2026 at 6 PM",
        urgency_level="HIGH",
        ranking_reason="The deadline is approaching.",
        confidence_score=0.9,
        source_url="https://example.com/announcement",
    )


def test_save_and_read_announcement(tmp_path):
    repo = AnnouncementRepository(tmp_path / "test.db")
    repo.initialize()

    saved, announcement_id = repo.save(
        "Submit your assignment by 25 October 2026 at 6 PM.",
        make_digest(),
    )

    assert saved is True
    assert announcement_id is not None

    rows = repo.list_active()
    assert len(rows) == 1
    assert rows[0][3] == "Assignment submission"
    assert rows[0][6] == "HIGH"


def test_duplicate_message_is_not_saved_twice(tmp_path):
    repo = AnnouncementRepository(tmp_path / "test.db")
    repo.initialize()

    first = repo.save("Submit the assignment.", make_digest())
    second = repo.save("  Submit   the assignment.  ", make_digest())

    assert first[0] is True
    assert second[0] is False
    assert second[1] == first[1]
    assert len(repo.list_active()) == 1


def test_expiry_is_deadline_plus_24_hours(tmp_path):
    repo = AnnouncementRepository(tmp_path / "test.db")
    repo.initialize()

    received = datetime(2026, 10, 24, 12, tzinfo=timezone.utc)
    deadline = datetime(2026, 10, 25, 12, tzinfo=timezone.utc)

    repo.save(
        "Submit the assignment.",
        make_digest(),
        received_at=received,
        deadline_at=deadline,
    )

    assert repo.delete_expired(
        datetime(2026, 10, 26, 11, 59, 59, tzinfo=timezone.utc)
    ) == 0

    assert repo.delete_expired(
        datetime(2026, 10, 26, 12, tzinfo=timezone.utc)
    ) == 1

    assert repo.list_active() == []


def test_announcement_without_resolved_deadline_is_not_expired(
    tmp_path,
):
    repo = AnnouncementRepository(tmp_path / "test.db")
    repo.initialize()

    repo.save(
        "The library will remain open until 9 PM this week.",
        make_digest(),
    )

    removed = repo.delete_expired(
        datetime.now(timezone.utc) + timedelta(days=365)
    )

    assert removed == 0
    assert len(repo.list_active()) == 1


def test_list_active_excludes_expired_announcements(tmp_path):
    repo = AnnouncementRepository(tmp_path / "test.db")
    repo.initialize()

    deadline = datetime(
        2026, 10, 25, 12, tzinfo=timezone.utc
    )

    repo.save(
        "Submit the assignment by noon.",
        make_digest(),
        received_at=datetime(
            2026, 10, 24, 12, tzinfo=timezone.utc
        ),
        deadline_at=deadline,
    )

    repo.save(
        "Library announcement without a resolved deadline.",
        make_digest(),
        received_at=datetime(
            2026, 10, 24, 13, tzinfo=timezone.utc
        ),
    )

    rows = repo.list_active(
        datetime(2026, 10, 26, 12, 0, 1, tzinfo=timezone.utc)
    )

    assert len(rows) == 1
    assert rows[0][1] == (
        "Library announcement without a resolved deadline."
    )