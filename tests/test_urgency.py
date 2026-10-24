
from ai_pipeline.schema import AnnouncementDigest
from ai_pipeline.urgency import rank_urgency


def make_announcement(
    announcement_type="deadline",
    date_or_deadline="25 October 2026 at 6 PM",
):
    return AnnouncementDigest(
        announcement_type=announcement_type,
        summary_title="Assignment submission",
        required_action="Submit the assignment",
        date_or_deadline=date_or_deadline,
        urgency_level="LOW",
        ranking_reason="Initial classification.",
        confidence_score=0.9,
        source_url="https://example.com/announcement",
    )


def test_deadline_within_24_hours_is_high():
    result = rank_urgency(
        make_announcement(),
        "2026-10-25T00:00:00",
    )

    assert result.urgency_level == "HIGH"
    assert "less than 24 hours" in result.ranking_reason


def test_deadline_between_24_and_48_hours_is_medium():
    result = rank_urgency(
        make_announcement(),
        "2026-10-24T00:00:00",
    )

    assert result.urgency_level == "MEDIUM"
    assert "24 but less than 48 hours" in result.ranking_reason


def test_deadline_at_least_48_hours_away_is_low():
    result = rank_urgency(
        make_announcement(),
        "2026-10-22T00:00:00",
    )

    assert result.urgency_level == "LOW"
    assert "at least 48 hours" in result.ranking_reason


def test_missing_reference_timestamp_does_not_guess():
    result = rank_urgency(make_announcement())

    assert result.urgency_level == "LOW"
    assert "cannot be established" in result.ranking_reason


def test_missing_deadline_is_low():
    result = rank_urgency(
        make_announcement(date_or_deadline="Not specified"),
        "2026-10-24T00:00:00",
    )

    assert result.urgency_level == "LOW"


def test_general_update_is_not_deadline_urgent():
    result = rank_urgency(
        make_announcement(
            announcement_type="general_update",
            date_or_deadline="Not specified",
        ),
        "2026-10-24T00:00:00",
    )

    assert result.urgency_level == "LOW"


def test_invalid_deadline_does_not_guess():
    result = rank_urgency(
        make_announcement(date_or_deadline="sometime next week"),
        "2026-10-24T00:00:00",
    )

    assert result.urgency_level == "LOW"
    assert "cannot be established" in result.ranking_reason


def test_timezone_mismatch_does_not_guess():
    result = rank_urgency(
        make_announcement(),
        "2026-10-25T00:00:00+00:00",
    )

    assert result.urgency_level == "LOW"
    assert "timezone" in result.ranking_reason
