
import logging
import os
import re
from typing import Any, Dict
from dotenv import load_dotenv
from config import settings
from services.llm_client import (
    MODEL_TIER_FLASH,
    PROVIDER_QWEN,
    ROUTE_MODE_EXPLORER_QWEN_PILOT,
    generate_text,
    get_model_for_tier,
)

# Load environment (legacy compatibility for standalone scripts)
env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '.env')
load_dotenv(dotenv_path=env_path)

logger = logging.getLogger(__name__)

class DataCleanerService:
    """
    Service to remove repetitive metadata, ISBNs, and headers/footers from content.
    """
    
    @staticmethod
    def strip_basic_patterns(text: str) -> str:
        """
        Fast regex-based cleaning for common artifacts.
        """
        if not text:
            return ""
            
        # 1. Remove ISBNs
        text = re.sub(r'ISBN(?:-10|-13)?:\s*[\d\-X]+', '', text, flags=re.IGNORECASE)
        
        # 2. Remove common URLs
        text = re.sub(r'www\.[a-z0-9\-]+\.[a-z]{2,}(?:\.[a-z]{2,})?', '', text, flags=re.IGNORECASE)
        
        # 3. Remove consecutive spaces
        text = re.sub(r'\s+', ' ', text).strip()
        
        return text

    @staticmethod
    def assess_noise(text: str, title: str = "", author: str = "") -> Dict[str, Any]:
        """
        Cheap heuristic noise detector for deciding whether AI cleaning is worth it.
        Returns a structured dict with score and signal counts.
        """
        if not text:
            return {"score": 0, "signals": {}, "reasons": []}

        raw = text
        lowered = raw.lower()
        stripped = DataCleanerService.strip_basic_patterns(raw)
        signals: Dict[str, int | float] = {}
        reasons: list[str] = []

        isbn_count = len(DataCleanerService._ISBN_RE.findall(raw))
        url_count = len(DataCleanerService._URL_RE.findall(raw))
        page_artifact_count = len(DataCleanerService._PAGE_ARTIFACT_RE.findall(raw))
        biblio_markers = len(DataCleanerService._BIBLIO_MARKER_RE.findall(raw))

        title_hits = 0
        author_hits = 0
        if title:
            t = str(title).strip().lower()
            if len(t) >= 4:
                title_hits = lowered.count(t)
        if author:
            a = str(author).strip().lower()
            if len(a) >= 4:
                author_hits = lowered.count(a)

        # Repeated short lines are common OCR/header/footer artifacts.
        lines = [ln.strip().lower() for ln in raw.splitlines() if ln.strip()]
        short_lines = [ln for ln in lines if 3 <= len(ln) <= 80]
        repeated_short_line_count = 0
        if short_lines:
            counts: Dict[str, int] = {}
            for ln in short_lines:
                counts[ln] = counts.get(ln, 0) + 1
            repeated_short_line_count = sum(1 for c in counts.values() if c >= 2)

        uppercase_ratio = 0.0
        letters = [ch for ch in raw if ch.isalpha()]
        if letters:
            uppercase_ratio = sum(1 for ch in letters if ch.isupper()) / max(1, len(letters))

        delta_ratio = 0.0
        if raw:
            delta_ratio = max(0.0, (len(raw) - len(stripped)) / max(1, len(raw)))

        score = 0
        score += min(isbn_count, 3) * 3
        score += min(url_count, 3) * 2
        score += min(page_artifact_count, 5) * 2
        score += min(biblio_markers, 3) * 3
        score += min(max(title_hits - 1, 0), 4) * 2
        score += min(max(author_hits - 1, 0), 4) * 2
        score += min(repeated_short_line_count, 5) * 2
        if uppercase_ratio >= 0.45 and len(raw) >= 120:
            score += 1
        if delta_ratio >= 0.08:
            score += 1
        if delta_ratio >= 0.18:
            score += 2

        if isbn_count:
            reasons.append("isbn")
        if url_count:
            reasons.append("url")
        if page_artifact_count:
            reasons.append("page_artifact")
        if biblio_markers:
            reasons.append("biblio_marker")
        if title_hits >= 2:
            reasons.append("title_repeat")
        if author_hits >= 2:
            reasons.append("author_repeat")
        if repeated_short_line_count:
            reasons.append("repeated_short_lines")

        signals["isbn_count"] = isbn_count
        signals["url_count"] = url_count
        signals["page_artifact_count"] = page_artifact_count
        signals["biblio_markers"] = biblio_markers
        signals["title_hits"] = title_hits
        signals["author_hits"] = author_hits
        signals["repeated_short_line_count"] = repeated_short_line_count
        signals["uppercase_ratio"] = round(uppercase_ratio, 3)
        signals["strip_delta_ratio"] = round(delta_ratio, 3)

        return {"score": int(score), "signals": signals, "reasons": reasons}

    @staticmethod
    def should_use_ai(text: str, title: str = "", author: str = "", threshold: int | None = None) -> tuple[bool, Dict[str, Any]]:
        assessment = DataCleanerService.assess_noise(text, title=title, author=author)
        if threshold is None:
            threshold = int(getattr(settings, "INGESTION_DATA_CLEANER_NOISE_THRESHOLD", 4) or 4)
        return (int(assessment.get("score", 0)) >= int(threshold), assessment)

    @staticmethod
    def clean_with_ai(text: str, title: str = "", author: str = "") -> str:
        """
        Deep cleaning using Gemini to remove book headers/footers.
        """
        base_text = DataCleanerService.strip_basic_patterns(text)
        min_chars = int(getattr(settings, "INGESTION_DATA_CLEANER_MIN_CHARS_FOR_AI", 180) or 180)
        if not settings.GEMINI_API_KEY or not base_text or len(base_text) < min_chars:
            return base_text

        # Keep prompt compact. The large cost driver is still chunk volume, not instructions.
        prompt = (
            "Clean the text by removing repetitive metadata/header/footer clutter only.\n"
            f"Title: {title}\n"
            f"Author: {author}\n"
            "Rules: keep body content, do not summarize, remove repeated title/author, page markers, ISBN, publisher clutter, bibliography/index lists.\n"
            "Return only cleaned text.\n\n"
            f"TEXT:\n{base_text}"
        )

        try:
            model = get_model_for_tier(MODEL_TIER_FLASH)
            result = generate_text(
                model=model,
                prompt=prompt,
                task="data_cleaner",
                model_tier=MODEL_TIER_FLASH,
                timeout_s=20.0,
                provider_hint=PROVIDER_QWEN,
                route_mode=ROUTE_MODE_EXPLORER_QWEN_PILOT,
                allow_secondary_fallback=True,
                fallback_state={"secondary_fallback_used": 0},
            )
            if result and result.text:
                cleaned = result.text.strip()
                # Safety net: avoid severe truncation or empty outputs.
                if len(cleaned) >= max(40, int(len(base_text) * 0.30)):
                    return cleaned
                logger.warning(
                    "data_cleaner AI output too short; falling back to rule-based cleaned text",
                    extra={"in_len": len(base_text), "out_len": len(cleaned)},
                )
        except Exception:
            logger.debug("data_cleaner AI cleaning failed; using rule-based cleaned text", exc_info=True)

        return base_text
    _PAGE_ARTIFACT_RE = re.compile(
        r"(?:^|\b)(?:sayfa|page)\s*\d{1,4}(?:\s*/\s*\d{1,4})?(?:\b|$)|^\s*\d{1,4}\s*$",
        flags=re.IGNORECASE | re.MULTILINE,
    )
    _BIBLIO_MARKER_RE = re.compile(
        r"\b(?:kaynakça|references|bibliography|index|dizin)\b",
        flags=re.IGNORECASE,
    )
    _URL_RE = re.compile(r"(?:https?://|www\.)\S+", flags=re.IGNORECASE)
    _ISBN_RE = re.compile(r"\bISBN(?:-10|-13)?[:\s]*[\dXx\-]{8,20}\b", flags=re.IGNORECASE)
