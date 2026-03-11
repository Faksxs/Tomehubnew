from __future__ import annotations

from difflib import SequenceMatcher
import ftfy
import logging
from rapidfuzz import fuzz, process
import re

logger = logging.getLogger(__name__)


class LinguisticCorrectionService:
    RULE_VERSION = "tr_ocr_v2_safe"
    MAX_DELTA_RATIO = 0.22

    # Keep only high-confidence targeted repairs. Avoid generic catch-all
    # replacements that can damage already-correct body text.
    REGEX_RULES = [
        (r"\bgPnOmuz\b", "g\u00fcn\u00fcm\u00fcz"),
        (r"\bgOnOmuz\b", "g\u00fcn\u00fcm\u00fcz"),
        (r"\bgonomuz\b", "g\u00fcn\u00fcm\u00fcz"),
        (r"\bg[O0]n\b", "g\u00fcn"),
        (r"\bb[O0]t[O0]n\b", "b\u00fct\u00fcn"),
        (r"\bg[O0]z\b", "g\u00f6z"),
        (r"\bk[O0]lt[O0]r\b", "k\u00fclt\u00fcr"),
        (r"\b~ok\b", "\u00e7ok"),
        (r"\bi~in\b", "i\u00e7in"),
        (r"\bi~inde\b", "i\u00e7inde"),
        (r"([a-z])1\b", "\\1\u0131"),
    ]

    def __init__(self):
        self.valid_words = set()
        self._load_bootstrap_dictionary()

    def _load_bootstrap_dictionary(self) -> None:
        bootstrap_words = """
        günümüz
        kültür
        bütün
        göz
        hayat
        anlam
        insan
        felsefe
        toplum
        çalışma
        bağlı
        olarak
        bir
        bu
        var
        yok
        için
        """
        self.valid_words = {w.strip() for w in bootstrap_words.strip().split() if w.strip()}

    def fix_text(self, text: str) -> str:
        if not text:
            return ""

        original = str(text)
        candidate = ftfy.fix_text(original)
        candidate = re.sub(r"(\w+)-\s*\n\s*([a-zğüşiöç]+)", r"\1\2\n", candidate)

        for pattern, replacement in self.REGEX_RULES:
            candidate = re.sub(pattern, replacement, candidate, flags=re.IGNORECASE)

        if self._delta_ratio(original, candidate) > self.MAX_DELTA_RATIO:
            logger.debug("Linguistic correction skipped due to high delta ratio")
            return ftfy.fix_text(original)

        return candidate

    def verify_word(self, word: str):
        return process.extractOne(word, self.valid_words, scorer=fuzz.ratio)

    @staticmethod
    def _delta_ratio(original: str, candidate: str) -> float:
        if original == candidate:
            return 0.0
        similarity = SequenceMatcher(None, str(original or ""), str(candidate or "")).ratio()
        return max(0.0, 1.0 - similarity)
