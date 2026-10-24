"""Integration tests for extraction and deadline resolution."""

from unittest.mock import Mock

from ai_pipeline.extractor import extract_announcement


def fake_ollama_response(monkeypatch):
    """Mock Ollama so tests run locally without network requests."""
    payload = {
        "announcement_type": "deadline",
        "summary_title": "Form submission",
        "required_action": "Not specified",
        "date_or_deadline": "Not specified",
        "urgency_level": "LOW",
        "ranking_reason": "A form submission is mentioned.",
        "confidence_score": 0.9,
        "source_url": "",
    }

    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = {
        "message": {"content": __import__("json").dumps(payload)}
    }

    monkeypatch.setattr(
        "ai_pipeline.extractor.requests.post",
        lambda *args, **kwargs: response,
    )


def test_supported_relative_deadline_is_resolved(monkeypatch):
    fake_ollama_response(monkeypatch)

    digest = extract_announcement(
        "Submit the form by tomorrow at 9 PM.",
        reference_timestamp="2026-10-24T18:00:00+05:30",
    )

    assert digest.announcement_type == "deadline"
    assert digest.date_or_deadline == "2026-10-25T21:00:00+05:30"
    assert digest.urgency_level == "MEDIUM"
    assert "Asia/Kolkata" in digest.ranking_reason


def test_ambiguous_deadline_is_not_guessed(monkeypatch):
    fake_ollama_response(monkeypatch)

    digest = extract_announcement(
        "Submit the form by sometime soon.",
        reference_timestamp="2026-10-24T18:00:00+05:30",
    )

    assert digest.announcement_type == "deadline"
    assert digest.date_or_deadline == "sometime soon"
    assert digest.urgency_level == "LOW"
    assert "could not be safely resolved" in digest.ranking_reason


def test_schedule_change_is_not_classified_as_deadline(monkeypatch):
    fake_ollama_response(monkeypatch)

    digest = extract_announcement(
        "The lecture has been postponed until tomorrow at 9 PM.",
        reference_timestamp="2026-10-24T18:00:00+05:30",
    )

    assert digest.announcement_type == "schedule_change"
    assert digest.date_or_deadline == "tomorrow at 9 PM"
