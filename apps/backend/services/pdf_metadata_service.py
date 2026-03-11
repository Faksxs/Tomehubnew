from __future__ import annotations

import logging
import re
from typing import Any, Dict, Optional

from services.ai_service import extract_metadata_from_text_async
from utils.text_utils import repair_common_mojibake

logger = logging.getLogger(__name__)


def _open_pymupdf_document(pdf_path: str):
    try:
        import fitz  # type: ignore
    except Exception as exc:  # pragma: no cover - optional dependency
        raise RuntimeError("PyMuPDF is required for PDF metadata extraction") from exc
    return fitz.open(pdf_path)


def _clean_metadata_value(value: Any) -> Optional[str]:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text or None


def _extract_embedded_metadata(document: Any) -> Dict[str, Optional[str]]:
    raw = getattr(document, "metadata", None) or {}
    return {
        "title": _clean_metadata_value(raw.get("title")),
        "author": _clean_metadata_value(raw.get("author")),
    }


def _extract_first_page_text(document: Any) -> str:
    if len(document) <= 0:
        return ""
    page = document.load_page(0)
    raw_text = str(page.get_text("text", sort=True) or "").strip()
    if not raw_text:
        return ""
    return repair_common_mojibake(raw_text)


async def get_pdf_metadata(pdf_path: str) -> Dict[str, Any]:
    """
    Active PDF metadata extraction path for `/api/extract-metadata`.

    Uses PyMuPDF for page count + first page text and the existing AI metadata
    extractor for title/author enrichment. This path intentionally avoids the
    legacy OCI Document Understanding pipeline.
    """
    metadata: Dict[str, Any] = {
        "title": None,
        "author": None,
        "page_count": 0,
    }

    document = None
    try:
        document = _open_pymupdf_document(pdf_path)
        metadata["page_count"] = int(len(document))

        embedded = _extract_embedded_metadata(document)
        metadata["title"] = embedded.get("title")
        metadata["author"] = embedded.get("author")

        first_page_text = _extract_first_page_text(document)
        if len(first_page_text.strip()) >= 40:
            ai_meta = await extract_metadata_from_text_async(first_page_text[:4000])
            ai_title = _clean_metadata_value(ai_meta.get("title")) if isinstance(ai_meta, dict) else None
            ai_author = _clean_metadata_value(ai_meta.get("author")) if isinstance(ai_meta, dict) else None
            if ai_title:
                metadata["title"] = ai_title
            if ai_author:
                metadata["author"] = ai_author

        return metadata
    except Exception as exc:
        logger.error("Active PDF metadata extraction failed: %s", exc)
        return metadata
    finally:
        if document is not None:
            try:
                document.close()
            except Exception:
                pass
