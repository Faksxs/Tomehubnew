import unittest
import sys
import types
from pathlib import Path
from unittest.mock import patch

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

fake_infra_pkg = types.ModuleType("infrastructure")
fake_db_manager_module = types.ModuleType("infrastructure.db_manager")
fake_db_manager_module.DatabaseManager = object
sys.modules.setdefault("infrastructure", fake_infra_pkg)
sys.modules["infrastructure.db_manager"] = fake_db_manager_module

fake_llm_client_module = types.ModuleType("services.llm_client")
fake_llm_client_module.MODEL_TIER_FLASH = "flash"
fake_llm_client_module.generate_text = lambda *args, **kwargs: None
sys.modules["services.llm_client"] = fake_llm_client_module

from services import translation_service


class TranslationServiceTests(unittest.TestCase):
    def test_resolve_translation_model_prefers_explicit_translation_model(self):
        with patch.object(
            translation_service.settings,
            "LLM_TRANSLATION_MODEL",
            "moonshotai/kimi-k2-instruct",
        ):
            self.assertEqual(
                translation_service._resolve_translation_model(),
                "moonshotai/kimi-k2-instruct",
            )

    def test_resolve_translation_model_normalizes_thinking_suffix(self):
        with patch.object(
            translation_service.settings,
            "LLM_TRANSLATION_MODEL",
            "kimi-k2-thinking",
        ):
            self.assertEqual(
                translation_service._resolve_translation_model(),
                "kimi-k2-instruct",
            )

    def test_resolve_translation_provider_defaults_to_nvidia(self):
        with patch.object(
            translation_service.settings,
            "LLM_TRANSLATION_PROVIDER",
            "",
        ):
            self.assertEqual(
                translation_service._resolve_translation_provider(),
                "nvidia",
            )


if __name__ == "__main__":
    unittest.main()
