"""
tests/test_voice_and_calendar.py
Unit tests for Kokoro/Local TTS synthesis and Calendar deadline parsing.
"""

import unittest
from datetime import datetime

from calendar_integration import parse_deadline, sync_digest_to_calendars
from tts_kokoro import synthesize_bytes


class TestVoiceAndCalendar(unittest.TestCase):

    def test_deadline_parser_today(self):
        dt = parse_deadline("Today, 11 PM")
        self.assertIsNotNone(dt)
        self.assertEqual(dt.hour, 23)
        self.assertEqual(dt.minute, 0)

    def test_deadline_parser_tomorrow(self):
        dt = parse_deadline("Tomorrow 5:30 PM")
        self.assertIsNotNone(dt)
        self.assertEqual(dt.hour, 17)
        self.assertEqual(dt.minute, 30)

    def test_deadline_parser_iso_date(self):
        dt = parse_deadline("2026-11-15")
        self.assertIsNotNone(dt)
        self.assertEqual(dt.year, 2026)
        self.assertEqual(dt.month, 11)
        self.assertEqual(dt.day, 15)

    def test_deadline_parser_unspecified(self):
        self.assertIsNone(parse_deadline("Not specified"))
        self.assertIsNone(parse_deadline(""))
        self.assertIsNone(parse_deadline("none"))

    def test_calendar_sync_zero_setup(self):
        payload = {
            "ranked_summary": [
                {
                    "title": "Lab Exam Final Submission",
                    "summary": "Submit final report by tonight 11 PM.",
                    "deadline": "Today 11 PM",
                    "urgency": "HIGH",
                }
            ]
        }
        results = sync_digest_to_calendars(payload, use_google=True, use_outlook=True)
        self.assertEqual(len(results), 1)
        res = results[0]
        self.assertIn("google", res)
        self.assertIn("outlook", res)
        # Verify 1-click links are generated
        self.assertIn("calendar.google.com", res["google"]["htmlLink"])
        self.assertIn("outlook.live.com", res["outlook"]["webLink"])

    def test_tts_synthesize_bytes(self):
        text = "Short announcement test."
        data, engine = synthesize_bytes(text, speed=1.5)
        self.assertGreater(len(data), 1000)
        self.assertIn("speed", engine)


if __name__ == "__main__":
    unittest.main()
