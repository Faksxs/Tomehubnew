# -*- coding: utf-8 -*-
"""
Unified LLM client for TomeHub runtime services.

Responsibilities:
- Provide provider-aware SDK integration (Gemini + Qwen/NVIDIA for explorer pilot)
- Keep model/tier policy in one place
- Expose provider-like interface for future multi-provider extension
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import json
import logging
from threading import Lock
import time
from typing import Any, Dict, List, Optional, Protocol
import urllib.error
import urllib.request

from google import genai
from google.genai import types

from config import settings
from services.monitoring import (
    AI_SERVICE_LATENCY,
    LLM_CALLS_TOTAL,
    LLM_FALLBACK_TOTAL,
    LLM_PROVIDER_CALLS_TOTAL,
    LLM_TOKENS_TOTAL,
)

logger = logging.getLogger(__name__)

MODEL_TIER_LITE = "lite"
MODEL_TIER_FLASH = "flash"
MODEL_TIER_PRO = "pro"
MODEL_TIER_EMBEDDING = "embedding"

PROVIDER_GEMINI = "gemini"
PROVIDER_QWEN = "qwen"
PROVIDER_NVIDIA = "nvidia"

ROUTE_MODE_DEFAULT = "default"
ROUTE_MODE_EXPLORER_QWEN_PILOT = "explorer_qwen_pilot"

_GEMINI_MIN_TIMEOUT_MS = 10_000
_NVIDIA_DEFAULT_TIMEOUT_S = 30.0
_NVIDIA_MAX_ERROR_BODY_CHARS = 600

_QWEN_WINDOW_SECONDS = 60.0
_QWEN_RPM_TIMESTAMPS: deque[float] = deque()
_QWEN_RPM_LOCK = Lock()


@dataclass
class GenerateResult:
    text: str
    model_used: str
    model_tier: str
    fallback_applied: bool
    usage_metadata: Optional[Dict[str, Any]] = None
    provider_name: str = PROVIDER_GEMINI
    secondary_fallback_applied: bool = False
    fallback_reason: Optional[str] = None


class LLMProvider(Protocol):
    name: str

    def generate_text(
        self,
        model: str,
        prompt: str,
        temperature: Optional[float] = None,
        max_output_tokens: Optional[int] = None,
        response_mime_type: Optional[str] = None,
        timeout_s: Optional[float] = None,
    ) -> GenerateResult:
        ...

    def embed_contents(
        self,
        model: str,
        contents: str | List[str],
        task_type: str = "retrieval_document",
        output_dimensionality: int = 768,
        timeout_s: Optional[float] = None,
    ) -> List[List[float]]:
        ...


class GeminiProvider:
    name = PROVIDER_GEMINI
    _client: Optional[genai.Client] = None
    _client_lock = Lock()

    def _get_client(self) -> genai.Client:
        if self._client is None:
            with self._client_lock:
                if self._client is None:
                    self._client = genai.Client(api_key=settings.GEMINI_API_KEY)
        return self._client

    @staticmethod
    def _http_options(timeout_s: Optional[float]) -> Optional[types.HttpOptions]:
        if timeout_s is None:
            return None
        try:
            timeout_ms = int(float(timeout_s) * 1000)
        except (TypeError, ValueError):
            return None
        if timeout_ms <= 0:
            return None
        if timeout_ms < _GEMINI_MIN_TIMEOUT_MS:
            timeout_ms = _GEMINI_MIN_TIMEOUT_MS
        return types.HttpOptions(timeout=timeout_ms)

    def generate_text(
        self,
        model: str,
        prompt: str,
        temperature: Optional[float] = None,
        max_output_tokens: Optional[int] = None,
        response_mime_type: Optional[str] = None,
        timeout_s: Optional[float] = None,
    ) -> GenerateResult:
        config: Dict[str, Any] = {}
        if temperature is not None:
            config["temperature"] = temperature
        if max_output_tokens is not None:
            config["max_output_tokens"] = max_output_tokens
        if response_mime_type:
            config["response_mime_type"] = response_mime_type
        http_options = self._http_options(timeout_s)
        if http_options is not None:
            config["http_options"] = http_options

        with AI_SERVICE_LATENCY.labels(service="gemini_flash", operation="generate").time():
            response = self._get_client().models.generate_content(
                model=model,
                contents=prompt,
                config=config or None,
            )

        text = getattr(response, "text", None) or ""
        usage = getattr(response, "usage_metadata", None)
        usage_metadata = usage.model_dump() if usage is not None else None
        return GenerateResult(
            text=text,
            model_used=model,
            model_tier=MODEL_TIER_FLASH,
            fallback_applied=False,
            usage_metadata=usage_metadata,
            provider_name=self.name,
        )

    def embed_contents(
        self,
        model: str,
        contents: str | List[str],
        task_type: str = "retrieval_document",
        output_dimensionality: int = 768,
        timeout_s: Optional[float] = None,
    ) -> List[List[float]]:
        config: Dict[str, Any] = {
            "task_type": task_type,
            "output_dimensionality": output_dimensionality,
        }
        http_options = self._http_options(timeout_s)
        if http_options is not None:
            config["http_options"] = http_options

        with AI_SERVICE_LATENCY.labels(service="google_embedding", operation="embed").time():
            response = self._get_client().models.embed_content(
                model=model,
                contents=contents,
                config=config,
            )

        embeddings = []
        for item in (response.embeddings or []):
            values = getattr(item, "values", None)
            if values:
                embeddings.append(list(values))
        return embeddings


class NvidiaProvider:
    name = PROVIDER_QWEN

    def _endpoint(self) -> str:
        return f"{settings.NVIDIA_BASE_URL}/v1/chat/completions"

    @staticmethod
    def _normalize_timeout(timeout_s: Optional[float]) -> float:
        try:
            timeout = float(timeout_s) if timeout_s is not None else _NVIDIA_DEFAULT_TIMEOUT_S
        except (TypeError, ValueError):
            timeout = _NVIDIA_DEFAULT_TIMEOUT_S
        if timeout <= 0:
            timeout = _NVIDIA_DEFAULT_TIMEOUT_S
        return timeout

    def generate_text(
        self,
        model: str,
        prompt: str,
        temperature: Optional[float] = None,
        max_output_tokens: Optional[int] = None,
        response_mime_type: Optional[str] = None,
        timeout_s: Optional[float] = None,
    ) -> GenerateResult:
        if not settings.NVIDIA_API_KEY:
            raise RuntimeError("NVIDIA_API_KEY is not configured")

        payload: Dict[str, Any] = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
        }
        if temperature is not None:
            payload["temperature"] = temperature
        if max_output_tokens is not None:
            payload["max_tokens"] = max_output_tokens
        if response_mime_type == "application/json":
            payload["response_format"] = {"type": "json_object"}

        request_data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url=self._endpoint(),
            data=request_data,
            method="POST",
            headers={
                "Authorization": f"Bearer {settings.NVIDIA_API_KEY}",
                "Content-Type": "application/json",
            },
        )

        timeout = self._normalize_timeout(timeout_s)

        try:
            with AI_SERVICE_LATENCY.labels(service="nvidia_qwen", operation="generate").time():
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    raw = resp.read().decode("utf-8")
        except urllib.error.HTTPError as http_err:
            body = ""
            try:
                body = http_err.read().decode("utf-8", errors="replace")
            except Exception:
                body = str(http_err)
            raise RuntimeError(
                f"NVIDIA request failed with HTTP {http_err.code}: {body[:_NVIDIA_MAX_ERROR_BODY_CHARS]}"
            ) from http_err
        except urllib.error.URLError as url_err:
            raise RuntimeError(f"NVIDIA request failed: {url_err}") from url_err

        parsed = json.loads(raw)
        choices = parsed.get("choices") or []
        text = ""
        if choices:
            message = choices[0].get("message") or {}
            text = message.get("content") or ""
            if not isinstance(text, str):
                text = str(text)

        usage = parsed.get("usage") or {}
        usage_metadata = {
            "prompt_tokens": usage.get("prompt_tokens"),
            "completion_tokens": usage.get("completion_tokens"),
            "total_tokens": usage.get("total_tokens"),
        }
        return GenerateResult(
            text=text,
            model_used=model,
            model_tier=MODEL_TIER_FLASH,
            fallback_applied=False,
            usage_metadata=usage_metadata,
            provider_name=self.name,
        )

    def embed_contents(
        self,
        model: str,
        contents: str | List[str],
        task_type: str = "retrieval_document",
        output_dimensionality: int = 768,
        timeout_s: Optional[float] = None,
    ) -> List[List[float]]:
        raise NotImplementedError("NVIDIA provider does not support embedding in this adapter")


_GEMINI_PROVIDER: Optional[LLMProvider] = None
_NVIDIA_PROVIDER: Optional[LLMProvider] = None
_PROVIDER_LOCK = Lock()


def _normalize_provider_hint(provider_hint: Optional[str]) -> str:
    hint = (provider_hint or PROVIDER_GEMINI).strip().lower()
    if hint in {PROVIDER_QWEN, PROVIDER_NVIDIA}:
        return PROVIDER_QWEN
    return PROVIDER_GEMINI


def get_provider(provider_hint: Optional[str] = None) -> LLMProvider:
    global _GEMINI_PROVIDER, _NVIDIA_PROVIDER
    normalized = _normalize_provider_hint(provider_hint)
    with _PROVIDER_LOCK:
        if normalized == PROVIDER_QWEN:
            if _NVIDIA_PROVIDER is None:
                _NVIDIA_PROVIDER = NvidiaProvider()
            return _NVIDIA_PROVIDER
        if _GEMINI_PROVIDER is None:
            _GEMINI_PROVIDER = GeminiProvider()
        return _GEMINI_PROVIDER


def get_model_for_tier(model_tier: str) -> str:
    if model_tier == MODEL_TIER_LITE:
        return settings.LLM_MODEL_LITE
    if model_tier == MODEL_TIER_FLASH:
        return settings.LLM_MODEL_FLASH
    if model_tier == MODEL_TIER_PRO:
        return settings.LLM_MODEL_PRO
    if model_tier == MODEL_TIER_EMBEDDING:
        return settings.EMBEDDING_MODEL_NAME
    return settings.LLM_MODEL_FLASH


def _observe_tokens(task: str, model_tier: str, usage_metadata: Optional[Dict[str, Any]]) -> None:
    if not usage_metadata:
        return
    prompt_tokens = int(
        usage_metadata.get("prompt_token_count")
        or usage_metadata.get("prompt_tokens")
        or 0
    )
    output_tokens = int(
        usage_metadata.get("candidates_token_count")
        or usage_metadata.get("completion_token_count")
        or usage_metadata.get("completion_tokens")
        or 0
    )
    total_tokens = int(
        usage_metadata.get("total_token_count")
        or usage_metadata.get("total_tokens")
        or 0
    )
    if prompt_tokens > 0:
        LLM_TOKENS_TOTAL.labels(task=task, model_tier=model_tier, direction="prompt").inc(prompt_tokens)
    if output_tokens > 0:
        LLM_TOKENS_TOTAL.labels(task=task, model_tier=model_tier, direction="output").inc(output_tokens)
    if total_tokens > 0:
        LLM_TOKENS_TOTAL.labels(task=task, model_tier=model_tier, direction="total").inc(total_tokens)


def _increment_call(task: str, model_tier: str, status: str) -> None:
    LLM_CALLS_TOTAL.labels(task=task, model_tier=model_tier, status=status).inc()


def _increment_provider_call(task: str, provider: str, status: str) -> None:
    LLM_PROVIDER_CALLS_TOTAL.labels(task=task, provider=provider, status=status).inc()


def _increment_fallback(from_provider: str, to_provider: str, reason: str) -> None:
    LLM_FALLBACK_TOTAL.labels(
        from_provider=from_provider,
        to_provider=to_provider,
        reason=reason,
    ).inc()


def is_retryable_llm_error(exc: Exception) -> bool:
    if isinstance(exc, TimeoutError):
        return True

    msg = str(exc).lower()
    retry_markers = (
        "429",
        "resource_exhausted",
        "rate limit",
        "timeout",
        "timed out",
        "deadline",
        "503",
        "502",
        "500",
        "internal error",
        "service unavailable",
        "temporarily unavailable",
    )
    return any(marker in msg for marker in retry_markers)


def _can_use_pro_fallback(fallback_state: Optional[Dict[str, Any]]) -> bool:
    if not settings.LLM_PRO_FALLBACK_ENABLED:
        return False
    if fallback_state is None:
        return settings.LLM_PRO_FALLBACK_MAX_PER_REQUEST > 0
    used = int(fallback_state.get("pro_fallback_used", 0))
    return used < int(settings.LLM_PRO_FALLBACK_MAX_PER_REQUEST)


def _mark_pro_fallback_used(fallback_state: Optional[Dict[str, Any]]) -> None:
    if fallback_state is None:
        return
    fallback_state["pro_fallback_used"] = int(fallback_state.get("pro_fallback_used", 0)) + 1


def _can_use_secondary_fallback(fallback_state: Optional[Dict[str, Any]]) -> bool:
    if fallback_state is None:
        return int(settings.LLM_EXPLORER_SECONDARY_MAX_PER_REQUEST) > 0
    used = int(fallback_state.get("secondary_fallback_used", 0))
    return used < int(settings.LLM_EXPLORER_SECONDARY_MAX_PER_REQUEST)


def _mark_secondary_fallback_used(fallback_state: Optional[Dict[str, Any]]) -> None:
    if fallback_state is None:
        return
    fallback_state["secondary_fallback_used"] = int(fallback_state.get("secondary_fallback_used", 0)) + 1


def _consume_qwen_rpm_slot() -> bool:
    cap = int(getattr(settings, "LLM_EXPLORER_RPM_CAP", 35))
    if cap <= 0:
        return False
    now = time.monotonic()
    cutoff = now - _QWEN_WINDOW_SECONDS
    with _QWEN_RPM_LOCK:
        while _QWEN_RPM_TIMESTAMPS and _QWEN_RPM_TIMESTAMPS[0] < cutoff:
            _QWEN_RPM_TIMESTAMPS.popleft()
        if len(_QWEN_RPM_TIMESTAMPS) >= cap:
            return False
        _QWEN_RPM_TIMESTAMPS.append(now)
        return True


def _resolve_secondary_provider() -> str:
    return _normalize_provider_hint(getattr(settings, "LLM_EXPLORER_FALLBACK_PROVIDER", PROVIDER_GEMINI))


def _resolve_secondary_model(model_tier: str) -> str:
    secondary_provider = _resolve_secondary_provider()
    if secondary_provider == PROVIDER_GEMINI:
        return get_model_for_tier(model_tier)
    return getattr(settings, "LLM_EXPLORER_PRIMARY_MODEL", get_model_for_tier(model_tier))


def _secondary_fallback_generate(
    prompt: str,
    task: str,
    model_tier: str,
    temperature: Optional[float],
    max_output_tokens: Optional[int],
    response_mime_type: Optional[str],
    timeout_s: Optional[float],
    fallback_state: Optional[Dict[str, Any]],
    from_provider: str,
    reason: str,
) -> GenerateResult:
    secondary_provider_hint = _resolve_secondary_provider()
    secondary_model = _resolve_secondary_model(model_tier)
    secondary_provider = get_provider(secondary_provider_hint)
    result = secondary_provider.generate_text(
        model=secondary_model,
        prompt=prompt,
        temperature=temperature,
        max_output_tokens=max_output_tokens,
        response_mime_type=response_mime_type,
        timeout_s=timeout_s,
    )
    result.model_tier = model_tier
    result.fallback_applied = True
    result.secondary_fallback_applied = True
    result.fallback_reason = reason
    result.provider_name = getattr(secondary_provider, "name", secondary_provider_hint)
    _mark_secondary_fallback_used(fallback_state)
    _increment_call(task=task, model_tier=model_tier, status="success")
    _increment_provider_call(task=task, provider=result.provider_name, status="success")
    _increment_fallback(from_provider=from_provider, to_provider=result.provider_name, reason=reason)
    _observe_tokens(task=task, model_tier=model_tier, usage_metadata=result.usage_metadata)
    return result


def _resolve_primary_provider_hint(provider_hint: Optional[str], route_mode: str) -> str:
    if route_mode == ROUTE_MODE_EXPLORER_QWEN_PILOT and settings.LLM_EXPLORER_QWEN_PILOT_ENABLED:
        return _normalize_provider_hint(settings.LLM_EXPLORER_PRIMARY_PROVIDER)
    return _normalize_provider_hint(provider_hint)


def generate_text(
    model: str,
    prompt: str,
    task: str,
    model_tier: str,
    temperature: Optional[float] = None,
    max_output_tokens: Optional[int] = None,
    response_mime_type: Optional[str] = None,
    timeout_s: Optional[float] = None,
    allow_pro_fallback: bool = False,
    fallback_state: Optional[Dict[str, Any]] = None,
    provider_hint: Optional[str] = None,
    route_mode: str = ROUTE_MODE_DEFAULT,
    allow_secondary_fallback: bool = False,
) -> GenerateResult:
    primary_provider_hint = _resolve_primary_provider_hint(provider_hint, route_mode)

    if (
        route_mode == ROUTE_MODE_EXPLORER_QWEN_PILOT
        and primary_provider_hint == PROVIDER_QWEN
        and settings.LLM_EXPLORER_QWEN_PILOT_ENABLED
    ):
        if not _consume_qwen_rpm_slot():
            if allow_secondary_fallback and _can_use_secondary_fallback(fallback_state):
                return _secondary_fallback_generate(
                    prompt=prompt,
                    task=task,
                    model_tier=model_tier,
                    temperature=temperature,
                    max_output_tokens=max_output_tokens,
                    response_mime_type=response_mime_type,
                    timeout_s=timeout_s,
                    fallback_state=fallback_state,
                    from_provider=PROVIDER_QWEN,
                    reason="qwen_rpm_cap",
                )
            raise RuntimeError("Qwen RPM cap reached and secondary fallback is disabled")

    provider = get_provider(primary_provider_hint)
    provider_name = getattr(provider, "name", primary_provider_hint)

    try:
        result = provider.generate_text(
            model=model,
            prompt=prompt,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
            response_mime_type=response_mime_type,
            timeout_s=timeout_s,
        )
        result.model_tier = model_tier
        result.provider_name = provider_name
        _increment_call(task=task, model_tier=model_tier, status="success")
        _increment_provider_call(task=task, provider=provider_name, status="success")
        _observe_tokens(task=task, model_tier=model_tier, usage_metadata=result.usage_metadata)
        return result
    except Exception as exc:
        _increment_call(task=task, model_tier=model_tier, status="error")
        _increment_provider_call(task=task, provider=provider_name, status="error")

        if (
            provider_name == PROVIDER_GEMINI
            and allow_pro_fallback
            and model_tier == MODEL_TIER_FLASH
            and is_retryable_llm_error(exc)
            and _can_use_pro_fallback(fallback_state)
        ):
            logger.warning("Flash model failed with retryable error; using Pro fallback", exc_info=True)
            _mark_pro_fallback_used(fallback_state)
            pro_model = get_model_for_tier(MODEL_TIER_PRO)
            pro_result = provider.generate_text(
                model=pro_model,
                prompt=prompt,
                temperature=temperature,
                max_output_tokens=max_output_tokens,
                response_mime_type=response_mime_type,
                timeout_s=timeout_s,
            )
            pro_result.model_tier = MODEL_TIER_PRO
            pro_result.fallback_applied = True
            pro_result.provider_name = provider_name
            pro_result.fallback_reason = "gemini_pro_fallback"
            _increment_call(task=task, model_tier=MODEL_TIER_PRO, status="success")
            _increment_provider_call(task=task, provider=provider_name, status="success")
            _increment_fallback(
                from_provider=provider_name,
                to_provider=provider_name,
                reason="gemini_flash_to_pro",
            )
            _observe_tokens(task=task, model_tier=MODEL_TIER_PRO, usage_metadata=pro_result.usage_metadata)
            return pro_result

        if (
            route_mode == ROUTE_MODE_EXPLORER_QWEN_PILOT
            and provider_name == PROVIDER_QWEN
            and allow_secondary_fallback
            and is_retryable_llm_error(exc)
            and _can_use_secondary_fallback(fallback_state)
        ):
            logger.warning("Qwen primary failed with retryable error; using secondary fallback", exc_info=True)
            return _secondary_fallback_generate(
                prompt=prompt,
                task=task,
                model_tier=model_tier,
                temperature=temperature,
                max_output_tokens=max_output_tokens,
                response_mime_type=response_mime_type,
                timeout_s=timeout_s,
                fallback_state=fallback_state,
                from_provider=PROVIDER_QWEN,
                reason="qwen_retryable_error",
            )

        raise




def embed_contents(
    model: str,
    contents: str | List[str],
    task_type: str = "retrieval_document",
    output_dimensionality: int = 768,
    timeout_s: Optional[float] = None,
    task: str = "embedding",
) -> List[List[float]]:
    provider = get_provider(PROVIDER_GEMINI)
    try:
        vectors = provider.embed_contents(
            model=model,
            contents=contents,
            task_type=task_type,
            output_dimensionality=output_dimensionality,
            timeout_s=timeout_s,
        )
        _increment_call(task=task, model_tier=MODEL_TIER_EMBEDDING, status="success")
        _increment_provider_call(task=task, provider=PROVIDER_GEMINI, status="success")
        return vectors
    except Exception:
        _increment_call(task=task, model_tier=MODEL_TIER_EMBEDDING, status="error")
        _increment_provider_call(task=task, provider=PROVIDER_GEMINI, status="error")
        raise
