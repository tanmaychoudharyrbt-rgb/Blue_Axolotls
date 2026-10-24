
from ai_pipeline.deduplication import (
    AnnouncementRecord,
    deduplicate_announcements,
    jaccard_similarity,
)


def test_identical_messages_have_similarity_one():
    assert jaccard_similarity(
        "Submit the assignment by Friday",
        "Submit the assignment by Friday",
    ) == 1.0


def test_completely_different_messages_have_similarity_zero():
    assert jaccard_similarity(
        "Submit your assignment",
        "Library closes early",
    ) == 0.0


def test_similar_announcements_are_grouped():
    records = [
        AnnouncementRecord(
            text="Submit the assignment by Friday",
            source_url="https://example.com/first",
            timestamp="2026-10-20T10:00:00",
        ),
        AnnouncementRecord(
            text="Submit the assignment by Friday!",
            source_url="https://example.com/second",
            timestamp="2026-10-20T11:00:00",
        ),
    ]

    groups = deduplicate_announcements(records)

    assert len(groups) == 1
    assert len(groups[0].duplicates) == 1


def test_earliest_source_is_retained():
    records = [
        AnnouncementRecord(
            text="Submit assignment by Friday",
            source_url="https://example.com/later",
            timestamp="2026-10-20T11:00:00",
        ),
        AnnouncementRecord(
            text="Submit assignment by Friday",
            source_url="https://example.com/earlier",
            timestamp="2026-10-20T10:00:00",
        ),
    ]

    groups = deduplicate_announcements(records)

    assert groups[0].representative.source_url == (
        "https://example.com/earlier"
    )


def test_dissimilar_messages_remain_separate():
    records = [
        AnnouncementRecord(text="Submit the assignment"),
        AnnouncementRecord(text="Library closes at nine"),
    ]

    groups = deduplicate_announcements(records)

    assert len(groups) == 2


def test_empty_messages_are_not_grouped():
    records = [
        AnnouncementRecord(text=""),
        AnnouncementRecord(text=""),
    ]

    groups = deduplicate_announcements(records)

    assert len(groups) == 2


def test_custom_threshold_is_supported():
    records = [
        AnnouncementRecord(text="Submit assignment Friday"),
        AnnouncementRecord(text="Submit assignment Monday"),
    ]

    groups = deduplicate_announcements(records, threshold=0.5)

    assert len(groups) == 1


def test_invalid_threshold_is_rejected():
    try:
        deduplicate_announcements([], threshold=1.5)
    except ValueError:
        pass
    else:
        raise AssertionError("An invalid threshold should be rejected.")
