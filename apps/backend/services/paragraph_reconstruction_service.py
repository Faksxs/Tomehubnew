from __future__ import annotations

import copy
import re
from typing import Dict, List, Tuple

from services.canonical_document_service import CanonicalBlock, CanonicalDocument
from services.chunk_quality_audit_service import should_skip_for_ingestion


_SENTENCE_END_RE = re.compile(r"[.!?\"')\]]\s*$")
_CONTINUATION_RE = re.compile(
    r"^(?:[-,;:)\]\"']|ve\b|veya\b|ama\b|ancak\b|fakat\b|ile\b|ki\b|de\b|da\b|gibi\b|icin\b|için\b)",
    flags=re.IGNORECASE,
)
_HYPHEN_LINEBREAK_RE = re.compile(r"(\w)-\s+(\w)")

_NON_MERGE_TYPES = {"heading", "table", "quote", "footnote", "toc", "bibliography", "front_matter", "imprint", "catalog"}


def _normalize_text(text: str) -> str:
    value = str(text or "").replace("\r", "\n")
    value = _HYPHEN_LINEBREAK_RE.sub(r"\1\2", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def _is_mergeable(block: CanonicalBlock) -> bool:
    return str(block.block_type or "body").lower() not in _NON_MERGE_TYPES


def _should_merge(left: CanonicalBlock, right: CanonicalBlock) -> Tuple[bool, str]:
    if not _is_mergeable(left) or not _is_mergeable(right):
        return False, "blocked_type"

    left_text = str(left.text or "").strip()
    right_text = str(right.text or "").strip()
    if not left_text or not right_text:
        return False, "empty"

    if left.page_number == right.page_number:
        if left_text.endswith("-"):
            return True, "hyphenation_merge"
        if not _SENTENCE_END_RE.search(left_text):
            return True, "same_page_continuation"
        return False, "same_page_terminal"

    if right.page_number - left.page_number == 1:
        if left_text.endswith("-"):
            return True, "hyphenation_merge"
        if (not _SENTENCE_END_RE.search(left_text)) and (
            right_text[:1].islower() or bool(_CONTINUATION_RE.search(right_text))
        ):
            return True, "page_boundary_merge"
    return False, "gap"


def reconstruct_document(document: CanonicalDocument) -> CanonicalDocument:
    reconstructed = copy.deepcopy(document)
    blocks = sorted(
        list(reconstructed.blocks or []),
        key=lambda block: (int(block.page_number), int(block.reading_order), str(block.block_id)),
    )
    merged_blocks: List[CanonicalBlock] = []
    metrics = {
        "page_boundary_merge_total": 0,
        "hyphenation_merge_total": 0,
        "same_page_merge_total": 0,
        "toc_bibliography_pruned_total": 0,
        "header_footer_removed_total": int(document.quality_metrics.get("header_footer_removed_total", 0) or 0),
    }

    current_heading_path: List[str] = []
    buffer_block: CanonicalBlock | None = None

    def flush_buffer() -> None:
        nonlocal buffer_block
        if buffer_block is None:
            return
        buffer_block.text = _normalize_text(buffer_block.text)
        if buffer_block.block_type != "heading":
            buffer_block.context_prefix = " > ".join(buffer_block.heading_path or [])
        merged_blocks.append(buffer_block)
        buffer_block = None

    for block in blocks:
        block.text = _normalize_text(block.text)
        if not block.text:
            continue

        skip, analysis = should_skip_for_ingestion(block.text, page_number=block.page_number)
        if skip and (
            analysis.get("bibliography_like")
            or analysis.get("toc_like")
            or analysis.get("front_matter_like")
            or analysis.get("imprint_like")
            or analysis.get("catalog_like")
            or analysis.get("address_like")
        ):
            metrics["toc_bibliography_pruned_total"] += 1
            continue

        if block.block_type == "heading":
            flush_buffer()
            current_heading_path = list(block.heading_path or current_heading_path)
            if not current_heading_path or current_heading_path[-1] != block.text:
                current_heading_path = [*current_heading_path, block.text]
            block.heading_path = list(current_heading_path)
            merged_blocks.append(block)
            continue

        if not block.heading_path:
            block.heading_path = list(current_heading_path)

        if buffer_block is None:
            buffer_block = block
            continue

        should_merge, reason = _should_merge(buffer_block, block)
        if should_merge:
            joiner = "" if buffer_block.text.endswith("-") else " "
            merged_text = f"{buffer_block.text.rstrip('-')}{joiner}{block.text.lstrip('-')}".strip()
            buffer_block.text = _normalize_text(merged_text)
            buffer_block.merge_origin = reason
            buffer_block.confidence = min(float(buffer_block.confidence or 1.0), float(block.confidence or 1.0))
            if reason == "page_boundary_merge":
                metrics["page_boundary_merge_total"] += 1
            elif reason == "hyphenation_merge":
                metrics["hyphenation_merge_total"] += 1
            else:
                metrics["same_page_merge_total"] += 1
            continue

        flush_buffer()
        buffer_block = block

    flush_buffer()
    for idx, block in enumerate(merged_blocks):
        block.reading_order = idx
        if block.block_type != "heading":
            block.context_prefix = " > ".join(block.heading_path or [])

    reconstructed.blocks = merged_blocks
    reconstructed.quality_metrics = {**dict(reconstructed.quality_metrics or {}), **metrics}
    return reconstructed
