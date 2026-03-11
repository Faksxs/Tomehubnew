from __future__ import annotations

import logging
import math
import re
import sys
from typing import Any, Dict, List

from config import settings
from services.canonical_document_service import CanonicalBlock, CanonicalDocument
from services.monitoring import PDF_TABLE_CHUNK_SPLIT_TOTAL

logger = logging.getLogger(__name__)

try:
    import semchunk
except ImportError:  # pragma: no cover - dependency is optional in some test envs
    semchunk = None

_SEMCHUNKERS: dict[int, object] = {}
_SPACY_SENTENCIZER = None
_SPACY_INIT_ATTEMPTED = False
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?…])\s+")


def _estimate_tokens(text: str) -> int:
    words = len(str(text or "").split())
    return max(1, int(math.ceil(words * 1.3)))


def _render_prefix(block: CanonicalBlock, parser_engine: str) -> str:
    heading = ""
    if block.heading_path:
        heading = f"## {block.heading_path[-1]}\n"
    source = f"[Page {int(block.page_number)} | Parser: {parser_engine}]"
    return f"{heading}{source}"


def _get_semchunker(chunk_size: int):
    cached = _SEMCHUNKERS.get(int(chunk_size))
    if cached is not None:
        return cached
    if semchunk is None:
        return None
    chunker = semchunk.chunkerify(_estimate_tokens, chunk_size=int(chunk_size))
    _SEMCHUNKERS[int(chunk_size)] = chunker
    return chunker


def _get_spacy_sentencizer():
    global _SPACY_SENTENCIZER, _SPACY_INIT_ATTEMPTED
    if _SPACY_INIT_ATTEMPTED:
        return _SPACY_SENTENCIZER
    _SPACY_INIT_ATTEMPTED = True
    if sys.version_info >= (3, 14):  # pragma: no cover - depends on runtime interpreter
        logger.warning("spaCy sentencizer disabled for Python %s.%s; using regex fallback", sys.version_info.major, sys.version_info.minor)
        _SPACY_SENTENCIZER = None
        return _SPACY_SENTENCIZER
    try:
        import spacy

        nlp = spacy.blank("tr")
        if "sentencizer" not in nlp.pipe_names:
            nlp.add_pipe("sentencizer")
        _SPACY_SENTENCIZER = nlp
    except Exception as exc:  # pragma: no cover - depends on runtime python/spacy build
        logger.warning("spaCy sentencizer unavailable for PDF chunking; using regex fallback: %s", exc)
        _SPACY_SENTENCIZER = None
    return _SPACY_SENTENCIZER


def _fallback_split_sentences(text: str) -> List[str]:
    sentences: List[str] = []
    for paragraph in re.split(r"\n{2,}", str(text or "")):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        parts = [part.strip() for part in _SENTENCE_SPLIT_RE.split(paragraph) if part and part.strip()]
        if parts:
            sentences.extend(parts)
        else:
            sentences.append(paragraph)
    return sentences


def _split_sentences(text: str) -> List[str]:
    source = str(text or "").strip()
    if not source:
        return []
    nlp = _get_spacy_sentencizer()
    if nlp is None:
        return _fallback_split_sentences(source)
    try:
        doc = nlp(source)
        sentences = [str(span.text).strip() for span in doc.sents if str(span.text).strip()]
        return sentences or _fallback_split_sentences(source)
    except Exception as exc:  # pragma: no cover - depends on runtime pipeline state
        logger.warning("spaCy sentence split failed for PDF chunking; using regex fallback: %s", exc)
        return _fallback_split_sentences(source)


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


def _render_body_region_legacy(
    blocks: List[CanonicalBlock],
    parser_engine: str,
    *,
    body_target_words: int,
    body_hard_words: int,
) -> List[Dict[str, Any]]:
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
                "rendered_context_prefix": _render_prefix(first, parser_engine),
                "heading_path": list(first.heading_path or []),
                "block_types": [block.block_type for block in buffer_blocks],
                "parser_engine": parser_engine,
                "token_estimate": _estimate_tokens(combined_text),
            }
        )
        buffer_blocks = []
        buffer_words = 0

    for block in blocks:
        block_words = len(str(block.text or "").split())
        if buffer_blocks and (buffer_words + block_words) > body_hard_words:
            flush()
        buffer_blocks.append(block)
        buffer_words += block_words
        if buffer_words >= body_target_words:
            flush()
    flush()
    return chunks


def _build_sentence_units(blocks: List[CanonicalBlock]) -> List[Dict[str, Any]]:
    units: List[Dict[str, Any]] = []
    for block in blocks:
        sentences = _split_sentences(block.text)
        if not sentences:
            sentences = [str(block.text or "").strip()]
        for sentence in sentences:
            cleaned = str(sentence or "").strip()
            if not cleaned:
                continue
            units.append(
                {
                    "text": cleaned,
                    "page_number": int(block.page_number),
                    "block_type": str(block.block_type or "body"),
                }
            )
    return units


def _map_offset_pages(
    sentence_spans: List[tuple[int, int, int]],
    chunk_start: int,
    chunk_end: int,
    default_page: int,
) -> tuple[int, int]:
    matched_pages = [
        page_number
        for span_start, span_end, page_number in sentence_spans
        if span_end > chunk_start and span_start < chunk_end
    ]
    if not matched_pages:
        return default_page, default_page
    return matched_pages[0], matched_pages[-1]


def _render_body_region_sentence_aware(
    blocks: List[CanonicalBlock],
    parser_engine: str,
    *,
    soft_target: int,
    hard_cap: int,
    overlap_tokens: int,
) -> List[Dict[str, Any]]:
    if not blocks:
        return []

    sentence_units = _build_sentence_units(blocks)
    if not sentence_units:
        return []

    chunker = _get_semchunker(soft_target)
    if chunker is None:
        raise RuntimeError("semchunk unavailable")

    parts: List[str] = []
    sentence_spans: List[tuple[int, int, int]] = []
    cursor = 0
    for idx, unit in enumerate(sentence_units):
        if idx > 0:
            parts.append("\n")
            cursor += 1
        text = str(unit["text"] or "").strip()
        start = cursor
        parts.append(text)
        cursor += len(text)
        sentence_spans.append((start, cursor, int(unit["page_number"])))

    region_text = "".join(parts).strip()
    if not region_text:
        return []

    overlap = int(overlap_tokens or 0)
    chunk_texts, offsets = chunker(
        region_text,
        offsets=True,
        overlap=overlap if overlap > 0 else None,
    )

    chunks: List[Dict[str, Any]] = []
    first_block = blocks[0]
    block_types = list(dict.fromkeys(str(block.block_type or "body") for block in blocks))
    for text, (chunk_start, chunk_end) in zip(chunk_texts, offsets):
        cleaned = str(text or "").strip()
        if not cleaned:
            continue
        token_estimate = _estimate_tokens(cleaned)
        if token_estimate > hard_cap:
            raise RuntimeError(f"semchunk exceeded hard cap: {token_estimate}>{hard_cap}")
        page_start, page_end = _map_offset_pages(sentence_spans, int(chunk_start), int(chunk_end), int(first_block.page_number))
        chunks.append(
            {
                "text": cleaned,
                "page_num": int(page_start),
                "page_number_start": int(page_start),
                "page_number_end": int(page_end),
                "context_prefix": first_block.context_prefix or "",
                "rendered_context_prefix": _render_prefix(first_block, parser_engine),
                "heading_path": list(first_block.heading_path or []),
                "block_types": block_types,
                "parser_engine": parser_engine,
                "token_estimate": token_estimate,
            }
        )
    return chunks


def render_document_chunks(document: CanonicalDocument) -> List[Dict[str, Any]]:
    soft_target = int(getattr(settings, "PDF_CHUNK_SOFT_TOKEN_TARGET", 350))
    hard_cap = int(getattr(settings, "PDF_CHUNK_HARD_TOKEN_CAP", 450))
    overlap_tokens = int(getattr(settings, "PDF_CHUNK_OVERLAP_TOKENS", 20) or 0)
    sentence_chunking_enabled = bool(getattr(settings, "PDF_SENTENCE_CHUNKING_ENABLED", True))
    body_target_words = max(60, int(soft_target / 1.3))
    body_hard_words = max(body_target_words, int(hard_cap / 1.3))

    chunks: List[Dict[str, Any]] = []
    body_region: List[CanonicalBlock] = []

    def flush_body_region() -> None:
        nonlocal body_region
        if not body_region:
            return
        if sentence_chunking_enabled:
            try:
                chunks.extend(
                    _render_body_region_sentence_aware(
                        body_region,
                        document.parser_engine,
                        soft_target=soft_target,
                        hard_cap=hard_cap,
                        overlap_tokens=overlap_tokens,
                    )
                )
                body_region = []
                return
            except Exception as exc:
                logger.warning("Sentence-aware PDF chunking failed; falling back to legacy chunker: %s", exc)
        chunks.extend(
            _render_body_region_legacy(
                body_region,
                document.parser_engine,
                body_target_words=body_target_words,
                body_hard_words=body_hard_words,
            )
        )
        body_region = []

    for block in document.blocks or []:
        if not block.text or block.block_type == "heading":
            flush_body_region()
            continue

        if block.block_type in {"table", "quote", "list_cluster", "figure_caption"}:
            flush_body_region()
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

        if body_region and body_region[-1].heading_path != block.heading_path:
            flush_body_region()
        body_region.append(block)

    flush_body_region()
    return chunks


def summarize_chunk_metrics(chunks: List[Dict[str, Any]]) -> Dict[str, Any]:
    token_estimates = [int(chunk.get("token_estimate", 0) or 0) for chunk in chunks]
    total_tokens = sum(token_estimates)
    return {
        "chunk_count": len(chunks),
        "avg_chunk_tokens": round((total_tokens / float(len(chunks))) if chunks else 0.0, 2),
    }
