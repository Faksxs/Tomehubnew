import unittest
from datetime import UTC, datetime, timedelta

from services.memory_profile_service import (
    build_memory_context_snippet,
    parse_profile_payload,
    should_refresh_profile,
)


class MemoryProfileServiceTests(unittest.TestCase):
    def test_should_refresh_profile_respects_threshold(self):
        current = datetime(2026, 3, 7, 12, 0, tzinfo=UTC)
        fresh_profile = {
            "last_refreshed_at": (current - timedelta(minutes=10)).isoformat(),
        }
        stale_profile = {
            "last_refreshed_at": (current - timedelta(minutes=90)).isoformat(),
        }

        self.assertFalse(
            should_refresh_profile(fresh_profile, min_refresh_minutes=30, now=current)
        )
        self.assertTrue(
            should_refresh_profile(stale_profile, min_refresh_minutes=30, now=current)
        )
        self.assertTrue(
            should_refresh_profile(fresh_profile, min_refresh_minutes=30, force=True, now=current)
        )

    def test_parse_profile_payload_falls_back_to_counts(self):
        payload = parse_profile_payload(
            """```json
            {
              "profile_summary": "Reader is focusing on ethics and tragedy.",
              "active_themes": ["ethics", "tragedy"],
              "open_questions": ["How does duty relate to fate?"]
            }
            ```""",
            fallback_counts={"notes": 3, "messages": 4},
        )

        self.assertEqual(payload["profile_summary"], "Reader is focusing on ethics and tragedy.")
        self.assertEqual(payload["active_themes"], ["ethics", "tragedy"])
        self.assertEqual(payload["open_questions"], ["How does duty relate to fate?"])
        self.assertEqual(payload["evidence_counts"], {"notes": 3, "messages": 4})

    def test_build_memory_context_snippet_is_compact_and_structured(self):
        snippet = build_memory_context_snippet(
            {
                "profile_summary": "User keeps comparing duty, conscience, and leadership.",
                "active_themes": ["duty", "conscience", "leadership"],
                "open_questions": ["Is duty stronger than personal safety?"],
            },
            max_chars=220,
        )

        self.assertIn("### USER MEMORY PROFILE", snippet)
        self.assertIn("Active themes:", snippet)
        self.assertIn("Open questions:", snippet)
        self.assertLessEqual(len(snippet), 220)


if __name__ == "__main__":
    unittest.main()
