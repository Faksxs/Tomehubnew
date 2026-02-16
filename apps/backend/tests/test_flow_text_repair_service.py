import unittest
from unittest.mock import patch

from services.flow_text_repair_service import FlowTextRepairService


class TestFlowTextRepairService(unittest.TestCase):
    def test_repairs_hyphen_break_for_pdf(self):
        service = FlowTextRepairService(
            enabled=True,
            source_types={"PDF"},
            max_delta_ratio=0.5,
            max_input_chars=4000,
            ruleset_version="test_v1",
        )
        text = "Bu metin ozel-\nlikle daha temiz olmali ve yeterince uzundur."

        repaired = service.repair_for_flow_card(text, "PDF")

        self.assertNotIn("\n", repaired)
        self.assertIn("ozellikle", repaired)

    def test_rejects_when_delta_ratio_too_high(self):
        service = FlowTextRepairService(
            enabled=True,
            source_types={"PDF"},
            max_delta_ratio=0.0,
            max_input_chars=4000,
            ruleset_version="test_v1",
        )
        text = "Bu metin ozel-\nlikle daha temiz olmali ve yeterince uzundur."

        repaired = service.repair_for_flow_card(text, "PDF")
        self.assertEqual(repaired, text)

    def test_noop_for_non_target_source_type(self):
        service = FlowTextRepairService(
            enabled=True,
            source_types={"PDF"},
            max_delta_ratio=0.5,
            max_input_chars=4000,
            ruleset_version="test_v1",
        )
        text = "Bu metin website degil, personal note olsun ve oldugu gibi kalsin."

        repaired = service.repair_for_flow_card(text, "HIGHLIGHT")
        self.assertEqual(repaired, text)

    def test_caches_by_content_hash(self):
        service = FlowTextRepairService(
            enabled=True,
            source_types={"PDF"},
            max_delta_ratio=0.5,
            max_input_chars=4000,
            ruleset_version="test_v1",
        )
        text = "Bu metin ozel-\nlikle daha temiz olmali ve yeterince uzundur."

        with patch.object(service, "_apply_pipeline", wraps=service._apply_pipeline) as wrapped:
            first = service.repair_for_flow_card(text, "PDF")
            second = service.repair_for_flow_card(text, "PDF")

        self.assertEqual(first, second)
        self.assertEqual(wrapped.call_count, 1)


if __name__ == "__main__":
    unittest.main()
