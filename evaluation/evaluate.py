
import json
from itertools import combinations
from pathlib import Path

from ai_pipeline.deduplication import (
    SIMILARITY_THRESHOLD,
    jaccard_similarity,
)
from ai_pipeline.schema import AnnouncementDigest
from ai_pipeline.urgency import rank_urgency


ROOT = Path(__file__).resolve().parent.parent
DATASET_PATH = ROOT / "data" / "evaluation" / "announcements.json"

# Fixed reference time makes the evaluation reproducible.
# The deadline examples are all due later on 24 October 2026.
REFERENCE_TIMESTAMP = "2026-10-24T12:00:00"


def load_dataset():
    """Load and validate the labelled evaluation dataset."""

    with DATASET_PATH.open("r", encoding="utf-8") as file:
        records = json.load(file)

    if len(records) != 40:
        raise ValueError(
            f"Expected 40 examples, found {len(records)}."
        )

    ids = [record["id"] for record in records]
    if len(ids) != len(set(ids)):
        raise ValueError("Dataset contains duplicate IDs.")

    return records


def calculate_metrics(true_positive, false_positive, false_negative):
    """Calculate precision, recall, and F1 without dividing by zero."""

    precision_denominator = true_positive + false_positive
    recall_denominator = true_positive + false_negative

    precision = (
        true_positive / precision_denominator
        if precision_denominator
        else 0.0
    )
    recall = (
        true_positive / recall_denominator
        if recall_denominator
        else 0.0
    )

    f1 = (
        2 * precision * recall / (precision + recall)
        if precision + recall
        else 0.0
    )

    return precision, recall, f1


def evaluate_urgency(records):
    """Evaluate HIGH urgency as the positive class."""

    true_positive = 0
    false_positive = 0
    false_negative = 0
    true_negative = 0
    errors = []

    for record in records:
        announcement = AnnouncementDigest(
            announcement_type=record["announcement_type"],
            summary_title=record["text"][:80],
            required_action="Not specified",
            date_or_deadline=record["date_or_deadline"],
            urgency_level="LOW",
            ranking_reason="Initial evaluation label.",
            confidence_score=0.5,
            source_url="",
        )

        result = rank_urgency(
            announcement,
            REFERENCE_TIMESTAMP,
        )

        expected_high = record["expected_urgency"] == "HIGH"
        predicted_high = result.urgency_level == "HIGH"

        if expected_high and predicted_high:
            true_positive += 1
        elif not expected_high and predicted_high:
            false_positive += 1
            errors.append(
                (
                    record["id"],
                    "False positive",
                    result.urgency_level,
                    result.ranking_reason,
                )
            )
        elif expected_high and not predicted_high:
            false_negative += 1
            errors.append(
                (
                    record["id"],
                    "False negative",
                    result.urgency_level,
                    result.ranking_reason,
                )
            )
        else:
            true_negative += 1

    precision, recall, f1 = calculate_metrics(
        true_positive,
        false_positive,
        false_negative,
    )

    print("\n=== URGENCY EVALUATION ===")
    print("Positive class: HIGH")
    print(f"Reference timestamp: {REFERENCE_TIMESTAMP}")
    print(f"True positives:  {true_positive}")
    print(f"False positives: {false_positive}")
    print(f"False negatives: {false_negative}")
    print(f"True negatives:  {true_negative}")
    print(f"Precision: {precision:.3f}")
    print(f"Recall:    {recall:.3f}")
    print(f"F1 score:  {f1:.3f}")

    if errors:
        print("\nUrgency errors:")
        for item_id, error_type, urgency, reason in errors:
            print(
                f"- {item_id}: {error_type}; "
                f"predicted={urgency}; reason={reason}"
            )
    else:
        print("No urgency classification errors.")

    return {
        "true_positive": true_positive,
        "false_positive": false_positive,
        "false_negative": false_negative,
        "true_negative": true_negative,
        "precision": precision,
        "recall": recall,
        "f1": f1,
    }


def evaluate_duplicates(records):
    """Evaluate duplicate detection over all distinct record pairs."""

    true_positive = 0
    false_positive = 0
    false_negative = 0
    true_negative = 0
    false_positives = []
    false_negatives = []

    for first, second in combinations(records, 2):
        same_group = (
            first["duplicate_group"] is not None
            and first["duplicate_group"] == second["duplicate_group"]
        )

        similarity = jaccard_similarity(
            first["text"],
            second["text"],
        )
        predicted_duplicate = similarity >= SIMILARITY_THRESHOLD

        if same_group and predicted_duplicate:
            true_positive += 1
        elif not same_group and predicted_duplicate:
            false_positive += 1
            false_positives.append(
                (first["id"], second["id"], similarity)
            )
        elif same_group and not predicted_duplicate:
            false_negative += 1
            false_negatives.append(
                (first["id"], second["id"], similarity)
            )
        else:
            true_negative += 1

    precision, recall, f1 = calculate_metrics(
        true_positive,
        false_positive,
        false_negative,
    )

    print("\n=== DUPLICATE DETECTION EVALUATION ===")
    print(f"Similarity threshold: {SIMILARITY_THRESHOLD:.2f}")
    print(f"True positives:  {true_positive}")
    print(f"False positives: {false_positive}")
    print(f"False negatives: {false_negative}")
    print(f"True negatives:  {true_negative}")
    print(f"Precision: {precision:.3f}")
    print(f"Recall:    {recall:.3f}")
    print(f"F1 score:  {f1:.3f}")

    print("\nDuplicate false positives:")
    if false_positives:
        for first_id, second_id, score in false_positives:
            print(
                f"- {first_id} vs {second_id}: "
                f"similarity={score:.3f}"
            )
    else:
        print("- None")

    print("\nDuplicate false negatives:")
    if false_negatives:
        for first_id, second_id, score in false_negatives:
            print(
                f"- {first_id} vs {second_id}: "
                f"similarity={score:.3f}"
            )
    else:
        print("- None")

    return {
        "true_positive": true_positive,
        "false_positive": false_positive,
        "false_negative": false_negative,
        "true_negative": true_negative,
        "precision": precision,
        "recall": recall,
        "f1": f1,
    }


def main():
    records = load_dataset()

    print(f"Loaded {len(records)} labelled announcements.")
    urgency_results = evaluate_urgency(records)
    duplicate_results = evaluate_duplicates(records)

    print("\n=== EVALUATION SUMMARY ===")
    print(
        "Urgency HIGH precision/recall: "
        f"{urgency_results['precision']:.3f} / "
        f"{urgency_results['recall']:.3f}"
    )
    print(
        "Duplicate precision/recall: "
        f"{duplicate_results['precision']:.3f} / "
        f"{duplicate_results['recall']:.3f}"
    )
    print(
        "\nNote: these are results on the initial synthetic "
        "dataset, not a measure of real-world performance."
    )


if __name__ == "__main__":
    main()
