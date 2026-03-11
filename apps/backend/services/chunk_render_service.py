from __future__ import annotations

import math
from typing import Any, Dict, List

from config import settings
from services.canonical_document_service import CanonicalBlock, CanonicalDocument
from services.monitoring import PDF_TABLE_CHUNK_SPLIT_TOTAL


def _estimate_tokens(text: str) -> int:
    words = len(str(text or "").split())
    return max(1, int(math.ceil(words * 1.3)))


def _render_prefix(block: CanonicalBlock, parser_engine: str) -> str:
    heading = ""
    if block.heading_path:
        heading = f"## {block.heading_path[-1]}\n"
    source = f"[Page {int(block.page_number)} | Parser: {parser_engine}]"
    return f"{heading}{source}"


def _split_table_block(block: CanonicalBlock, parser_engine: str, hard_cap: int) -> List[Dict[str, Any]]:
    lines = [line.strip() for line in str(block.text or "").splitlines() if line and line.strip()]
    if len(lines) <= 2:
        return []

    title = lines[0]
    header = lines[1]
    body_rows = lines[2:]
    chunks: List[Dict[str, Any]] = []
    row_buffer: List[str] = []

    def flush() -> None:
        nonlocal row_buffer
        if not row_buffer:
            return
        text = "\n".join([title, header, *row_buffer])
        chunks.append(
            {
                "text": text,
                "page_num": int(block.page_number),
                "page_number_start": int(block.page_number),
                "page_number_end": int(block.page_number),
                "context_prefix": block.context_prefix or "",
                "rendered_context_prefix": _render_prefix(block, parser_engine),
                "heading_path": list(block.heading_path or []),
                "block_types": [block.block_type],
                "parser_engine": parser_engine,
                "token_estimate": _estimate_tokens(text),
            }
        )
        row_buffer = []

    for row in body_rows:
        candidate_rows = [*row_buffer, row]
        candidate_text = "\n".join([title, header, *candidate_rows])
        if row_buffer and _estimate_tokens(candidate_text) > hard_cap:
            flush()
        row_buffer.append(row)
    flush()
    return chunks if len(chunks) > 1 else []


def render_document_chunks(document: CanonicalDocument) -> List[Dict[str, Any]]:
    soft_target = int(getattr(settings, "PDF_CHUNK_SOFT_TOKEN_TARGET", 350))
    hard_cap = int(getattr(settings, "PDF_CHUNK_HARD_TOKEN_CAP", 450))
    body_target_words = max(60, int(soft_target / 1.3))
    body_hard_words = max(body_target_words, int(hard_cap / 1.3))

    chunks: List[Dict[str, Any]] = []
    buffer_blocks: List[CanonicalBlock] = []
    buffer_words = 0

    def flush() -> None:
        nonlocal buffer_blocks, buffer_words
        if not buffer_blocks:
            return
        first = buffer_blocks[0]
        last = buffer_blocks[-1]
        combined_text = "\n\n".join(block.text for block in buffer_blocks if block.text)
        chunks.append(
            {
                "text": combined_text,
                "page_num": int(first.page_number),
                "page_number_start": int(first.page_number),
                "page_number_end": int(last.page_number),
                "context_prefix": first.context_prefix or "",
                "rendered_context_prefix": _render_prefix(first, document.parser_engine),
                "heading_path": list(first.heading_path or []),
                "block_types": [block.block_type for block in buffer_blocks],
                "parser_engine": document.parser_engine,
                "token_estimate": _estimate_tokens(combined_text),
            }
        )
        buffer_blocks = []
        buffer_words = 0

    for block in document.blocks or []:
        if not block.text or block.block_type == "heading":
            continue
        if block.block_type in {"table", "quote", "list_cluster", "figure_caption"}:
            flush()
            if block.block_type == "table":
                table_chunks = _split_table_block(block, document.parser_engine, hard_cap)
                if table_chunks:
                    PDF_TABLE_CHUNK_SPLIT_TOTAL.labels(
                        parser_engine=str(document.parser_engine or "UNKNOWN"),
                        route=str(document.route or "UNKNOWN"),
                    ).inc(len(table_chunks) - 1)
                    chunks.extend(table_chunks)
                    continue
            chunks.append(
                {
                    "text": block.text,
                    "page_num": int(block.page_number),
                    "page_number_start": int(block.page_number),
                    "page_number_end": int(block.page_number),
                    "context_prefix": block.context_prefix or "",
                    "rendered_context_prefix": _render_prefix(block, document.parser_engine),
                    "heading_path": list(block.heading_path or []),
                    "block_types": [block.block_type],
                    "parser_engine": document.parser_engine,
                    "token_estimate": _estimate_tokens(block.text),
                }
            )
            continue

        block_words = len(block.text.split())
        if buffer_blocks and (buffer_words + block_words) > body_hard_words:
            flush()
        buffer_blocks.append(block)
        buffer_words += block_words
        if buffer_words >= body_target_words:
            flush()

    flush()
    return chunks


def summarize_chunk_metrics(chunks: List[Dict[str, Any]]) -> Dict[str, Any]:
    token_estimates = [int(chunk.get("token_estimate", 0) or 0) for chunk in chunks]
    total_tokens = sum(token_estimates)
    return {
        "chunk_count": len(chunks),
        "avg_chunk_tokens": round((total_tokens / float(len(chunks))) if chunks else 0.0, 2),
    }
