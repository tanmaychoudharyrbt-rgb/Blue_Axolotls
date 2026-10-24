
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime

SIMILARITY_THRESHOLD = 0.75


@dataclass
class AnnouncementRecord:
    """One raw announcement and its source metadata."""

    text: str
    source_url: str = ""
    timestamp: str = ""
    channel_id: str = ""


@dataclass
class DuplicateGroup:
    """A representative announcement and its repeated messages."""

    representative: AnnouncementRecord
    duplicates: list[AnnouncementRecord]
    similarity_scores: list[float]


def normalize_text(text: str) -> str:
    """Normalize text before comparing announcements."""

    text = text.lower()
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return " ".join(text.split())


def token_set(text: str) -> set[str]:
    """Convert normalized text into unique word tokens."""

    return set(normalize_text(text).split())


def jaccard_similarity(first: str, second: str) -> float:
    """Calculate word-set Jaccard similarity between two messages."""

    first_tokens = token_set(first)
    second_tokens = token_set(second)

    if not first_tokens or not second_tokens:
        return 0.0

    intersection = first_tokens & second_tokens
    union = first_tokens | second_tokens

    return len(intersection) / len(union)


def parse_timestamp(value: str) -> datetime | None:
    """Parse an ISO timestamp; return None when unavailable or invalid."""

    if not value:
        return None

    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def earliest_record(
    records: list[AnnouncementRecord],
) -> AnnouncementRecord:
    """
    Pick the earliest timestamp when all timestamps are comparable.

    If timestamps are missing or incomparable, retain the first input
    record rather than guessing which message came first.
    """

    parsed = [parse_timestamp(record.timestamp) for record in records]

    if any(value is None for value in parsed):
        return records[0]

    try:
        return records[parsed.index(min(parsed))]
    except TypeError:
        # For example, mixing timezone-aware and naive timestamps.
        return records[0]


def deduplicate_announcements(
    announcements: list[AnnouncementRecord],
    threshold: float = SIMILARITY_THRESHOLD,
) -> list[DuplicateGroup]:
    """
    Group similar announcements using a greedy representative strategy.

    Each later message is compared against existing group representatives.
    A message joins the most similar representative if the score meets
    the threshold. Otherwise, it starts a new group.
    """

    if not 0.0 <= threshold <= 1.0:
        raise ValueError("threshold must be between 0.0 and 1.0")

    groups: list[list[AnnouncementRecord]] = []

    for announcement in announcements:
        best_group_index = None
        best_score = -1.0

        for index, group in enumerate(groups):
            score = jaccard_similarity(
                announcement.text,
                group[0].text,
            )

            if score >= threshold and score > best_score:
                best_group_index = index
                best_score = score

        if best_group_index is None:
            groups.append([announcement])
        else:
            groups[best_group_index].append(announcement)

    result = []

    for group in groups:
        representative = earliest_record(group)
        duplicates = [
            record for record in group if record is not representative
        ]

        scores = [
            jaccard_similarity(representative.text, record.text)
            for record in duplicates
        ]

        result.append(
            DuplicateGroup(
                representative=representative,
                duplicates=duplicates,
                similarity_scores=scores,
            )
        )

    return result
