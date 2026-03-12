from __future__ import annotations

import json
import os
import sys

from services.pdf_async_ingestion_service import (
    _finalize_document,
    _run_ocr_parse,
    _run_text_native_parse,
    _should_retry_as_ocr,
)
from services.pdf_classifier_service import classify_pdf


def _page_summary(classifier_result) -> dict:
    pages = classifier_result.pages or []
    sample = []
    for page in pages[:5]:
        sample.append(
            {
                "page_number": int(page.page_number),
                "has_text_layer": bool(page.has_text_layer),
                "char_count": int(page.char_count),
                "word_count": int(page.word_count),
                "image_heavy_suspected": bool(page.image_heavy_suspected),
                "garbled_ratio": float(page.garbled_ratio),
            }
        )
    return {
        "page_count": len(pages),
        "sample_pages": sample,
    }


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: pdf_v2_probe.py <pdf_path>", file=sys.stderr)
        return 2

    pdf_path = sys.argv[1]
    if not os.path.exists(pdf_path):
        print(json.dumps({"error": f"file_not_found:{pdf_path}"}))
        return 1

    classifier_result = classify_pdf(pdf_path)
    route = str(classifier_result.route or "IMAGE_SCAN")
    document_id = "probe-doc"

    parse_summary = {
        "initial_route": route,
        "final_route": route,
        "parser_engine": None,
        "fallback_engine": None,
        "fallback_triggered": False,
        "retry_as_ocr": False,
        "retry_reason": None,
        "shard_count": 1,
        "shard_failed_count": 0,
    }

    if route == "TEXT_NATIVE":
        document = _run_text_native_parse(
            pdf_path=pdf_path,
            document_id=document_id,
            classifier_result=classifier_result,
        )
        document, chunks, quality_metrics = _finalize_document(document)
        retry_as_ocr, retry_reason = _should_retry_as_ocr(classifier_result, quality_metrics)
        parse_summary["parser_engine"] = str(document.parser_engine or "PYMUPDF")
        parse_summary["retry_as_ocr"] = bool(retry_as_ocr)
        parse_summary["retry_reason"] = retry_reason
        if retry_as_ocr:
            document, fallback_engine, fallback_triggered, shard_count, shard_failed_count = _run_ocr_parse(
                pdf_path=pdf_path,
                document_id=document_id,
                classifier_result=classifier_result,
            )
            document, chunks, quality_metrics = _finalize_document(document)
            parse_summary["final_route"] = "IMAGE_SCAN"
            parse_summary["parser_engine"] = str(document.parser_engine or "LLAMAPARSE")
            parse_summary["fallback_engine"] = fallback_engine
            parse_summary["fallback_triggered"] = bool(fallback_triggered)
            parse_summary["shard_count"] = int(shard_count)
            parse_summary["shard_failed_count"] = int(shard_failed_count)
    else:
        document, fallback_engine, fallback_triggered, shard_count, shard_failed_count = _run_ocr_parse(
            pdf_path=pdf_path,
            document_id=document_id,
            classifier_result=classifier_result,
        )
        document, chunks, quality_metrics = _finalize_document(document)
        parse_summary["parser_engine"] = str(document.parser_engine or "LLAMAPARSE")
        parse_summary["fallback_engine"] = fallback_engine
        parse_summary["fallback_triggered"] = bool(fallback_triggered)
        parse_summary["shard_count"] = int(shard_count)
        parse_summary["shard_failed_count"] = int(shard_failed_count)

    result = {
        "file_name": os.path.basename(pdf_path),
        "classifier_metrics": classifier_result.classifier_metrics,
        "page_summary": _page_summary(classifier_result),
        "parse_summary": parse_summary,
        "document_summary": {
            "pages": len(document.pages or []),
            "blocks": len(document.blocks or []),
            "chunks": len(chunks or []),
            "quality_metrics": quality_metrics,
            "sample_headings": [block.text for block in (document.blocks or []) if block.block_type == "heading"][:5],
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


if __name__ == "__main__":
    raise SystemExit(main())
