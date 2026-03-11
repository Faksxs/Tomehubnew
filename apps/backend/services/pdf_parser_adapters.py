from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

import requests

from config import settings
from services.canonical_document_service import (
    CanonicalBlock,
    CanonicalDocument,
    CanonicalPage,
    build_document,
)
from services.chunk_quality_audit_service import looks_like_heading
from services.pdf_classifier_service import PdfClassifierResult

try:  # pragma: no cover - optional dependency import guard
    from llama_cloud import LlamaCloud
except Exception:  # pragma: no cover - dependency may be absent in some test envs
    LlamaCloud = None


def _parse_language_values(raw: Any) -> List[str]:
    parts = [part.strip() for part in str(raw or "").split(",") if part and part.strip()]
    return parts or ["tr"]


def _normalize_bbox(bbox: Any) -> Optional[Dict[str, float]]:
    if bbox is None:
        return None
    if isinstance(bbox, list) and bbox and all(isinstance(item, dict) for item in bbox):
        x0 = min(float(item.get("x", item.get("x0", 0.0)) or 0.0) for item in bbox)
        y0 = min(float(item.get("y", item.get("y0", 0.0)) or 0.0) for item in bbox)
        x1 = max(
            float(item.get("x1", (float(item.get("x", 0.0) or 0.0) + float(item.get("w", 0.0) or 0.0))) or 0.0)
            for item in bbox
        )
        y1 = max(
            float(item.get("y1", (float(item.get("y", 0.0) or 0.0) + float(item.get("h", 0.0) or 0.0))) or 0.0)
            for item in bbox
        )
        return {"x0": x0, "y0": y0, "x1": x1, "y1": y1}
    if isinstance(bbox, (list, tuple)) and len(bbox) >= 4:
        return {
            "x0": float(bbox[0]),
            "y0": float(bbox[1]),
            "x1": float(bbox[2]),
            "y1": float(bbox[3]),
        }
    if isinstance(bbox, dict):
        return {
            "x0": float(bbox.get("x0", 0.0) or 0.0),
            "y0": float(bbox.get("y0", 0.0) or 0.0),
            "x1": float(bbox.get("x1", 0.0) or 0.0),
            "y1": float(bbox.get("y1", 0.0) or 0.0),
        }
    if hasattr(bbox, "x") and hasattr(bbox, "y") and hasattr(bbox, "w") and hasattr(bbox, "h"):
        x0 = float(getattr(bbox, "x", 0.0) or 0.0)
        y0 = float(getattr(bbox, "y", 0.0) or 0.0)
        return {
            "x0": x0,
            "y0": y0,
            "x1": x0 + float(getattr(bbox, "w", 0.0) or 0.0),
            "y1": y0 + float(getattr(bbox, "h", 0.0) or 0.0),
        }
    return None


def _detect_block_type(text: str) -> str:
    value = str(text or "").strip()
    if not value:
        return "body"
    lowered = value.lower()
    if looks_like_heading(value):
        return "heading"
    if value.startswith((">", '"', "'")):
        return "quote"
    if "\t" in value or ("  " in value and any(ch.isdigit() for ch in value)):
        return "table"
    if lowered.startswith(("dipnot", "footnote")) or (value[:2].isdigit() and len(value.split()) <= 16):
        return "footnote"
    return "body"


class BasePdfAdapter(ABC):
    parser_engine = "UNKNOWN"
    parser_version = "v1"

    @abstractmethod
    def parse(
        self,
        *,
        pdf_path: str,
        document_id: str,
        route: str,
        classifier_result: PdfClassifierResult,
    ) -> CanonicalDocument:
        raise NotImplementedError


class PyMuPdfAdapter(BasePdfAdapter):
    parser_engine = "PYMUPDF"
    parser_version = "v1"

    def parse(
        self,
        *,
        pdf_path: str,
        document_id: str,
        route: str,
        classifier_result: PdfClassifierResult,
    ) -> CanonicalDocument:
        try:
            import fitz  # type: ignore
        except Exception as exc:  # pragma: no cover - optional dependency
            raise RuntimeError("PyMuPDF is required for TEXT_NATIVE parsing") from exc

        source = fitz.open(pdf_path)
        blocks: List[CanonicalBlock] = []
        pages: List[CanonicalPage] = []
        current_heading_path: List[str] = []
        reading_order = 0

        for page_idx in range(len(source)):
            page = source.load_page(page_idx)
            page_metrics = classifier_result.pages[page_idx]
            pages.append(
                CanonicalPage(
                    page_number=page_idx + 1,
                    has_text_layer=bool(page_metrics.has_text_layer),
                    char_count=int(page_metrics.char_count),
                    word_count=int(page_metrics.word_count),
                    ocr_applied=False,
                    image_heavy_suspected=bool(page_metrics.image_heavy_suspected),
                    garbled_ratio=float(page_metrics.garbled_ratio),
                )
            )
            for block_idx, block in enumerate(page.get_text("blocks", sort=True) or []):
                text = str(block[4] or "").strip()
                if not text:
                    continue
                block_type = _detect_block_type(text)
                if block_type == "heading":
                    if not current_heading_path or current_heading_path[-1] != text:
                        current_heading_path = [*current_heading_path, text]
                canonical = CanonicalBlock(
                    block_id=f"{document_id}:p{page_idx + 1}:b{block_idx}",
                    page_number=page_idx + 1,
                    block_type=block_type,
                    text=text,
                    bbox=_normalize_bbox(block[:4]),
                    reading_order=reading_order,
                    heading_path=list(current_heading_path),
                    confidence=1.0,
                    source_engine=self.parser_engine,
                )
                reading_order += 1
                blocks.append(canonical)

        return build_document(
            document_id=document_id,
            route=route,
            parser_engine=self.parser_engine,
            parser_version=self.parser_version,
            pages=pages,
            blocks=blocks,
            classifier_metrics=classifier_result.classifier_metrics,
        )


class LlamaParseAdapter(BasePdfAdapter):
    parser_engine = "LLAMAPARSE"
    parser_version = "v1"

    def parse(
        self,
        *,
        pdf_path: str,
        document_id: str,
        route: str,
        classifier_result: PdfClassifierResult,
    ) -> CanonicalDocument:
        api_key = str(getattr(settings, "LLAMA_CLOUD_API_KEY", "") or "").strip()
        if not api_key:
            raise RuntimeError("LLAMA_CLOUD_API_KEY is required for IMAGE_SCAN parsing")

        timeout_sec = int(getattr(settings, "LLAMA_PARSE_TIMEOUT_SEC", 900))
        poll_interval_sec = int(getattr(settings, "LLAMA_PARSE_POLL_INTERVAL_SEC", 8))
        languages = _parse_language_values(getattr(settings, "PDF_OCR_LANGUAGES", "tr,en"))
        if LlamaCloud is None:
            raise RuntimeError("llama-cloud package is required for IMAGE_SCAN parsing")

        client = LlamaCloud(api_key=api_key)
        file_obj = client.files.create(file=pdf_path, purpose="parse")
        result = client.parsing.parse(
            file_id=str(file_obj.id),
            tier=str(getattr(settings, "LLAMA_PARSE_TIER", "agentic") or "agentic"),
            version=str(getattr(settings, "LLAMA_PARSE_VERSION", "latest") or "latest"),
            expand=["items"],
            processing_options={
                "ocr_parameters": {
                    "languages": languages,
                }
            },
            output_options={
                "spatial_text": {
                    "preserve_layout_alignment_across_pages": True,
                }
            },
            polling_interval=max(1.0, float(poll_interval_sec)),
            timeout=float(timeout_sec),
            verbose=False,
        )
        return _canonicalize_ocr_payload(
            document_id=document_id,
            route=route,
            parser_engine=self.parser_engine,
            parser_version=self.parser_version,
            payload=result.model_dump(mode="json"),
            classifier_result=classifier_result,
            ocr_applied=True,
        )


class UnstructuredAdapter(BasePdfAdapter):
    parser_engine = "UNSTRUCTURED_API"
    parser_version = "v1"

    def parse(
        self,
        *,
        pdf_path: str,
        document_id: str,
        route: str,
        classifier_result: PdfClassifierResult,
        ) -> CanonicalDocument:
        api_url = str(getattr(settings, "UNSTRUCTURED_API_URL", "") or "").strip()
        api_key = str(getattr(settings, "UNSTRUCTURED_API_KEY", "") or "").strip()
        if not api_url:
            raise RuntimeError("UNSTRUCTURED_API_URL is required for OCR fallback")

        headers = {"Accept": "application/json"}
        if api_key:
            headers["unstructured-api-key"] = api_key

        with open(pdf_path, "rb") as handle:
            response = requests.post(
                api_url,
                headers=headers,
                data={
                    "strategy": "hi_res",
                    "languages": json.dumps(_parse_language_values(getattr(settings, "PDF_OCR_LANGUAGES", "tr,en"))),
                    "coordinates": "true",
                    "pdf_infer_table_structure": "true",
                },
                files={"files": (os.path.basename(pdf_path), handle, "application/pdf")},
                timeout=300,
            )
        response.raise_for_status()
        return _canonicalize_ocr_payload(
            document_id=document_id,
            route=route,
            parser_engine=self.parser_engine,
            parser_version=self.parser_version,
            payload=response.json(),
            classifier_result=classifier_result,
            ocr_applied=True,
        )


def _extract_payload_items(payload: Any) -> List[Dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]

    if not isinstance(payload, dict):
        return []

    if isinstance(payload.get("items"), list):
        return [item for item in payload["items"] if isinstance(item, dict)]

    items_payload = payload.get("items") or {}
    pages = items_payload.get("pages") if isinstance(items_payload, dict) else None
    flattened: List[Dict[str, Any]] = []
    if isinstance(pages, list):
        for page in pages:
            if not isinstance(page, dict) or not page.get("success", True):
                continue
            page_number = int(page.get("page_number") or 1)
            for item in page.get("items") or []:
                if not isinstance(item, dict):
                    continue
                flattened.append(
                    {
                        **item,
                        "page_number": int(item.get("page_number") or page_number),
                    }
                )
    if flattened:
        return flattened

    if isinstance(payload.get("pages"), list):
        return [item for item in payload["pages"] if isinstance(item, dict)]
    if isinstance(payload.get("blocks"), list):
        return [item for item in payload["blocks"] if isinstance(item, dict)]
    return []


def _canonicalize_ocr_payload(
    *,
    document_id: str,
    route: str,
    parser_engine: str,
    parser_version: str,
    payload: Any,
    classifier_result: PdfClassifierResult,
    ocr_applied: bool,
) -> CanonicalDocument:
    blocks: List[CanonicalBlock] = []
    pages_map: Dict[int, CanonicalPage] = {
        int(page.page_number): CanonicalPage(
            page_number=int(page.page_number),
            has_text_layer=bool(page.has_text_layer),
            char_count=int(page.char_count),
            word_count=int(page.word_count),
            ocr_applied=ocr_applied,
            image_heavy_suspected=bool(page.image_heavy_suspected),
            garbled_ratio=float(page.garbled_ratio),
        )
        for page in classifier_result.pages
    }

    current_heading_path: List[str] = []
    reading_order = 0
    items = _extract_payload_items(payload)

    if isinstance(items, list):
        for idx, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            text = str(item.get("text") or item.get("value") or item.get("content") or item.get("md") or item.get("csv") or "").strip()
            if not text:
                continue
            page_number = int(item.get("page_number") or item.get("page") or item.get("metadata", {}).get("page_number") or 1)
            block_type = str(item.get("block_type") or item.get("type") or _detect_block_type(text)).lower()
            if block_type == "heading":
                if not current_heading_path or current_heading_path[-1] != text:
                    current_heading_path = [*current_heading_path, text]
            block = CanonicalBlock(
                block_id=f"{document_id}:ocr:{idx}",
                page_number=page_number,
                block_type=block_type,
                text=text,
                bbox=_normalize_bbox(item.get("bbox") or item.get("coordinates")),
                reading_order=reading_order,
                heading_path=list(current_heading_path),
                confidence=float(item.get("confidence") or item.get("metadata", {}).get("confidence") or 0.95),
                source_engine=parser_engine,
            )
            reading_order += 1
            blocks.append(block)
            if page_number not in pages_map:
                pages_map[page_number] = CanonicalPage(
                    page_number=page_number,
                    has_text_layer=False,
                    char_count=len(text),
                    word_count=len(text.split()),
                    ocr_applied=ocr_applied,
                    image_heavy_suspected=True,
                    garbled_ratio=0.0,
                )
            else:
                pages_map[page_number].ocr_applied = ocr_applied

    pages = sorted(pages_map.values(), key=lambda page: int(page.page_number))
    return build_document(
        document_id=document_id,
        route=route,
        parser_engine=parser_engine,
        parser_version=parser_version,
        pages=pages,
        blocks=blocks,
        classifier_metrics=classifier_result.classifier_metrics,
    )
