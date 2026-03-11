from __future__ import annotations

import asyncio
import copy
import json
import logging
import os
import time
from typing import Dict, Optional

from config import settings
from infrastructure.db_manager import DatabaseManager
from services.canonical_document_service import CanonicalDocument, merge_documents
from services.chunk_render_service import render_document_chunks, summarize_chunk_metrics
from services.external_kb_service import maybe_trigger_external_enrichment_async
from services.index_freshness_service import maybe_trigger_graph_enrichment_async
from services.ingestion_service import ingest_pre_extracted_chunks
from services.ingestion_status_service import (
    delete_ingested_file_row,
    get_pdf_record,
    list_pending_parse_jobs,
    list_pending_storage_deletes,
    mark_storage_delete_failed,
    set_storage_delete_pending,
    upsert_ingestion_status,
)
from services.monitoring import (
    PDF_AVG_CHUNK_TOKENS,
    PDF_CHARS_EXTRACTED_TOTAL,
    PDF_CHUNK_COUNT,
    PDF_CLASSIFIER_ROUTE_TOTAL,
    PDF_FALLBACK_TRIGGERED_TOTAL,
    PDF_GARBLED_RATIO,
    PDF_HEADER_FOOTER_REMOVED_TOTAL,
    PDF_PAGE_BOUNDARY_MERGE_TOTAL,
    PDF_PAGES_PROCESSED,
    PDF_PARSE_SHARD_TOTAL,
    PDF_PARSE_TIME_SECONDS,
    PDF_PARSER_ENGINE_TOTAL,
    PDF_RETRY_AS_OCR_TOTAL,
    PDF_TOC_BIBLIOGRAPHY_PRUNED_TOTAL,
    PDF_HYPHENATION_MERGE_TOTAL,
)
from services.object_storage_service import (
    build_canonical_object_key,
    cleanup_pdf_artifacts,
    download_object_to_tempfile,
    put_json_object,
)
from services.paragraph_reconstruction_service import reconstruct_document
from services.pdf_classifier_service import PdfClassifierResult, classify_pdf
from services.pdf_parser_adapters import LlamaParseAdapter, PyMuPdfAdapter, UnstructuredAdapter
from services.report_service import generate_file_report

logger = logging.getLogger(__name__)


def _status_json(value: Dict[str, object]) -> str:
    return json.dumps(value, ensure_ascii=False)


def _resolve_book_metadata(book_id: str, firebase_uid: str) -> Dict[str, str]:
    fallback = {"title": "", "author": ""}
    try:
        with DatabaseManager.get_read_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT TITLE, AUTHOR
                    FROM TOMEHUB_LIBRARY_ITEMS
                    WHERE ITEM_ID = :p_book AND FIREBASE_UID = :p_uid
                    """,
                    {"p_book": book_id, "p_uid": firebase_uid},
                )
                row = cursor.fetchone()
                if not row:
                    return fallback
                return {"title": str(row[0] or ""), "author": str(row[1] or "")}
    except Exception as exc:
        logger.warning("Failed to resolve book metadata for async ingestion: %s", exc)
        return fallback


def _parse_csv_tags(raw: Optional[str]) -> list[str]:
    return [part.strip() for part in str(raw or "").split(",") if part and part.strip()]


def _query_chunk_counts(book_id: str, firebase_uid: str) -> Dict[str, int]:
    counts = {"chunk_count": 0, "embedding_count": 0}
    try:
        with DatabaseManager.get_read_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT COUNT(*),
                           SUM(CASE WHEN VEC_EMBEDDING IS NOT NULL THEN 1 ELSE 0 END)
                    FROM TOMEHUB_CONTENT_V2
                    WHERE ITEM_ID = :p_bid AND FIREBASE_UID = :p_uid
                    """,
                    {"p_bid": book_id, "p_uid": firebase_uid},
                )
                row = cursor.fetchone()
                counts["chunk_count"] = int(row[0] or 0) if row else 0
                counts["embedding_count"] = int(row[1] or 0) if row and row[1] is not None else 0
    except Exception as exc:
        logger.error("Failed to query ingestion counts: %s", exc)
    return counts


def _emit_post_ingestion_effects(book_id: str, firebase_uid: str, title: str, author: str, categories: Optional[str]) -> None:
    try:
        maybe_trigger_graph_enrichment_async(
            firebase_uid=firebase_uid,
            book_id=book_id,
            reason="pdf_ingest_completed",
        )
    except Exception as exc:
        logger.warning("Graph enrichment trigger failed after async ingest: %s", exc)
    try:
        maybe_trigger_external_enrichment_async(
            book_id=book_id,
            firebase_uid=firebase_uid,
            title=title,
            author=author,
            tags=_parse_csv_tags(categories),
            mode_hint="INGEST",
        )
    except Exception as exc:
        logger.warning("External enrichment trigger failed after async ingest: %s", exc)
    try:
        generate_file_report(book_id, firebase_uid)
    except Exception as exc:
        logger.warning("File report generation failed after async ingest: %s", exc)


def _should_retry_as_ocr(classifier_result: PdfClassifierResult, chunk_metrics: Dict[str, object]) -> tuple[bool, str]:
    chunk_count = int(chunk_metrics.get("chunk_count", 0) or 0)
    garbled_ratio = float(classifier_result.classifier_metrics.get("garbled_ratio", 0.0) or 0.0)
    if chunk_count < int(getattr(settings, "PDF_RETRY_AS_OCR_MIN_CHUNKS", 8)):
        return True, "low_chunk_yield"
    if garbled_ratio >= float(getattr(settings, "PDF_RETRY_AS_OCR_GARBLED_RATIO", 0.18)):
        return True, "garbled_text"
    return False, "not_needed"


def _needs_ocr_sharding(classifier_result: PdfClassifierResult) -> bool:
    pages = int(classifier_result.classifier_metrics.get("page_count", 0) or 0)
    file_size_mb = float(classifier_result.classifier_metrics.get("file_size_bytes", 0) or 0) / float(1024 * 1024)
    return (
        pages >= int(getattr(settings, "PDF_OCR_SHARD_TRIGGER_PAGES", 300))
        or file_size_mb >= float(getattr(settings, "PDF_OCR_SHARD_TRIGGER_FILE_MB", 25))
    )


def _build_pdf_shards(pdf_path: str) -> list[dict[str, object]]:
    try:
        import fitz  # type: ignore
    except Exception as exc:  # pragma: no cover - optional dependency
        raise RuntimeError("PyMuPDF is required for OCR shard creation") from exc

    shard_size = max(1, int(getattr(settings, "PDF_OCR_SHARD_SIZE", 100)))
    source = fitz.open(pdf_path)
    shard_jobs: list[dict[str, object]] = []
    directory = os.path.dirname(pdf_path)
    base = os.path.splitext(os.path.basename(pdf_path))[0]

    for start in range(0, len(source), shard_size):
        stop = min(len(source), start + shard_size)
        target = fitz.open()
        target.insert_pdf(source, from_page=start, to_page=stop - 1)
        shard_path = os.path.join(directory, f"{base}.shard_{start + 1}_{stop}.pdf")
        target.save(shard_path)
        target.close()
        shard_jobs.append(
            {
                "pdf_path": shard_path,
                "start_page": start + 1,
                "stop_page": stop,
            }
        )

    source.close()
    return shard_jobs


def _build_shard_classifier_result(
    classifier_result: PdfClassifierResult,
    *,
    start_page: int,
    stop_page: int,
    file_path: str,
) -> PdfClassifierResult:
    selected_pages = []
    for local_index, page in enumerate(classifier_result.pages[start_page - 1:stop_page], start=1):
        cloned = copy.deepcopy(page)
        cloned.page_number = local_index
        selected_pages.append(cloned)

    page_count = len(selected_pages)
    pages_with_text = sum(1 for page in selected_pages if page.has_text_layer)
    blank_pages = sum(1 for page in selected_pages if int(page.char_count or 0) == 0)
    image_heavy_pages = sum(1 for page in selected_pages if page.image_heavy_suspected)
    total_chars = sum(int(page.char_count or 0) for page in selected_pages)
    total_words = sum(int(page.word_count or 0) for page in selected_pages)
    total_garbled = sum(float(page.garbled_ratio or 0.0) for page in selected_pages)

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
        "route_reason": str(classifier_result.classifier_metrics.get("route_reason") or "ocr_default"),
    }
    return PdfClassifierResult(route="IMAGE_SCAN", classifier_metrics=metrics, pages=selected_pages)


def _offset_document_page_numbers(document: CanonicalDocument, page_offset: int) -> CanonicalDocument:
    if page_offset <= 0:
        return document
    for page in document.pages or []:
        page.page_number = int(page.page_number) + page_offset
    for block in document.blocks or []:
        block.page_number = int(block.page_number) + page_offset
    return document


def _run_text_native_parse(
    *,
    pdf_path: str,
    document_id: str,
    classifier_result: PdfClassifierResult,
) -> CanonicalDocument:
    adapter = PyMuPdfAdapter()
    return adapter.parse(
        pdf_path=pdf_path,
        document_id=document_id,
        route="TEXT_NATIVE",
        classifier_result=classifier_result,
    )


def _run_ocr_parse(
    *,
    pdf_path: str,
    document_id: str,
    classifier_result: PdfClassifierResult,
) -> tuple[CanonicalDocument, Optional[str], bool, int, int]:
    primary = LlamaParseAdapter()
    fallback = UnstructuredAdapter()
    fallback_engine: Optional[str] = None
    fallback_triggered = False
    shard_count = 1
    shard_failed_count = 0

    shard_jobs = [
        {
            "pdf_path": pdf_path,
            "start_page": 1,
            "stop_page": int(classifier_result.classifier_metrics.get("page_count", 0) or 0),
        }
    ]
    if _needs_ocr_sharding(classifier_result):
        shard_jobs = _build_pdf_shards(pdf_path)
        shard_count = len(shard_jobs)

    documents: list[CanonicalDocument] = []
    try:
        for shard_index, shard_job in enumerate(shard_jobs):
            shard_path = str(shard_job["pdf_path"])
            start_page = int(shard_job["start_page"])
            stop_page = int(shard_job["stop_page"])
            shard_classifier_result = _build_shard_classifier_result(
                classifier_result,
                start_page=start_page,
                stop_page=stop_page,
                file_path=shard_path,
            )
            shard_id = f"{document_id}:shard:{shard_index + 1}"
            try:
                document = primary.parse(
                    pdf_path=shard_path,
                    document_id=shard_id,
                    route="IMAGE_SCAN",
                    classifier_result=shard_classifier_result,
                )
                PDF_PARSE_SHARD_TOTAL.labels(parser_engine=primary.parser_engine, status="success").inc()
            except Exception as primary_exc:
                PDF_PARSE_SHARD_TOTAL.labels(parser_engine=primary.parser_engine, status="failed").inc()
                try:
                    document = fallback.parse(
                        pdf_path=shard_path,
                        document_id=shard_id,
                        route="IMAGE_SCAN",
                        classifier_result=shard_classifier_result,
                    )
                    fallback_engine = fallback.parser_engine
                    fallback_triggered = True
                    PDF_FALLBACK_TRIGGERED_TOTAL.labels(
                        from_engine=primary.parser_engine,
                        to_engine=fallback.parser_engine,
                        reason=str(primary_exc.__class__.__name__).lower(),
                    ).inc()
                    PDF_PARSE_SHARD_TOTAL.labels(parser_engine=fallback.parser_engine, status="success").inc()
                except Exception:
                    shard_failed_count += 1
                    PDF_PARSE_SHARD_TOTAL.labels(parser_engine=fallback.parser_engine, status="failed").inc()
                    raise
            document = _offset_document_page_numbers(document, start_page - 1)
            documents.append(document)
    finally:
        if len(shard_jobs) > 1:
            for shard_job in shard_jobs:
                try:
                    shard_path = str(shard_job["pdf_path"])
                    if os.path.exists(shard_path):
                        os.remove(shard_path)
                except Exception:
                    pass

    merged_parser_engine = "UNKNOWN"
    if documents:
        merged_parser_engine = str(documents[0].parser_engine or "UNKNOWN")
        if any(str(document.parser_engine or "UNKNOWN") != merged_parser_engine for document in documents[1:]):
            merged_parser_engine = "MIXED"

    merged = merge_documents(
        document_id=document_id,
        route="IMAGE_SCAN",
        parser_engine=merged_parser_engine,
        parser_version="v1",
        documents=documents,
        classifier_metrics=classifier_result.classifier_metrics,
        routing_metrics={
            "shard_count": shard_count,
            "shard_failed_count": shard_failed_count,
            "fallback_triggered": fallback_triggered,
            "fallback_engine": fallback_engine,
        },
    )
    return merged, fallback_engine, fallback_triggered, shard_count, shard_failed_count


def _finalize_document(document: CanonicalDocument) -> tuple[CanonicalDocument, list[dict], Dict[str, object]]:
    reconstructed = reconstruct_document(document)
    chunks = render_document_chunks(reconstructed)
    chunk_metrics = summarize_chunk_metrics(chunks)
    chars_extracted = sum(len(str(block.text or "")) for block in reconstructed.blocks or [])
    pages = len(reconstructed.pages or [])
    garbled_ratio = 0.0
    if reconstructed.pages:
        garbled_ratio = sum(float(page.garbled_ratio or 0.0) for page in reconstructed.pages) / float(len(reconstructed.pages))

    reconstructed.quality_metrics = {
        **dict(reconstructed.quality_metrics or {}),
        **chunk_metrics,
        "chars_extracted": chars_extracted,
        "pages": pages,
        "garbled_ratio": round(garbled_ratio, 4),
    }
    return reconstructed, chunks, reconstructed.quality_metrics


def _observe_document_metrics(document: CanonicalDocument, quality_metrics: Dict[str, object]) -> None:
    parser_engine = str(document.parser_engine or "UNKNOWN")
    route = str(document.route or "UNKNOWN")
    pages = int(quality_metrics.get("pages", 0) or 0)
    chars_extracted = int(quality_metrics.get("chars_extracted", 0) or 0)
    garbled_ratio = float(quality_metrics.get("garbled_ratio", 0.0) or 0.0)
    chunk_count = int(quality_metrics.get("chunk_count", 0) or 0)
    avg_chunk_tokens = float(quality_metrics.get("avg_chunk_tokens", 0.0) or 0.0)

    PDF_PARSER_ENGINE_TOTAL.labels(parser_engine=parser_engine, route=route).inc()
    PDF_PAGES_PROCESSED.labels(parser_engine=parser_engine, route=route).observe(pages)
    PDF_CHARS_EXTRACTED_TOTAL.labels(parser_engine=parser_engine, route=route).inc(chars_extracted)
    PDF_GARBLED_RATIO.labels(parser_engine=parser_engine, route=route).observe(garbled_ratio)
    PDF_CHUNK_COUNT.labels(parser_engine=parser_engine, route=route).observe(chunk_count)
    PDF_AVG_CHUNK_TOKENS.labels(parser_engine=parser_engine, route=route).observe(avg_chunk_tokens)
    PDF_HEADER_FOOTER_REMOVED_TOTAL.labels(parser_engine=parser_engine, route=route).inc(
        int(quality_metrics.get("header_footer_removed_total", 0) or 0)
    )
    PDF_TOC_BIBLIOGRAPHY_PRUNED_TOTAL.labels(parser_engine=parser_engine, route=route).inc(
        int(quality_metrics.get("toc_bibliography_pruned_total", 0) or 0)
    )
    PDF_PAGE_BOUNDARY_MERGE_TOTAL.labels(parser_engine=parser_engine, route=route).inc(
        int(quality_metrics.get("page_boundary_merge_total", 0) or 0)
    )
    PDF_HYPHENATION_MERGE_TOTAL.labels(parser_engine=parser_engine, route=route).inc(
        int(quality_metrics.get("hyphenation_merge_total", 0) or 0)
    )


class AsyncPdfIngestionManager:
    def __init__(self) -> None:
        self._parse_tasks: dict[str, asyncio.Task] = {}
        self._maintenance_task: Optional[asyncio.Task] = None

    def _task_key(self, firebase_uid: str, book_id: str) -> str:
        return f"{firebase_uid}:{book_id}"

    async def enqueue_pdf_processing(
        self,
        *,
        book_id: str,
        firebase_uid: str,
        title: str,
        author: str,
        categories: Optional[str],
        bucket_name: str,
        object_key: str,
    ) -> None:
        key = self._task_key(firebase_uid, book_id)
        current = self._parse_tasks.get(key)
        if current and not current.done():
            raise RuntimeError(f"PDF ingestion already active for {book_id}")
        upsert_ingestion_status(
            book_id,
            firebase_uid,
            status="PROCESSING",
            parse_path="PDF_V2",
            parse_status="QUEUED",
            classification_route=None,
            parse_engine=None,
            fallback_engine=None,
            fallback_triggered=0,
            shard_count=0,
            shard_failed_count=0,
        )
        self._ensure_processing_task(
            book_id=book_id,
            firebase_uid=firebase_uid,
            title=title,
            author=author,
            categories=categories,
            bucket_name=bucket_name,
            object_key=object_key,
        )

    def _ensure_processing_task(
        self,
        *,
        book_id: str,
        firebase_uid: str,
        title: str,
        author: str,
        categories: Optional[str],
        bucket_name: str,
        object_key: str,
    ) -> None:
        key = self._task_key(firebase_uid, book_id)
        current = self._parse_tasks.get(key)
        if current and not current.done():
            return
        self._parse_tasks[key] = asyncio.create_task(
            self._process_pdf_from_storage(
                book_id=book_id,
                firebase_uid=firebase_uid,
                title=title,
                author=author,
                categories=categories,
                bucket_name=bucket_name,
                object_key=object_key,
            )
        )

    async def _process_pdf_from_storage(
        self,
        *,
        book_id: str,
        firebase_uid: str,
        title: str,
        author: str,
        categories: Optional[str],
        bucket_name: str,
        object_key: str,
    ) -> None:
        parse_started = time.perf_counter()
        temp_path = None
        route = None
        parser_engine = None
        fallback_engine = None
        fallback_triggered = False
        shard_count = 1
        shard_failed_count = 0
        try:
            upsert_ingestion_status(
                book_id,
                firebase_uid,
                status="PROCESSING",
                parse_path="PDF_V2",
                parse_status="CLASSIFYING",
            )
            temp_path = await asyncio.to_thread(download_object_to_tempfile, bucket_name, object_key, ".pdf")
            classifier_result = await asyncio.to_thread(classify_pdf, temp_path)
            route = str(classifier_result.route or "IMAGE_SCAN")
            PDF_CLASSIFIER_ROUTE_TOTAL.labels(route=route).inc()

            upsert_ingestion_status(
                book_id,
                firebase_uid,
                status="PROCESSING",
                parse_path="PDF_V2",
                parse_status="PARSING",
                classification_route=route,
                classifier_metrics_json=_status_json(classifier_result.classifier_metrics),
                pages=int(classifier_result.classifier_metrics.get("page_count", 0) or 0),
                garbled_ratio=float(classifier_result.classifier_metrics.get("garbled_ratio", 0.0) or 0.0),
            )

            if route == "TEXT_NATIVE":
                parser_engine = "PYMUPDF"
                document = await asyncio.to_thread(
                    _run_text_native_parse,
                    pdf_path=temp_path,
                    document_id=book_id,
                    classifier_result=classifier_result,
                )
                document, chunks, quality_metrics = await asyncio.to_thread(_finalize_document, document)
                retry_as_ocr, retry_reason = _should_retry_as_ocr(classifier_result, quality_metrics)
                if retry_as_ocr:
                    PDF_RETRY_AS_OCR_TOTAL.labels(reason=retry_reason).inc()
                    route = "IMAGE_SCAN"
                    document, fallback_engine, fallback_triggered, shard_count, shard_failed_count = await asyncio.to_thread(
                        _run_ocr_parse,
                        pdf_path=temp_path,
                        document_id=book_id,
                        classifier_result=classifier_result,
                    )
                    parser_engine = str(document.parser_engine or "LLAMAPARSE")
                    document.routing_metrics = {
                        **dict(document.routing_metrics or {}),
                        "retry_as_ocr": True,
                        "retry_reason": retry_reason,
                    }
                    document, chunks, quality_metrics = await asyncio.to_thread(_finalize_document, document)
                else:
                    document.routing_metrics = {
                        **dict(document.routing_metrics or {}),
                        "retry_as_ocr": False,
                    }
            else:
                document, fallback_engine, fallback_triggered, shard_count, shard_failed_count = await asyncio.to_thread(
                    _run_ocr_parse,
                    pdf_path=temp_path,
                    document_id=book_id,
                    classifier_result=classifier_result,
                )
                parser_engine = str(document.parser_engine or "LLAMAPARSE")
                document, chunks, quality_metrics = await asyncio.to_thread(_finalize_document, document)

            upsert_ingestion_status(
                book_id,
                firebase_uid,
                status="PROCESSING",
                parse_path="PDF_V2",
                parse_status="INGESTING",
                classification_route=route,
                parse_engine=parser_engine,
                fallback_engine=fallback_engine,
                fallback_triggered=int(bool(fallback_triggered)),
                shard_count=int(shard_count),
                shard_failed_count=int(shard_failed_count),
                quality_metrics_json=_status_json(quality_metrics),
                routing_metrics_json=_status_json(document.routing_metrics or {}),
                chars_extracted=int(quality_metrics.get("chars_extracted", 0) or 0),
                avg_chunk_tokens=float(quality_metrics.get("avg_chunk_tokens", 0.0) or 0.0),
            )

            await asyncio.to_thread(
                put_json_object,
                bucket_name,
                build_canonical_object_key(firebase_uid, book_id),
                document.to_dict(),
            )

            success = await asyncio.to_thread(
                ingest_pre_extracted_chunks,
                chunks=chunks,
                title=title,
                author=author,
                firebase_uid=firebase_uid,
                book_id=book_id,
                source_type="PDF",
                categories=categories,
                file_path=None,
                cleanup_file=False,
            )
            if not success:
                raise RuntimeError("Failed to persist PDF Ingestion V2 chunks")

            parse_time_ms = int((time.perf_counter() - parse_started) * 1000)
            counts = _query_chunk_counts(book_id, firebase_uid)
            upsert_ingestion_status(
                book_id,
                firebase_uid,
                status="COMPLETED",
                parse_path="PDF_V2",
                parse_status="COMPLETED",
                classification_route=route,
                parse_engine=parser_engine,
                fallback_engine=fallback_engine,
                classifier_metrics_json=_status_json(classifier_result.classifier_metrics),
                quality_metrics_json=_status_json(quality_metrics),
                routing_metrics_json=_status_json(document.routing_metrics or {}),
                chunk_count=counts["chunk_count"],
                embedding_count=counts["embedding_count"],
                parse_time_ms=parse_time_ms,
                pages=int(quality_metrics.get("pages", 0) or 0),
                chars_extracted=int(quality_metrics.get("chars_extracted", 0) or 0),
                garbled_ratio=float(quality_metrics.get("garbled_ratio", 0.0) or 0.0),
                avg_chunk_tokens=float(quality_metrics.get("avg_chunk_tokens", 0.0) or 0.0),
                fallback_triggered=int(bool(fallback_triggered)),
                shard_count=int(shard_count),
                shard_failed_count=int(shard_failed_count),
                error_message=None,
            )

            _observe_document_metrics(document, quality_metrics)
            PDF_PARSE_TIME_SECONDS.labels(parser_engine=parser_engine or "UNKNOWN", route=route or "UNKNOWN", status="success").observe(
                parse_time_ms / 1000.0
            )
            _emit_post_ingestion_effects(book_id, firebase_uid, title, author, categories)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            parse_time_ms = int((time.perf_counter() - parse_started) * 1000)
            upsert_ingestion_status(
                book_id,
                firebase_uid,
                status="FAILED",
                parse_path="PDF_V2",
                parse_status="FAILED",
                classification_route=route,
                parse_engine=parser_engine,
                fallback_engine=fallback_engine,
                fallback_triggered=int(bool(fallback_triggered)),
                shard_count=int(shard_count),
                shard_failed_count=int(shard_failed_count),
                parse_time_ms=parse_time_ms,
                error_message=(str(exc) or "")[:1000],
            )
            PDF_PARSE_TIME_SECONDS.labels(parser_engine=parser_engine or "UNKNOWN", route=route or "UNKNOWN", status="failed").observe(
                parse_time_ms / 1000.0
            )
            logger.exception("PDF Ingestion V2 failed for %s/%s", firebase_uid, book_id)
        finally:
            self._parse_tasks.pop(self._task_key(firebase_uid, book_id), None)
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except Exception:
                    pass

    async def resume_pending_jobs(self) -> None:
        pending_rows = await asyncio.to_thread(list_pending_parse_jobs)
        for row in pending_rows:
            book_id = str(row.get("book_id") or "")
            firebase_uid = str(row.get("firebase_uid") or "")
            metadata = _resolve_book_metadata(book_id, firebase_uid)
            title = metadata["title"]
            author = metadata["author"]
            bucket_name = str(row.get("bucket_name") or "")
            object_key = str(row.get("object_key") or "")
            if not bucket_name or not object_key:
                continue
            self._ensure_processing_task(
                book_id=book_id,
                firebase_uid=firebase_uid,
                title=title,
                author=author,
                categories=None,
                bucket_name=bucket_name,
                object_key=object_key,
            )

    async def retry_pending_storage_deletes_once(self) -> None:
        rows = await asyncio.to_thread(list_pending_storage_deletes)
        for row in rows:
            book_id = str(row.get("book_id") or "")
            firebase_uid = str(row.get("firebase_uid") or "")
            bucket_name = str(row.get("bucket_name") or "")
            object_key = str(row.get("object_key") or "")
            output_prefix = str(row.get("oci_output_prefix") or "")
            try:
                await asyncio.to_thread(cleanup_pdf_artifacts, bucket_name, object_key, output_prefix)
                await asyncio.to_thread(delete_ingested_file_row, book_id, firebase_uid)
            except Exception as exc:
                mark_storage_delete_failed(book_id, firebase_uid, str(exc))

    async def _maintenance_loop(self) -> None:
        while True:
            try:
                await self.retry_pending_storage_deletes_once()
                await asyncio.sleep(settings.PDF_DELETE_RETRY_INTERVAL_SEC)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("PDF storage maintenance loop failed: %s", exc)
                await asyncio.sleep(settings.PDF_DELETE_RETRY_INTERVAL_SEC)

    async def startup(self) -> None:
        await self.resume_pending_jobs()
        if self._maintenance_task is None or self._maintenance_task.done():
            self._maintenance_task = asyncio.create_task(self._maintenance_loop())

    async def shutdown(self) -> None:
        for task in list(self._parse_tasks.values()):
            task.cancel()
        if self._maintenance_task:
            self._maintenance_task.cancel()
            await asyncio.gather(self._maintenance_task, return_exceptions=True)
            self._maintenance_task = None


pdf_async_ingestion_manager = AsyncPdfIngestionManager()


async def mark_pdf_for_cleanup(book_id: str, firebase_uid: str) -> None:
    record = get_pdf_record(book_id, firebase_uid)
    if not record or not record.get("object_key"):
        delete_ingested_file_row(book_id, firebase_uid)
        return
    set_storage_delete_pending(book_id, firebase_uid)
    await pdf_async_ingestion_manager.retry_pending_storage_deletes_once()
