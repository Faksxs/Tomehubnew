from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class CanonicalPage:
    page_number: int
    has_text_layer: bool
    char_count: int
    word_count: int
    ocr_applied: bool
    image_heavy_suspected: bool
    garbled_ratio: float


@dataclass
class CanonicalBlock:
    block_id: str
    page_number: int
    block_type: str
    text: str
    bbox: Optional[Dict[str, float]] = None
    reading_order: int = 0
    heading_path: List[str] = field(default_factory=list)
    confidence: float = 1.0
    source_engine: str = ""
    merge_origin: str = "original"
    context_prefix: str = ""


@dataclass
class CanonicalDocument:
    document_id: str
    route: str
    parser_engine: str
    parser_version: str
    pages: List[CanonicalPage]
    blocks: List[CanonicalBlock]
    classifier_metrics: Dict[str, Any] = field(default_factory=dict)
    quality_metrics: Dict[str, Any] = field(default_factory=dict)
    routing_metrics: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "document_id": self.document_id,
            "route": self.route,
            "parser_engine": self.parser_engine,
            "parser_version": self.parser_version,
            "pages": [asdict(page) for page in self.pages],
            "blocks": [asdict(block) for block in self.blocks],
            "classifier_metrics": dict(self.classifier_metrics or {}),
            "quality_metrics": dict(self.quality_metrics or {}),
            "routing_metrics": dict(self.routing_metrics or {}),
        }


def build_document(
    *,
    document_id: str,
    route: str,
    parser_engine: str,
    parser_version: str,
    pages: List[CanonicalPage],
    blocks: List[CanonicalBlock],
    classifier_metrics: Optional[Dict[str, Any]] = None,
    quality_metrics: Optional[Dict[str, Any]] = None,
    routing_metrics: Optional[Dict[str, Any]] = None,
) -> CanonicalDocument:
    return CanonicalDocument(
        document_id=document_id,
        route=str(route or "").upper(),
        parser_engine=str(parser_engine or "").upper(),
        parser_version=str(parser_version or ""),
        pages=list(pages or []),
        blocks=list(blocks or []),
        classifier_metrics=dict(classifier_metrics or {}),
        quality_metrics=dict(quality_metrics or {}),
        routing_metrics=dict(routing_metrics or {}),
    )


def merge_documents(
    *,
    document_id: str,
    route: str,
    parser_engine: str,
    parser_version: str,
    documents: List[CanonicalDocument],
    classifier_metrics: Optional[Dict[str, Any]] = None,
    routing_metrics: Optional[Dict[str, Any]] = None,
) -> CanonicalDocument:
    merged_pages_map: Dict[int, CanonicalPage] = {}
    merged_blocks: List[CanonicalBlock] = []
    merged_quality: Dict[str, Any] = {}

    for document in documents or []:
        for page in document.pages or []:
            page_number = int(page.page_number)
            existing = merged_pages_map.get(page_number)
            if existing is None:
                merged_pages_map[page_number] = page
                continue
            merged_pages_map[page_number] = CanonicalPage(
                page_number=page_number,
                has_text_layer=bool(existing.has_text_layer or page.has_text_layer),
                char_count=max(int(existing.char_count or 0), int(page.char_count or 0)),
                word_count=max(int(existing.word_count or 0), int(page.word_count or 0)),
                ocr_applied=bool(existing.ocr_applied or page.ocr_applied),
                image_heavy_suspected=bool(existing.image_heavy_suspected or page.image_heavy_suspected),
                garbled_ratio=max(float(existing.garbled_ratio or 0.0), float(page.garbled_ratio or 0.0)),
            )
        merged_blocks.extend(document.blocks or [])
        for key, value in (document.quality_metrics or {}).items():
            if isinstance(value, (int, float)):
                merged_quality[key] = float(merged_quality.get(key, 0.0)) + float(value)
            else:
                merged_quality[key] = value

    merged_pages = list(merged_pages_map.values())
    merged_pages.sort(key=lambda page: (int(page.page_number), not bool(page.has_text_layer)))
    merged_blocks.sort(key=lambda block: (int(block.page_number), int(block.reading_order), str(block.block_id)))

    for idx, block in enumerate(merged_blocks):
        block.reading_order = idx

    return build_document(
        document_id=document_id,
        route=route,
        parser_engine=parser_engine,
        parser_version=parser_version,
        pages=merged_pages,
        blocks=merged_blocks,
        classifier_metrics=classifier_metrics or {},
        quality_metrics=merged_quality,
        routing_metrics=routing_metrics or {},
    )
