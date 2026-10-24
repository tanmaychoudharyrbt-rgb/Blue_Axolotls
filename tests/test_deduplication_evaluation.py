
import json
from collections import defaultdict
from pathlib import Path

from ai_pipeline.deduplication import (
    AnnouncementRecord,
    deduplicate_announcements,
)


ROOT = Path(__file__).resolve().parents[1]
DATASET_PATH = ROOT / "data" / "evaluation" / "announcements.json"

EXPECTED_DUPLICATE_GROUPS = {
    "CAFETERIA_HOURS",
    "CAMPUS_SHUTTLE",
    "CODING_ORIENTATION",
    "HELP_DESK_LOCATION",
    "LIBRARY_HOURS",
}


def test_all_labelled_duplicate_pairs_are_grouped():
    records = json.loads(DATASET_PATH.read_text(encoding="utf-8"))

    labelled_groups = defaultdict(list)

    for record in records:
        group_label = record.get("duplicate_group")
        if group_label:
            labelled_groups[group_label].append(record)

    assert set(labelled_groups) == EXPECTED_DUPLICATE_GROUPS

    for label, pair in labelled_groups.items():
        assert len(pair) == 2, (
            f"{label} should contain exactly two labelled records"
        )

        announcements = [
            AnnouncementRecord(
                text=record["text"],
                source_url=record.get("source_url", ""),
                timestamp=record.get("timestamp", ""),
                channel_id=record.get("channel_id", ""),
            )
            for record in pair
        ]

        groups = deduplicate_announcements(announcements)

        assert len(groups) == 1, (
            f"{label}: expected both labelled records to be grouped"
        )

        assert len(groups[0].duplicates) == 1, (
            f"{label}: expected exactly one duplicate"
        )
