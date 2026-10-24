import json
import re
import statistics
import time
from pathlib import Path

from ai_pipeline.extractor import extract_announcement
from ai_pipeline.urgency import rank_urgency


ROOT = Path(__file__).resolve().parent.parent
DATASET_PATH = ROOT / "data" / "evaluation" / "announcements.json"
REFERENCE_TIMESTAMP = "2026-10-24T12:00:00"


def normalize(value):
    """Normalize whitespace and common date-spacing inconsistencies."""
    value = str(value or "").strip().lower()
    value = re.sub(
        r"(\d)(january|february|march|april|may|june|july|"
        r"august|september|october|november|december)\b",
        r"\1 \2",
        value,
        flags=re.IGNORECASE,
    )
    value = re.sub(r"\bat\s*(?=\d)", "at ", value, flags=re.IGNORECASE)
    return " ".join(value.split())


def load_dataset():
    with DATASET_PATH.open(encoding="utf-8") as file:
        records = json.load(file)

    if not records:
        raise ValueError("Evaluation dataset is empty.")

    ids = [record["id"] for record in records]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate evaluation IDs found.")

    missing = [
        record["id"]
        for record in records
        if "expected_required_action" not in record
    ]
    if missing:
        raise ValueError(
            "Missing expected_required_action labels for: "
            + ", ".join(missing)
        )

    return records


def main():
    records = load_dataset()
    results = []
    latencies = []

    print(f"Evaluating {len(records)} announcements")
    print("Model: configured Ollama model")
    print(f"Reference timestamp: {REFERENCE_TIMESTAMP}")
    print("This test calls the actual local extractor.")
    print("\nProcessing announcements; this may take a few minutes...")

    for record in records:
        started = time.perf_counter()

        try:
            extracted = extract_announcement(
                record["text"],
                source_url="",
                reference_timestamp=REFERENCE_TIMESTAMP,
            )
            ranked = rank_urgency(extracted, REFERENCE_TIMESTAMP)
            elapsed = time.perf_counter() - started
            latencies.append(elapsed)

            expected_action = record["expected_required_action"]
            predicted_action = ranked.required_action

            type_ok = (
                ranked.announcement_type == record["announcement_type"]
            )
            date_ok = (
                normalize(ranked.date_or_deadline)
                == normalize(record["date_or_deadline"])
            )
            urgency_ok = (
                ranked.urgency_level == record["expected_urgency"]
            )
            action_ok = (
                normalize(predicted_action) == normalize(expected_action)
            )

            expected_has_action = normalize(expected_action) != "not specified"
            predicted_has_action = normalize(predicted_action) != "not specified"

            missing_action = expected_has_action and not predicted_has_action
            false_action = not expected_has_action and predicted_has_action

            results.append({
                "id": record["id"],
                "type_ok": type_ok,
                "date_ok": date_ok,
                "urgency_ok": urgency_ok,
                "action_ok": action_ok,
                "missing_action": missing_action,
                "false_action": false_action,
                "expected_type": record["announcement_type"],
                "predicted_type": ranked.announcement_type,
                "expected_date": record["date_or_deadline"],
                "predicted_date": ranked.date_or_deadline,
                "expected_urgency": record["expected_urgency"],
                "predicted_urgency": ranked.urgency_level,
                "expected_action": expected_action,
                "predicted_action": predicted_action,
                "latency": elapsed,
            })

            print(
                f"{record['id']}: "
                f"type={'PASS' if type_ok else 'FAIL'}, "
                f"date={'PASS' if date_ok else 'FAIL'}, "
                f"urgency={'PASS' if urgency_ok else 'FAIL'}, "
                f"action={'PASS' if action_ok else 'FAIL'}, "
                f"{elapsed:.2f}s"
            )

        except Exception as exc:
            elapsed = time.perf_counter() - started
            results.append({
                "id": record["id"],
                "error": f"{type(exc).__name__}: {exc}",
                "latency": elapsed,
            })
            print(f"{record['id']}: ERROR — {type(exc).__name__}: {exc}")

    successful = [item for item in results if "error" not in item]
    failed = [item for item in results if "error" in item]

    print("\n=== EXTRACTION EVALUATION SUMMARY ===")
    print(f"Dataset size: {len(records)}")
    print(f"Successful extractions: {len(successful)}")
    print(f"Failed extractions: {len(failed)}")

    if successful:
        for field, label in (
            ("type_ok", "Announcement type"),
            ("date_ok", "Date/detail field"),
            ("urgency_ok", "Urgency"),
            ("action_ok", "Required action exact match"),
        ):
            correct = sum(item[field] for item in successful)
            print(
                f"{label}: {correct}/{len(successful)} "
                f"({correct / len(successful):.1%})"
            )

        missing_actions = sum(item["missing_action"] for item in successful)
        false_actions = sum(item["false_action"] for item in successful)

        print("\n=== ACTION ERROR ANALYSIS ===")
        print(f"Missing required actions: {missing_actions}")
        print(f"False actions on 'Not specified' records: {false_actions}")

        print("\nField mismatches:")
        mismatch_count = 0

        for item in successful:
            if not all(item[field] for field in (
                "type_ok", "date_ok", "urgency_ok", "action_ok"
            )):
                mismatch_count += 1
                print(
                    f"- {item['id']}: "
                    f"type {item['expected_type']!r} -> "
                    f"{item['predicted_type']!r}; "
                    f"date/detail {item['expected_date']!r} -> "
                    f"{item['predicted_date']!r}; "
                    f"urgency {item['expected_urgency']!r} -> "
                    f"{item['predicted_urgency']!r}; "
                    f"action {item['expected_action']!r} -> "
                    f"{item['predicted_action']!r}"
                )

        if mismatch_count == 0:
            print("- None")

    if latencies:
        print("\n=== LATENCY ===")
        print(f"Mean:   {statistics.mean(latencies):.2f}s")
        print(f"Median: {statistics.median(latencies):.2f}s")
        print(f"Min:    {min(latencies):.2f}s")
        print(f"Max:    {max(latencies):.2f}s")

    if failed:
        print("\nExtraction errors:")
        for item in failed:
            print(f"- {item['id']}: {item['error']}")

    print(
        "\nCaveat: results reflect this synthetic dataset only. "
        "Text fields use exact normalized string matching. "
        "Action labels are manually assigned evaluation targets; "
        "review mismatches before changing extraction logic. "
        "Urgency is ranked after extraction by the deterministic ranker."
    )


if __name__ == "__main__":
    main()
