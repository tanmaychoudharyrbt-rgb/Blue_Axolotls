
from ai_pipeline.extractor import (
    extract_announcement,
    normalize_month_spacing,
)


def test_action_without_deadline():
    result = extract_announcement(
        "Please register for the hackathon."
    )

    assert result.announcement_type == "required_action"
    assert result.required_action == "Register for the hackathon"
    assert result.date_or_deadline == "Not specified"


def test_action_with_explicit_deadline():
    result = extract_announcement(
        "Submit your assignment by 25 October 2026 at 6 PM."
    )

    assert result.announcement_type == "deadline"
    assert result.required_action == "Submit your assignment"
    assert result.date_or_deadline == "25 October 2026 at 6 PM"


def test_schedule_change():
    result = extract_announcement(
        "The lecture has moved from Tuesday at 2 PM "
        "to Wednesday at 4 PM."
    )

    assert result.announcement_type == "schedule_change"
    assert result.date_or_deadline == "Wednesday at 4 PM"


def test_library_update():
    result = extract_announcement(
        "The library will remain open until 9 PM this week."
    )

    assert result.announcement_type == "general_update"
    assert result.required_action == "Not specified"
    assert result.date_or_deadline == "Not specified"


def test_month_spacing_normalization():
    assert normalize_month_spacing(
        "25October 2026 at 6 PM"
    ) == "25 October 2026 at 6 PM"
