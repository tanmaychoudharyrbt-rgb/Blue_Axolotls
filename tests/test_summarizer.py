import json
import urllib.request
import urllib.error
import pytest

from slack_listener import (
    summarize_message,
    fallback_summary,
    looks_like_reasoning,
)


def test_looks_like_reasoning_detects_chain_of_thought():
    assert looks_like_reasoning("Hmm, the user wants me to summarize this.") is True
    assert looks_like_reasoning("I need to extract the key dates and actions.") is True
    assert looks_like_reasoning("The user is asking for a summary of the exam.") is True
    assert looks_like_reasoning("We are to say hello in exactly 3 words.") is True

    # Real summary should NOT be flagged as reasoning
    assert looks_like_reasoning("CS101 lab report due Friday at 5 PM in Room 402.") is False
    assert looks_like_reasoning("Midterm postponed to Nov 3 at 10 AM in Hall A.") is False


def test_fallback_summary_preserves_short_messages():
    short_msg = "Exam at 10 AM tomorrow."
    assert fallback_summary(short_msg) == short_msg


def test_fallback_summary_extracts_core_opening_sentence():
    long_msg = (
        "Attention students: The final deadline for CS201 project submission is Friday at midnight. "
        "Please ensure that your Git repositories are updated and all team members are listed. "
        "Any late submissions will be penalized by 10 percent per day."
    )
    fallback = fallback_summary(long_msg, limit=120)
    assert len(fallback) <= 120
    assert "Attention students" in fallback
    # Should not paste the entire 220+ char block
    assert len(fallback) < len(long_msg)


def test_summarize_message_handles_ollama_failure(monkeypatch):
    def failing_urlopen(*args, **kwargs):
        raise urllib.error.URLError("Connection refused")

    monkeypatch.setattr(urllib.request, "urlopen", failing_urlopen)

    msg = "Submit the physics lab report by 5 PM today."
    res = summarize_message(msg)
    assert res == "Submit the physics lab report by 5 PM today."


def test_summarize_message_cleans_think_tags(monkeypatch):
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def read(self):
            content = json.dumps({
                "summary": "CS101 final report due Friday 5 PM in room 402."
            })
            return json.dumps({
                "message": {
                    "role": "assistant",
                    "content": f"<think>thinking here...</think>{content}"
                }
            }).encode("utf-8")

    monkeypatch.setattr(
        urllib.request, "urlopen", lambda *args, **kwargs: FakeResponse()
    )

    res = summarize_message("Reminder: submit CS101 report by Friday 5 PM in room 402.")
    assert res == "CS101 final report due Friday 5 PM in room 402."
    assert "<think>" not in res


def test_summarize_message_with_live_ollama():
    """Verify live summarization against local Ollama model if available."""
    try:
        req = urllib.request.Request("http://localhost:11434/api/tags")
        with urllib.request.urlopen(req, timeout=2) as resp:
            pass
    except Exception:
        pytest.skip("Local Ollama is not accessible")

    announcement = (
        "URGENT NOTICE: Tomorrow's midsem exam for Data Structures (CS201) "
        "has been postponed to next Monday, Nov 3rd at 10:00 AM in Hall A due to maintenance."
    )

    summary = summarize_message(announcement)

    assert summary, "Summary should not be empty"
    # Crucial test: It must NOT just paste the exact same message!
    assert summary != announcement, "Bot must summarize, not echo the exact message!"
    assert not looks_like_reasoning(summary), "Summary must not leak model reasoning"
    assert "<think>" not in summary

    # Check key information preservation
    assert "CS201" in summary or "Data Structures" in summary or "midsem" in summary.lower() or "exam" in summary.lower()
    assert len(summary.split()) <= 30, "Summary should be under 30 words"
