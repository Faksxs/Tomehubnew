import unittest
from unittest.mock import patch
import time

from services import llm_client
from services.llm_client import (
    MODEL_TIER_FLASH,
    MODEL_TIER_LITE,
    MODEL_TIER_PRO,
    ROUTE_MODE_EXPLORER_QWEN_PILOT,
    GenerateResult,
)


class _ProviderSuccess:
    name = "gemini"

    def __init__(self):
        self.calls = []

    def generate_text(self, **kwargs):
        self.calls.append(kwargs)
        return GenerateResult(
            text="ok",
            model_used=kwargs["model"],
            model_tier=MODEL_TIER_FLASH,
            fallback_applied=False,
            usage_metadata={"prompt_token_count": 5, "candidates_token_count": 3, "total_token_count": 8},
        )

    def embed_contents(self, **kwargs):
        self.calls.append(kwargs)
        return [[0.1, 0.2, 0.3]]


class _ProviderFlashFailsThenPro:
    name = "gemini"

    def __init__(self):
        self.calls = 0

    def generate_text(self, **kwargs):
        self.calls += 1
        if self.calls == 1:
            raise TimeoutError("timed out")
        return GenerateResult(
            text="fallback-ok",
            model_used=kwargs["model"],
            model_tier=MODEL_TIER_PRO,
            fallback_applied=False,
            usage_metadata=None,
        )

    def embed_contents(self, **kwargs):
        return []


class _ProviderAlwaysRetryableError:
    name = "qwen"

    def generate_text(self, **kwargs):
        raise TimeoutError("timed out")

    def embed_contents(self, **kwargs):
        return []


class _ProviderModelDelays:
    name = "qwen"

    def __init__(self, delays):
        self.delays = delays
        self.calls = []

    def generate_text(self, **kwargs):
        model = kwargs["model"]
        self.calls.append(model)
        time.sleep(self.delays.get(model, 0.0))
        return GenerateResult(
            text=f"winner:{model}",
            model_used=model,
            model_tier=MODEL_TIER_FLASH,
            fallback_applied=False,
            usage_metadata=None,
        )

    def embed_contents(self, **kwargs):
        return []


class LLMClientTests(unittest.TestCase):
    def test_http_options_timeout_is_milliseconds(self):
        options = llm_client.GeminiProvider._http_options(20.0)
        self.assertIsNotNone(options)
        self.assertEqual(options.timeout, 20000)

    def test_http_options_enforces_minimum_timeout(self):
        options = llm_client.GeminiProvider._http_options(5.0)
        self.assertIsNotNone(options)
        self.assertEqual(options.timeout, 10000)

    def test_http_options_invalid_values(self):
        self.assertIsNone(llm_client.GeminiProvider._http_options(None))
        self.assertIsNone(llm_client.GeminiProvider._http_options(0))
        self.assertIsNone(llm_client.GeminiProvider._http_options(-1))

    def test_is_retryable_llm_error(self):
        self.assertTrue(llm_client.is_retryable_llm_error(TimeoutError("timeout")))
        self.assertTrue(llm_client.is_retryable_llm_error(RuntimeError("HTTP 429 resource_exhausted")))
        self.assertFalse(llm_client.is_retryable_llm_error(RuntimeError("invalid argument")))

    def test_get_model_for_tier(self):
        self.assertEqual(llm_client.get_model_for_tier(MODEL_TIER_LITE), llm_client.settings.LLM_MODEL_LITE)
        self.assertEqual(llm_client.get_model_for_tier(MODEL_TIER_FLASH), llm_client.settings.LLM_MODEL_FLASH)
        self.assertEqual(llm_client.get_model_for_tier(MODEL_TIER_PRO), llm_client.settings.LLM_MODEL_PRO)

    def test_generate_text_success_without_fallback(self):
        provider = _ProviderSuccess()
        with patch("services.llm_client.get_provider", return_value=provider):
            result = llm_client.generate_text(
                model=llm_client.settings.LLM_MODEL_FLASH,
                prompt="hello",
                task="test",
                model_tier=MODEL_TIER_FLASH,
                timeout_s=1.0,
            )
        self.assertEqual(result.text, "ok")
        self.assertEqual(result.model_tier, MODEL_TIER_FLASH)
        self.assertFalse(result.fallback_applied)

    def test_generate_text_uses_pro_fallback_on_retryable_error(self):
        provider = _ProviderFlashFailsThenPro()
        state = {"pro_fallback_used": 0}
        with patch("services.llm_client.get_provider", return_value=provider):
            with patch.object(llm_client.settings, "LLM_PRO_FALLBACK_ENABLED", True):
                with patch.object(llm_client.settings, "LLM_PRO_FALLBACK_MAX_PER_REQUEST", 1):
                    result = llm_client.generate_text(
                        model=llm_client.settings.LLM_MODEL_FLASH,
                        prompt="hello",
                        task="test",
                        model_tier=MODEL_TIER_FLASH,
                        allow_pro_fallback=True,
                        fallback_state=state,
                    )
        self.assertEqual(result.text, "fallback-ok")
        self.assertEqual(result.model_tier, MODEL_TIER_PRO)
        self.assertTrue(result.fallback_applied)
        self.assertEqual(state["pro_fallback_used"], 1)

    def test_generate_text_explorer_qwen_retryable_falls_back_to_gemini(self):
        qwen_provider = _ProviderAlwaysRetryableError()
        gemini_provider = _ProviderSuccess()

        def _provider_selector(provider_hint=None):
            if provider_hint == "qwen":
                return qwen_provider
            return gemini_provider

        state = {"secondary_fallback_used": 0}
        with patch("services.llm_client.get_provider", side_effect=_provider_selector):
            with patch.object(llm_client.settings, "LLM_EXPLORER_QWEN_PILOT_ENABLED", True):
                with patch.object(llm_client.settings, "LLM_EXPLORER_FALLBACK_PROVIDER", "gemini"):
                    with patch.object(llm_client.settings, "LLM_EXPLORER_SECONDARY_MAX_PER_REQUEST", 1):
                        with patch.object(llm_client.settings, "LLM_EXPLORER_PARALLEL_NVIDIA_ENABLED", False):
                            with patch("services.llm_client._consume_qwen_rpm_slots", return_value=True):
                                result = llm_client.generate_text(
                                    model=llm_client.settings.LLM_EXPLORER_PRIMARY_MODEL,
                                    prompt="hello",
                                    task="test_explorer",
                                    model_tier=MODEL_TIER_FLASH,
                                    provider_hint="qwen",
                                    route_mode=ROUTE_MODE_EXPLORER_QWEN_PILOT,
                                    allow_secondary_fallback=True,
                                    fallback_state=state,
                                )

        self.assertEqual(result.text, "ok")
        self.assertEqual(result.provider_name, "gemini")
        self.assertTrue(result.fallback_applied)
        self.assertTrue(result.secondary_fallback_applied)
        self.assertEqual(result.fallback_reason, "qwen_retryable_error")
        self.assertEqual(state["secondary_fallback_used"], 1)

    def test_generate_text_explorer_qwen_rpm_cap_bypasses_to_gemini(self):
        qwen_provider = _ProviderAlwaysRetryableError()
        gemini_provider = _ProviderSuccess()

        def _provider_selector(provider_hint=None):
            if provider_hint == "qwen":
                return qwen_provider
            return gemini_provider

        state = {"secondary_fallback_used": 0}
        with patch("services.llm_client.get_provider", side_effect=_provider_selector):
            with patch.object(llm_client.settings, "LLM_EXPLORER_QWEN_PILOT_ENABLED", True):
                with patch.object(llm_client.settings, "LLM_EXPLORER_FALLBACK_PROVIDER", "gemini"):
                    with patch.object(llm_client.settings, "LLM_EXPLORER_SECONDARY_MAX_PER_REQUEST", 1):
                        with patch.object(llm_client.settings, "LLM_EXPLORER_PARALLEL_NVIDIA_ENABLED", False):
                            with patch("services.llm_client._consume_qwen_rpm_slots", return_value=False):
                                result = llm_client.generate_text(
                                    model=llm_client.settings.LLM_EXPLORER_PRIMARY_MODEL,
                                    prompt="hello",
                                    task="test_explorer_rpm",
                                    model_tier=MODEL_TIER_FLASH,
                                    provider_hint="qwen",
                                    route_mode=ROUTE_MODE_EXPLORER_QWEN_PILOT,
                                    allow_secondary_fallback=True,
                                    fallback_state=state,
                                )

        self.assertEqual(result.text, "ok")
        self.assertEqual(result.provider_name, "gemini")
        self.assertTrue(result.fallback_applied)
        self.assertTrue(result.secondary_fallback_applied)
        self.assertEqual(result.fallback_reason, "qwen_rpm_cap")
        self.assertEqual(state["secondary_fallback_used"], 1)

    def test_generate_text_explorer_parallel_nvidia_uses_faster_winner(self):
        qwen_model = "qwen/qwen3-next-80b-a3b-thinking"
        minimax_model = "minimaxai/minimax-m2.1"
        provider = _ProviderModelDelays(
            delays={
                qwen_model: 0.05,
                minimax_model: 0.01,
            }
        )

        with patch("services.llm_client.get_provider", return_value=provider):
            with patch.object(llm_client.settings, "LLM_EXPLORER_QWEN_PILOT_ENABLED", True):
                with patch.object(llm_client.settings, "LLM_EXPLORER_PARALLEL_NVIDIA_ENABLED", True):
                    with patch.object(llm_client.settings, "LLM_EXPLORER_PARALLEL_NVIDIA_MODEL", minimax_model):
                        with patch("services.llm_client._consume_qwen_rpm_slots", return_value=True) as rpm_patch:
                            result = llm_client.generate_text(
                                model=qwen_model,
                                prompt="hello",
                                task="test_explorer_parallel",
                                model_tier=MODEL_TIER_FLASH,
                                provider_hint="qwen",
                                route_mode=ROUTE_MODE_EXPLORER_QWEN_PILOT,
                                allow_secondary_fallback=False,
                            )

        self.assertEqual(result.model_used, minimax_model)
        self.assertEqual(result.text, f"winner:{minimax_model}")
        self.assertFalse(result.fallback_applied)
        rpm_patch.assert_called_once_with(2)


if __name__ == "__main__":
    unittest.main()
