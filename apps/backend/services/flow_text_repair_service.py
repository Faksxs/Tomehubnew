# -*- coding: utf-8 -*-
"""
Layer 4 Flow Text Repair Service
================================
Deterministic, display-time text repair for Flow cards.
"""

from __future__ import annotations

import hashlib
import logging
import re
import threading
import time
from collections import OrderedDict
from difflib import SequenceMatcher
from typing import Optional, Set

import ftfy

from config import settings
from services.correction_service import LinguisticCorrectionService
from services.monitoring import (
    FLOW_TEXT_REPAIR_APPLIED_TOTAL,
    FLOW_TEXT_REPAIR_HIGH_DELTA_REJECT_TOTAL,
    FLOW_TEXT_REPAIR_LATENCY_SECONDS,
    FLOW_TEXT_REPAIR_SKIPPED_TOTAL,
)

logger = logging.getLogger(__name__)

DEFAULT_FLOW_REPAIR_SOURCE_TYPES = {"PDF", "EPUB", "PDF_CHUNK", "ARTICLE", "WEBSITE"}


def _parse_source_types(raw: Optional[str]) -> Set[str]:
    if not raw:
        return set(DEFAULT_FLOW_REPAIR_SOURCE_TYPES)
    values = [str(x).strip().upper() for x in str(raw).split(",")]
    parsed = {v for v in values if v}
    return parsed or set(DEFAULT_FLOW_REPAIR_SOURCE_TYPES)


class _HashLruCache:
    """Small thread-safe LRU cache keyed by content hash."""

    def __init__(self, max_size: int = 10000):
        self.max_size = max(1, int(max_size))
        self._items: "OrderedDict[str, str]" = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: str) -> Optional[str]:
        with self._lock:
            value = self._items.get(key)
            if value is None:
                return None
            self._items.move_to_end(key)
            return value

    def set(self, key: str, value: str) -> None:
        with self._lock:
            self._items[key] = value
            self._items.move_to_end(key)
            while len(self._items) > self.max_size:
                self._items.popitem(last=False)


class FlowTextRepairService:
    """
    Deterministic repair for Flow card text.
    """

    def __init__(
        self,
        *,
        enabled: Optional[bool] = None,
        source_types: Optional[Set[str]] = None,
        max_delta_ratio: Optional[float] = None,
        max_input_chars: Optional[int] = None,
        ruleset_version: Optional[str] = None,
        cache_max_size: int = 10000,
    ):
        self.enabled = settings.FLOW_TEXT_REPAIR_ENABLED if enabled is None else bool(enabled)
        self.source_types = (
            set(settings.FLOW_TEXT_REPAIR_SOURCE_TYPES)
            if source_types is None
            else {str(v).upper() for v in source_types}
        )
        if not self.source_types:
            self.source_types = set(DEFAULT_FLOW_REPAIR_SOURCE_TYPES)
        self.max_delta_ratio = (
            settings.FLOW_TEXT_REPAIR_MAX_DELTA_RATIO
            if max_delta_ratio is None
            else float(max_delta_ratio)
        )
        self.max_input_chars = (
            settings.FLOW_TEXT_REPAIR_MAX_INPUT_CHARS
            if max_input_chars is None
            else int(max_input_chars)
        )
        self.ruleset_version = (
            settings.FLOW_TEXT_REPAIR_RULESET_VERSION
            if ruleset_version is None
            else str(ruleset_version).strip()
        ) or "tr_flow_v1"

        self._corrector = LinguisticCorrectionService()
        self._cache = _HashLruCache(max_size=cache_max_size)

    def repair_for_flow_card(self, text: str, source_type: str) -> str:
        source = str(source_type or "").strip().upper()
        original = "" if text is None else str(text)

        if not self.enabled:
            FLOW_TEXT_REPAIR_SKIPPED_TOTAL.labels(source_type=source or "UNKNOWN", reason="disabled").inc()
            return original

        if source not in self.source_types:
            FLOW_TEXT_REPAIR_SKIPPED_TOTAL.labels(source_type=source or "UNKNOWN", reason="source_not_allowed").inc()
            return original

        length = len(original)
        if length < 30:
            FLOW_TEXT_REPAIR_SKIPPED_TOTAL.labels(source_type=source, reason="too_short").inc()
            return original
        if length > self.max_input_chars:
            FLOW_TEXT_REPAIR_SKIPPED_TOTAL.labels(source_type=source, reason="too_long").inc()
            return original

        cache_key = self._build_cache_key(original, source)
        cached = self._cache.get(cache_key)
        if cached is not None:
            FLOW_TEXT_REPAIR_SKIPPED_TOTAL.labels(source_type=source, reason="cache_hit").inc()
            return cached

        start_time = time.time()
        try:
            repaired = self._apply_pipeline(original)
            repaired = self._normalize_spacing_and_punctuation(repaired)

            if not repaired:
                FLOW_TEXT_REPAIR_SKIPPED_TOTAL.labels(source_type=source, reason="empty_after_repair").inc()
                self._cache.set(cache_key, original)
                return original

            delta_ratio = self._delta_ratio(original, repaired)
            if delta_ratio > self.max_delta_ratio:
                FLOW_TEXT_REPAIR_HIGH_DELTA_REJECT_TOTAL.labels(source_type=source).inc()
                self._cache.set(cache_key, original)
                return original

            if repaired != original:
                FLOW_TEXT_REPAIR_APPLIED_TOTAL.labels(
                    source_type=source,
                    ruleset=self.ruleset_version,
                ).inc()
            else:
                FLOW_TEXT_REPAIR_SKIPPED_TOTAL.labels(source_type=source, reason="no_change").inc()

            self._cache.set(cache_key, repaired)
            return repaired
        except Exception:
            FLOW_TEXT_REPAIR_SKIPPED_TOTAL.labels(source_type=source, reason="error").inc()
            logger.exception("Flow text repair failed")
            self._cache.set(cache_key, original)
            return original
        finally:
            FLOW_TEXT_REPAIR_LATENCY_SECONDS.labels(
                source_type=source or "UNKNOWN",
                ruleset=self.ruleset_version,
            ).observe(time.time() - start_time)

    def _build_cache_key(self, text: str, source_type: str) -> str:
        hasher = hashlib.sha1()
        hasher.update(self.ruleset_version.encode("utf-8", errors="ignore"))
        hasher.update(b"|")
        hasher.update(source_type.encode("utf-8", errors="ignore"))
        hasher.update(b"|")
        hasher.update(str(len(text)).encode("ascii", errors="ignore"))
        hasher.update(b"|")
        hasher.update(text.encode("utf-8", errors="ignore"))
        return hasher.hexdigest()

    @staticmethod
    def _repair_hyphenation(text: str) -> str:
        # Join words broken by line-wrap hyphenation.
        # Case 1: Standard hyphen + newline (e.g. "word-\n suffix")
        text = re.sub(r"(\w)-\s*\n\s*(\w)", r"\1\2", text, flags=re.UNICODE)
        # Case 2: Hyphen + space without newline (bad OCR strip) -> "word- suffix"
        text = re.sub(r"(\w+)- (?=[a-zğüşiöç])", r"\1", text)
        
        # Replace remaining hard line breaks with spaces.
        text = re.sub(r"\s*\n+\s*", " ", text)
        return text

    @staticmethod
    def _repair_ocr_artifacts(text: str) -> str:
        """Fix common Turkish OCR errors (0 vs O, 1 vs I, etc)"""
        if not text: return text
        
        # 1. Case-Insensitive Rules
        ci_replacements = [
            (r'\bgPnOmuz\b', 'günümüz'),
            (r'\bgOnOmuz\b', 'günümüz'),
            (r'\bgonomuz\b', 'günümüz'),
            (r'\bg[O0]n\b', 'gün'),
            (r'\bb[O0]t[O0]n\b', 'bütün'),
            (r'\bg[O0]z\b', 'göz'),
            (r'\bk[O0]lt[O0]r\b', 'kültür'),
            # Spacing fix: "BEST E" -> "BESTE" (Specific word)
            (r'\b(BEST)\s(E)\b', r'\1\2'),
        ]
        
        for pattern, replacement in ci_replacements:
            text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)

        # 2. Case-Sensitive Rules (Strict)
        cs_replacements = [
            # 1 -> ı fixer (mid-word, lower case context)
            (r'(?<=[a-z])1(?=[a-z])', 'ı'),
            # Spacing fix: "DÜ ŞÜNCE" -> "DÜŞÜNCE" (Only between Uppercase)
            (r'(?<=[A-ZĞÜŞİÖÇ])\s(?=[A-ZĞÜŞİÖÇ])', ''), 
        ]

        for pattern, replacement in cs_replacements:
            text = re.sub(pattern, replacement, text)
            
        return text

    @staticmethod
    def _normalize_spacing_and_punctuation(text: str) -> str:
        text = re.sub(r"\s+", " ", text)
        text = re.sub(r"\s+([,;:.!?])", r"\1", text)
        text = re.sub(r"([,;:.!?])([^\s\"'\)\]\}])", r"\1 \2", text)
        text = re.sub(r"([!?.,])\1{2,}", r"\1", text)
        return text.strip()

    @staticmethod
    def _delta_ratio(original: str, candidate: str) -> float:
        if original == candidate:
            return 0.0
        similarity = SequenceMatcher(None, original, candidate).ratio()
        return max(0.0, 1.0 - similarity)

    def _apply_pipeline(self, text: str) -> str:
        candidate = ftfy.fix_text(text)
        candidate = self._repair_hyphenation(candidate)
        candidate = self._repair_ocr_artifacts(candidate)
        candidate = self._corrector.fix_text(candidate)
        return candidate


_default_service = FlowTextRepairService(
    enabled=settings.FLOW_TEXT_REPAIR_ENABLED,
    source_types=_parse_source_types(",".join(settings.FLOW_TEXT_REPAIR_SOURCE_TYPES)),
    max_delta_ratio=settings.FLOW_TEXT_REPAIR_MAX_DELTA_RATIO,
    max_input_chars=settings.FLOW_TEXT_REPAIR_MAX_INPUT_CHARS,
    ruleset_version=settings.FLOW_TEXT_REPAIR_RULESET_VERSION,
)


def repair_for_flow_card(text: str, source_type: str) -> str:
    return _default_service.repair_for_flow_card(text=text, source_type=source_type)

