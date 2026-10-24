from datetime import datetime
from zoneinfo import ZoneInfo

from ai_pipeline.deadline_resolver import resolve_deadline


IST = ZoneInfo("Asia/Kolkata")
REFERENCE = datetime(2026, 10, 25, 12, 0, tzinfo=IST)


def test_resolves_tomorrow_at_nine_pm():
    result = resolve_deadline("tomorrow at 9 PM", REFERENCE)

    assert result == datetime(2026, 10, 26, 21, 0, tzinfo=IST)


def test_resolves_friday_deadline():
    result = resolve_deadline("by Friday at 5 PM", REFERENCE)

    # 25 October 2026 is Sunday; the next Friday is 30 October.
    assert result == datetime(2026, 10, 30, 17, 0, tzinfo=IST)


def test_resolves_this_week_using_sunday_policy():
    result = resolve_deadline("until 9 PM this week", REFERENCE)

    assert result == datetime(2026, 10, 25, 21, 0, tzinfo=IST)


def test_resolves_absolute_date_in_ist():
    result = resolve_deadline(
        "26 October 2026 at 6:30 PM",
        REFERENCE,
    )

    assert result == datetime(2026, 10, 26, 18, 30, tzinfo=IST)


def test_ambiguous_phrase_is_not_guessed():
    result = resolve_deadline("sometime this week", REFERENCE)

    assert result is None


def test_missing_reference_is_not_guessed():
    result = resolve_deadline("tomorrow at 9 PM", "not a timestamp")

    assert result is None


def test_naive_reference_is_interpreted_as_ist():
    result = resolve_deadline(
        "tomorrow at 9 PM",
        "2026-10-25T12:00:00",
    )

    assert result == datetime(2026, 10, 26, 21, 0, tzinfo=IST)
