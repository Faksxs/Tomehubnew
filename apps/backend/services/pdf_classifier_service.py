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


def _build_sample_page_indexes(page_count: int) -> List[int]:
    if page_count <= 0:
        return []

    sample_target = int(getattr(settings, "PDF_CLASSIFIER_SAMPLE_PAGES", 5) or 5)
    if page_count <= sample_target:
        return list(range(page_count))

    indexes = {0, page_count - 1}
    steps = max(2, sample_target)
    for slot in range(steps):
        fraction = slot / float(max(1, steps - 1))
        indexes.add(int(round((page_count - 1) * fraction)))
    return sorted(indexes)


def _inspect_page(page: Any, page_idx: int, min_chars_per_page: int) -> PdfPagePreflight:
    raw_text = str(page.get_text("text", sort=True) or "")
    char_count = len(raw_text.strip())
    word_count = len(_WORD_RE.findall(raw_text))
    image_count = len(page.get_images(full=True))
    garbled_ratio = _estimate_garbled_ratio(raw_text)
    has_text_layer = char_count >= min_chars_per_page
    image_heavy_suspected = bool(image_count > 0 and char_count < min_chars_per_page)
    return PdfPagePreflight(
        page_number=page_idx + 1,
        has_text_layer=has_text_layer,
        char_count=char_count,
        word_count=word_count,
        ocr_applied=False,
        image_heavy_suspected=image_heavy_suspected,
        garbled_ratio=garbled_ratio,
    )


def _summarize_pages(page_rows: List[PdfPagePreflight], *, page_count: int, file_path: str) -> Dict[str, Any]:
    pages_with_text = sum(1 for page in page_rows if page.has_text_layer)
    blank_pages = sum(1 for page in page_rows if int(page.char_count or 0) == 0)
    image_heavy_pages = sum(1 for page in page_rows if page.image_heavy_suspected)
    total_chars = sum(int(page.char_count or 0) for page in page_rows)
    total_words = sum(int(page.word_count or 0) for page in page_rows)
    total_garbled = sum(float(page.garbled_ratio or 0.0) for page in page_rows)
    divisor = float(max(1, len(page_rows)))
    return {
        "page_count": int(page_count),
        "pages_with_text": pages_with_text,
        "pages_with_text_ratio": round(pages_with_text / divisor, 4),
        "blank_page_ratio": round(blank_pages / divisor, 4),
        "avg_chars_per_page": round(total_chars / divisor, 2),
        "avg_words_per_page": round(total_words / divisor, 2),
        "garbled_ratio": round(total_garbled / divisor, 4),
        "image_heavy_ratio": round(image_heavy_pages / divisor, 4),
        "file_size_bytes": int(os.path.getsize(file_path)),
    }


def _should_early_route_to_ocr(sample_metrics: Dict[str, Any]) -> tuple[bool, str]:
    if not bool(getattr(settings, "PDF_CLASSIFIER_EARLY_OCR_ENABLED", True)):
        return False, ""

    sampled_page_count = int(sample_metrics.get("sampled_page_count", 0) or 0)
    if sampled_page_count < 3:
        return False, ""

    text_ratio = float(sample_metrics.get("pages_with_text_ratio", 0.0) or 0.0)
    blank_ratio = float(sample_metrics.get("blank_page_ratio", 0.0) or 0.0)
    avg_chars = float(sample_metrics.get("avg_chars_per_page", 0.0) or 0.0)
    garbled_ratio = float(sample_metrics.get("garbled_ratio", 0.0) or 0.0)
    image_heavy_ratio = float(sample_metrics.get("image_heavy_ratio", 0.0) or 0.0)

    min_chars = int(getattr(settings, "PDF_TEXT_NATIVE_MIN_CHARS_PER_PAGE", 120))
    strong_text_ratio_max = min(0.20, float(getattr(settings, "PDF_TEXT_NATIVE_TEXT_PAGE_RATIO_MIN", 0.70)) * 0.35)
    strong_avg_chars_max = max(24.0, float(min_chars) * 0.35)
    strong_image_heavy_min = max(0.60, float(getattr(settings, "PDF_TEXT_NATIVE_IMAGE_HEAVY_RATIO_MAX", 0.40)))
    garbled_trigger = max(
        float(getattr(settings, "PDF_RETRY_AS_OCR_GARBLED_RATIO", 0.18)),
        float(getattr(settings, "PDF_TEXT_NATIVE_GARBLED_RATIO_MAX", 0.12)) + 0.08,
    )

    if text_ratio <= 0.0 and avg_chars <= strong_avg_chars_max:
        return True, "sample_no_text"
    if text_ratio <= strong_text_ratio_max and (image_heavy_ratio >= strong_image_heavy_min or blank_ratio >= 0.60):
        return True, "sample_image_heavy"
    if garbled_ratio >= garbled_trigger and avg_chars <= float(min_chars):
        return True, "sample_garbled"
    return False, ""


def _build_placeholder_pages(
    *,
    page_count: int,
    sampled_pages: Dict[int, PdfPagePreflight],
    sampled_metrics: Dict[str, Any],
) -> List[PdfPagePreflight]:
    default_garbled = float(sampled_metrics.get("garbled_ratio", 0.0) or 0.0)
    image_heavy = float(sampled_metrics.get("image_heavy_ratio", 0.0) or 0.0) >= 0.5
    pages: List[PdfPagePreflight] = []
    for page_idx in range(page_count):
        if page_idx in sampled_pages:
            pages.append(sampled_pages[page_idx])
            continue
        pages.append(
            PdfPagePreflight(
                page_number=page_idx + 1,
                has_text_layer=False,
                char_count=0,
                word_count=0,
                ocr_applied=False,
                image_heavy_suspected=image_heavy,
                garbled_ratio=default_garbled,
            )
        )
    return pages


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
    page_count = len(document)
    min_chars_per_page = int(getattr(settings, "PDF_TEXT_NATIVE_MIN_CHARS_PER_PAGE", 120))

    sampled_pages: Dict[int, PdfPagePreflight] = {}
    sample_indexes = _build_sample_page_indexes(page_count)
    for page_idx in sample_indexes:
        sampled_pages[page_idx] = _inspect_page(document.load_page(page_idx), page_idx, min_chars_per_page)

    sample_rows = [sampled_pages[idx] for idx in sample_indexes]
    sample_metrics = _summarize_pages(sample_rows, page_count=page_count, file_path=file_path)
    sample_metrics["sampled_page_count"] = len(sample_rows)
    sample_metrics["sampled_page_numbers"] = [page.page_number for page in sample_rows]

    early_route_to_ocr, early_reason = _should_early_route_to_ocr(sample_metrics)
    if early_route_to_ocr:
        metrics = dict(sample_metrics)
        metrics["route_reason"] = early_reason
        metrics["early_exit_ocr"] = True
        return PdfClassifierResult(
            route="IMAGE_SCAN",
            classifier_metrics=metrics,
            pages=_build_placeholder_pages(
                page_count=page_count,
                sampled_pages=sampled_pages,
                sampled_metrics=sample_metrics,
            ),
        )

    page_rows: List[PdfPagePreflight] = []
    for page_idx in range(page_count):
        page_rows.append(
            sampled_pages.get(page_idx) or _inspect_page(document.load_page(page_idx), page_idx, min_chars_per_page)
        )

    metrics = _summarize_pages(page_rows, page_count=page_count, file_path=file_path)
    metrics["sampled_page_count"] = len(sample_rows)
    metrics["sampled_page_numbers"] = [page.page_number for page in sample_rows]
    metrics["early_exit_ocr"] = False
    route = decide_route(metrics)
    metrics["route_reason"] = "text_layer_strong" if route == "TEXT_NATIVE" else "ocr_default"
    return PdfClassifierResult(route=route, classifier_metrics=metrics, pages=page_rows)
