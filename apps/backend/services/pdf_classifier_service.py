from __future__ import annotations

import os
import re
from dataclasses import asdict, dataclass
from typing import Any, Dict, List

from config import settings


_WORD_RE = re.compile(r"[0-9A-Za-zÀ-ÿĀ-žƀ-ɏ]+", flags=re.UNICODE)
_GARBLED_RE = re.compile(r"(?:�|Ã|Â|[\x00-\x08\x0B\x0C\x0E-\x1F])")


@dataclass
class PdfPagePreflight:
    page_number: int
    has_text_layer: bool
    char_count: int
    word_count: int
    ocr_applied: bool
    image_heavy_suspected: bool
    garbled_ratio: float


@dataclass
class PdfClassifierResult:
    route: str
    classifier_metrics: Dict[str, Any]
    pages: List[PdfPagePreflight]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "route": self.route,
            "classifier_metrics": dict(self.classifier_metrics or {}),
            "pages": [asdict(page) for page in self.pages],
        }


def _estimate_garbled_ratio(text: str) -> float:
    raw = str(text or "")
    words = max(1, len(_WORD_RE.findall(raw)))
    suspicious = len(_GARBLED_RE.findall(raw))
    isolated_letters = len(re.findall(r"\b[A-Za-z]\b", raw))
    ratio = (suspicious + isolated_letters) / float(words)
    return round(min(1.0, ratio), 4)


def decide_route(metrics: Dict[str, Any]) -> str:
    pages = int(metrics.get("page_count", 0) or 0)
    if pages <= 0:
        return "IMAGE_SCAN"

    pages_with_text_ratio = float(metrics.get("pages_with_text_ratio", 0.0) or 0.0)
    avg_chars_per_page = float(metrics.get("avg_chars_per_page", 0.0) or 0.0)
    blank_page_ratio = float(metrics.get("blank_page_ratio", 1.0) or 1.0)
    garbled_ratio = float(metrics.get("garbled_ratio", 1.0) or 1.0)
    image_heavy_ratio = float(metrics.get("image_heavy_ratio", 1.0) or 1.0)

    text_ratio_threshold = float(getattr(settings, "PDF_TEXT_NATIVE_TEXT_PAGE_RATIO_MIN", 0.70))
    chars_threshold = int(getattr(settings, "PDF_TEXT_NATIVE_MIN_CHARS_PER_PAGE", 120))
    blank_ratio_threshold = float(getattr(settings, "PDF_TEXT_NATIVE_BLANK_PAGE_RATIO_MAX", 0.20))
    garbled_ratio_threshold = float(getattr(settings, "PDF_TEXT_NATIVE_GARBLED_RATIO_MAX", 0.12))
    image_heavy_threshold = float(getattr(settings, "PDF_TEXT_NATIVE_IMAGE_HEAVY_RATIO_MAX", 0.40))

    if (
        pages_with_text_ratio >= text_ratio_threshold
        and avg_chars_per_page >= chars_threshold
        and blank_page_ratio <= blank_ratio_threshold
        and garbled_ratio <= garbled_ratio_threshold
        and image_heavy_ratio <= image_heavy_threshold
    ):
        return "TEXT_NATIVE"
    return "IMAGE_SCAN"


def _require_pymupdf():
    try:
        import fitz  # type: ignore
    except Exception as exc:  # pragma: no cover - import guard
        raise RuntimeError("PyMuPDF is required for PDF Ingestion V2 text-native routing") from exc
    return fitz


def classify_pdf(file_path: str) -> PdfClassifierResult:
    if not os.path.exists(file_path):
        raise FileNotFoundError(file_path)

    fitz = _require_pymupdf()
    document = fitz.open(file_path)
    page_rows: List[PdfPagePreflight] = []
    total_chars = 0
    total_words = 0
    total_garbled = 0.0
    pages_with_text = 0
    blank_pages = 0
    image_heavy_pages = 0

    min_chars_per_page = int(getattr(settings, "PDF_TEXT_NATIVE_MIN_CHARS_PER_PAGE", 120))

    for page_idx in range(len(document)):
        page = document.load_page(page_idx)
        raw_text = str(page.get_text("text", sort=True) or "")
        char_count = len(raw_text.strip())
        word_count = len(_WORD_RE.findall(raw_text))
        image_count = len(page.get_images(full=True))
        garbled_ratio = _estimate_garbled_ratio(raw_text)
        has_text_layer = char_count >= min_chars_per_page
        image_heavy_suspected = bool(image_count > 0 and char_count < min_chars_per_page)

        if has_text_layer:
            pages_with_text += 1
        if char_count == 0:
            blank_pages += 1
        if image_heavy_suspected:
            image_heavy_pages += 1

        total_chars += char_count
        total_words += word_count
        total_garbled += garbled_ratio
        page_rows.append(
            PdfPagePreflight(
                page_number=page_idx + 1,
                has_text_layer=has_text_layer,
                char_count=char_count,
                word_count=word_count,
                ocr_applied=False,
                image_heavy_suspected=image_heavy_suspected,
                garbled_ratio=garbled_ratio,
            )
        )

    page_count = len(page_rows)
    metrics = {
        "page_count": page_count,
        "pages_with_text": pages_with_text,
        "pages_with_text_ratio": round((pages_with_text / float(page_count)) if page_count else 0.0, 4),
        "blank_page_ratio": round((blank_pages / float(page_count)) if page_count else 0.0, 4),
        "avg_chars_per_page": round((total_chars / float(page_count)) if page_count else 0.0, 2),
        "avg_words_per_page": round((total_words / float(page_count)) if page_count else 0.0, 2),
        "garbled_ratio": round((total_garbled / float(page_count)) if page_count else 0.0, 4),
        "image_heavy_ratio": round((image_heavy_pages / float(page_count)) if page_count else 0.0, 4),
        "file_size_bytes": int(os.path.getsize(file_path)),
    }
    route = decide_route(metrics)
    metrics["route_reason"] = "text_layer_strong" if route == "TEXT_NATIVE" else "ocr_default"
    return PdfClassifierResult(route=route, classifier_metrics=metrics, pages=page_rows)
