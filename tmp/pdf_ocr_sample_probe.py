from __future__ import annotations

import json
import os
import sys
import tempfile

import fitz  # type: ignore

from services.pdf_async_ingestion_service import _finalize_document, _run_ocr_parse
from services.pdf_classifier_service import classify_pdf


def _make_sample_pdf(source_path: str, page_limit: int) -> str:
    source = fitz.open(source_path)
    target = fitz.open()
    stop = min(len(source), max(1, page_limit))
    target.insert_pdf(source, from_page=0, to_page=stop - 1)
    handle = tempfile.NamedTemporaryFile(prefix="ocr-sample-", suffix=".pdf", delete=False)
    handle.close()
    target.save(handle.name)
    target.close()
    source.close()
    return handle.name


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: pdf_ocr_sample_probe.py <pdf_path> [page_limit]", file=sys.stderr)
        return 2

    source_path = sys.argv[1]
    page_limit = int(sys.argv[2]) if len(sys.argv) > 2 else 10
    sample_path = _make_sample_pdf(source_path, page_limit)
    try:
        classifier_result = classify_pdf(sample_path)
        document, fallback_engine, fallback_triggered, shard_count, shard_failed_count = _run_ocr_parse(
            pdf_path=sample_path,
            document_id="ocr-sample-probe",
            classifier_result=classifier_result,
        )
        document, chunks, quality_metrics = _finalize_document(document)
        result = {
            "sample_page_limit": page_limit,
            "classifier_metrics": classifier_result.classifier_metrics,
            "parse_summary": {
                "route": "IMAGE_SCAN",
                "parser_engine": document.parser_engine,
                "fallback_engine": fallback_engine,
                "fallback_triggered": bool(fallback_triggered),
                "shard_count": shard_count,
                "shard_failed_count": shard_failed_count,
            },
            "document_summary": {
                "pages": len(document.pages or []),
                "blocks": len(document.blocks or []),
                "chunks": len(chunks or []),
                "quality_metrics": quality_metrics,
                "sample_chunk_preview": [
                    {
                        "chunk_index": int(chunk.get("chunk_index", 0) or 0),
                        "page_number_start": chunk.get("page_number_start"),
                        "page_number_end": chunk.get("page_number_end"),
                        "block_types": chunk.get("block_types"),
                        "text_preview": str(chunk.get("text") or "")[:280],
                    }
                    for chunk in (chunks or [])[:3]
                ],
            },
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    finally:
        try:
            os.remove(sample_path)
        except OSError:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
