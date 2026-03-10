import asyncio
import unittest
from unittest.mock import patch

from services import ai_service


class AiServiceArticleSearchTests(unittest.TestCase):
    def test_article_search_uses_openalex_before_llm(self):
        payload = {
            "display_name": "Security and Privacy Issues in Internet of Things (IoT)",
            "doi": "10.36227/techrxiv.23512389.v1",
            "authors": [{"display_name": "Muhammad Akmal Husaini Bin Haris"}],
            "concepts": [{"display_name": "Internet of Things"}],
        }

        with patch("services.ai_service._fetch_openalex", return_value=payload) as mock_openalex, patch(
            "services.ai_service._run_generate_text_async"
        ) as mock_llm:
            results = asyncio.run(
                ai_service.search_resources_async("10.36227/techrxiv.23512389.v1", "ARTICLE")
            )

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["title"], payload["display_name"])
        self.assertEqual(results[0]["url"], "https://doi.org/10.36227/techrxiv.23512389.v1")
        mock_openalex.assert_called_once_with(
            "10.36227/techrxiv.23512389.v1",
            "",
            "10.36227/techrxiv.23512389.v1",
        )
        mock_llm.assert_not_called()

    def test_article_search_falls_back_to_llm_when_openalex_empty(self):
        class _FakeResult:
            text = "[]"
            secondary_fallback_applied = False

        with patch("services.ai_service._fetch_openalex", return_value=None), patch(
            "services.ai_service._run_generate_text_async",
            return_value=_FakeResult(),
        ) as mock_llm:
            results = asyncio.run(ai_service.search_resources_async("unknown article", "ARTICLE"))

        self.assertEqual(results, [])
        mock_llm.assert_called_once()


if __name__ == "__main__":
    unittest.main()
