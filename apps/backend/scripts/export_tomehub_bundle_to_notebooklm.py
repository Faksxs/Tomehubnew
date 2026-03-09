import argparse
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, UTC
from pathlib import Path
from typing import Any, Iterable


CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.dirname(CURRENT_DIR)
sys.path.insert(0, BACKEND_DIR)

from infrastructure.db_manager import DatabaseManager, safe_read_clob
from services.external_api_key_service import resolve_external_api_key
from services.search_service import get_rag_context


DEFAULT_NOTEBOOKLM_PATH = (
    r"C:\Users\aksoy\AppData\Local\Python\pythoncore-3.14-64\Scripts\notebooklm.exe"
)
PDF_TYPES = ("PDF", "EPUB", "PDF_CHUNK", "BOOK_CHUNK")


def _normalize_text(value: Any, limit: int | None = None) -> str:
    text = safe_read_clob(value) if hasattr(value, "read") else str(value or "")
    text = text.strip()
    if limit is not None and len(text) > limit:
        return text[: max(0, limit - 3)].rstrip() + "..."
    return text


def _parse_tags(value: Any) -> list[str]:
    text = _normalize_text(value)
    if not text:
        return []
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        payload = [part.strip() for part in text.split(",") if part.strip()]
    if not isinstance(payload, list):
        return []
    out: list[str] = []
    seen = set()
    for item in payload:
        tag = str(item or "").strip()
        if not tag or tag.lower() in seen:
            continue
        seen.add(tag.lower())
        out.append(tag)
    return out


def _fetch_library_item(owner_uid: str, item_id: str) -> dict[str, Any] | None:
    with DatabaseManager.get_read_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT ITEM_ID, ITEM_TYPE, TITLE, AUTHOR, SUMMARY_TEXT, TAGS_JSON,
                       SEARCH_VISIBILITY, PERSONAL_NOTE_CATEGORY, RATING
                FROM TOMEHUB_LIBRARY_ITEMS
                WHERE FIREBASE_UID = :p_uid
                  AND ITEM_ID = :p_item_id
                  AND NVL(IS_DELETED, 0) = 0
                FETCH FIRST 1 ROWS ONLY
                """,
                {"p_uid": owner_uid, "p_item_id": item_id},
            )
            row = cursor.fetchone()
    if not row:
        return None
    return {
        "item_id": str(row[0]),
        "item_type": _normalize_text(row[1]),
        "title": _normalize_text(row[2]),
        "author": _normalize_text(row[3]),
        "summary_text": _normalize_text(row[4], 1200),
        "tags": _parse_tags(row[5]),
        "search_visibility": _normalize_text(row[6]),
        "personal_note_category": _normalize_text(row[7]),
        "rating": row[8],
    }


def _fetch_library_items(owner_uid: str, limit: int = 200) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with DatabaseManager.get_read_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT ITEM_ID, ITEM_TYPE, TITLE, AUTHOR, SUMMARY_TEXT, TAGS_JSON,
                       SEARCH_VISIBILITY, PERSONAL_NOTE_CATEGORY, RATING
                FROM TOMEHUB_LIBRARY_ITEMS
                WHERE FIREBASE_UID = :p_uid
                  AND NVL(IS_DELETED, 0) = 0
                ORDER BY NVL(UPDATED_AT, CREATED_AT) DESC, ITEM_ID DESC
                FETCH FIRST :p_limit ROWS ONLY
                """,
                {"p_uid": owner_uid, "p_limit": int(limit)},
            )
            for row in cursor.fetchall():
                rows.append(
                    {
                        "item_id": str(row[0]),
                        "item_type": _normalize_text(row[1]),
                        "title": _normalize_text(row[2]),
                        "author": _normalize_text(row[3]),
                        "summary_text": _normalize_text(row[4], 1200),
                        "tags": _parse_tags(row[5]),
                        "search_visibility": _normalize_text(row[6]),
                        "personal_note_category": _normalize_text(row[7]),
                        "rating": row[8],
                    }
                )
    return rows


def _fetch_content_rows(
    *,
    owner_uid: str,
    content_types: Iterable[str],
    item_id: str | None = None,
    limit: int = 200,
    text_query: str | None = None,
) -> list[dict[str, Any]]:
    types = [str(ct).strip().upper() for ct in content_types if str(ct).strip()]
    if not types:
        return []

    placeholders = ", ".join(f":p_ct_{idx}" for idx, _ in enumerate(types))
    params: dict[str, Any] = {"p_uid": owner_uid, "p_limit": int(limit)}
    params.update({f"p_ct_{idx}": value for idx, value in enumerate(types)})

    sql = f"""
        SELECT c.ID,
               c.ITEM_ID,
               c.CONTENT_TYPE,
               c.TITLE,
               c.CONTENT_CHUNK,
               c.PAGE_NUMBER,
               c.COMMENT_TEXT,
               c.TAGS_JSON,
               l.AUTHOR
        FROM TOMEHUB_CONTENT_V2 c
        LEFT JOIN TOMEHUB_LIBRARY_ITEMS l
          ON l.FIREBASE_UID = c.FIREBASE_UID
         AND l.ITEM_ID = c.ITEM_ID
        WHERE c.FIREBASE_UID = :p_uid
          AND c.CONTENT_TYPE IN ({placeholders})
    """
    if item_id:
        sql += " AND c.ITEM_ID = :p_item_id "
        params["p_item_id"] = item_id

    if text_query:
        sql += " AND (LOWER(c.CONTENT_CHUNK) LIKE :p_query OR LOWER(c.TITLE) LIKE :p_query) "
        params["p_query"] = f"%{str(text_query).strip().lower()}%"

    sql += """
        ORDER BY NVL(c.PAGE_NUMBER, 0), NVL(c.CHUNK_INDEX, 0), c.ID
        FETCH FIRST :p_limit ROWS ONLY
    """

    rows: list[dict[str, Any]] = []
    with DatabaseManager.get_read_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(sql, params)
            for row in cursor.fetchall():
                rows.append(
                    {
                        "id": int(row[0]) if row[0] is not None else None,
                        "item_id": _normalize_text(row[1]),
                        "content_type": _normalize_text(row[2]),
                        "title": _normalize_text(row[3]),
                        "content_chunk": _normalize_text(row[4], 4000),
                        "page_number": row[5],
                        "comment_text": _normalize_text(row[6], 800),
                        "tags": _parse_tags(row[7]),
                        "author": _normalize_text(row[8]),
                    }
                )
    return rows


def _fetch_distinct_item_ids_for_types(
    *,
    owner_uid: str,
    content_types: Iterable[str],
    limit: int = 50,
) -> list[str]:
    types = [str(ct).strip().upper() for ct in content_types if str(ct).strip()]
    if not types:
        return []
    placeholders = ", ".join(f":p_ct_{idx}" for idx, _ in enumerate(types))
    params = {"p_uid": owner_uid, "p_limit": int(limit)}
    params.update({f"p_ct_{idx}": value for idx, value in enumerate(types)})
    sql = f"""
        SELECT ITEM_ID
        FROM (
            SELECT ITEM_ID, COUNT(*) AS CNT
            FROM TOMEHUB_CONTENT_V2
            WHERE FIREBASE_UID = :p_uid
              AND ITEM_ID IS NOT NULL
              AND CONTENT_TYPE IN ({placeholders})
            GROUP BY ITEM_ID
            ORDER BY CNT DESC
        )
        FETCH FIRST :p_limit ROWS ONLY
    """
    with DatabaseManager.get_read_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(sql, params)
            return [str(row[0]) for row in cursor.fetchall() if row[0]]


def _group_by_item(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        key = str(row.get("item_id") or "__NO_ITEM__")
        grouped.setdefault(key, []).append(row)
    return grouped


def _render_row(row: dict[str, Any]) -> list[str]:
    lines = [
        f"- Content Type: {row.get('content_type')}",
        f"- Chunk ID: {row.get('id')}",
        f"- Title: {row.get('title')}",
        f"- Author: {row.get('author')}",
        f"- Page: {row.get('page_number')}",
    ]
    tags = row.get("tags") or []
    if tags:
        lines.append(f"- Tags: {', '.join(tags)}")
    comment = str(row.get("comment_text") or "").strip()
    if comment:
        lines.append(f"- Comment: {comment}")
    lines.extend(["", row.get("content_chunk") or "", ""])
    return lines


def build_book_bundle(owner_uid: str, item_id: str, include_pdf_chunks: bool, limit: int) -> tuple[str, dict[str, Any]]:
    item = _fetch_library_item(owner_uid, item_id)
    if not item:
        raise RuntimeError(f"Library item not found: {item_id}")

    content_types = ["HIGHLIGHT", "INSIGHT", "PERSONAL_NOTE"]
    if include_pdf_chunks:
        content_types.extend(PDF_TYPES)
    rows = _fetch_content_rows(owner_uid=owner_uid, content_types=content_types, item_id=item_id, limit=limit)

    lines = [
        f"# TomeHub Book Bundle",
        "",
        f"- Item ID: {item['item_id']}",
        f"- Title: {item['title']}",
        f"- Author: {item['author']}",
        f"- Item Type: {item['item_type']}",
        f"- Generated At: {datetime.now(UTC).isoformat()}",
        "",
    ]
    if item["summary_text"]:
        lines.extend(["## Summary", item["summary_text"], ""])
    if item["tags"]:
        lines.extend(["## Tags", ", ".join(item["tags"]), ""])

    lines.append("## Content")
    lines.append("")
    for row in rows:
        lines.extend(_render_row(row))

    metadata = {
        "bundle_type": "book",
        "item_id": item_id,
        "row_count": len(rows),
        "included_pdf_chunks": bool(include_pdf_chunks),
    }
    return "\n".join(lines).strip() + "\n", metadata


def build_highlights_bundle(owner_uid: str, item_id: str | None, include_pdf_chunks: bool, limit: int) -> tuple[str, dict[str, Any]]:
    rows = _fetch_content_rows(
        owner_uid=owner_uid,
        content_types=("HIGHLIGHT", "INSIGHT"),
        item_id=item_id,
        limit=limit,
    )
    pdf_rows: list[dict[str, Any]] = []
    if include_pdf_chunks:
        target_items = [item_id] if item_id else list(_group_by_item(rows).keys())[:10]
        for target_item in [tid for tid in target_items if tid and tid != "__NO_ITEM__"]:
            pdf_rows.extend(
                _fetch_content_rows(
                    owner_uid=owner_uid,
                    content_types=PDF_TYPES,
                    item_id=target_item,
                    limit=max(20, limit // 2),
                )[:20]
            )

    lines = [
        "# TomeHub Highlights Bundle",
        "",
        f"- Generated At: {datetime.now(UTC).isoformat()}",
        f"- Item Filter: {item_id or 'ALL'}",
        "",
        "## Highlights And Insights",
        "",
    ]
    for row in rows:
        lines.extend(_render_row(row))

    if pdf_rows:
        lines.extend(["## Related PDF Chunks", ""])
        for row in pdf_rows:
            lines.extend(_render_row(row))

    metadata = {
        "bundle_type": "highlights",
        "item_id": item_id,
        "highlight_count": len(rows),
        "pdf_chunk_count": len(pdf_rows),
    }
    return "\n".join(lines).strip() + "\n", metadata


def build_notes_bundle(owner_uid: str, item_id: str | None, include_pdf_chunks: bool, limit: int) -> tuple[str, dict[str, Any]]:
    rows = _fetch_content_rows(
        owner_uid=owner_uid,
        content_types=("PERSONAL_NOTE",),
        item_id=item_id,
        limit=limit,
    )
    pdf_rows: list[dict[str, Any]] = []
    if include_pdf_chunks:
        target_items = [item_id] if item_id else list(_group_by_item(rows).keys())[:10]
        for target_item in [tid for tid in target_items if tid and tid != "__NO_ITEM__"]:
            pdf_rows.extend(
                _fetch_content_rows(
                    owner_uid=owner_uid,
                    content_types=PDF_TYPES,
                    item_id=target_item,
                    limit=max(20, limit // 2),
                )[:20]
            )

    lines = [
        "# TomeHub Notes Bundle",
        "",
        f"- Generated At: {datetime.now(UTC).isoformat()}",
        f"- Item Filter: {item_id or 'ALL'}",
        "",
        "## Personal Notes",
        "",
    ]
    for row in rows:
        lines.extend(_render_row(row))

    if pdf_rows:
        lines.extend(["## Related PDF Chunks", ""])
        for row in pdf_rows:
            lines.extend(_render_row(row))

    metadata = {
        "bundle_type": "notes",
        "item_id": item_id,
        "note_count": len(rows),
        "pdf_chunk_count": len(pdf_rows),
    }
    return "\n".join(lines).strip() + "\n", metadata


def build_topic_bundle(owner_uid: str, query: str, include_private_notes: bool, include_pdf_chunks: bool, limit: int) -> tuple[str, dict[str, Any]]:
    ctx = get_rag_context(
        query,
        owner_uid,
        context_book_id=None,
        mode="STANDARD",
        resource_type=None,
        limit=min(limit, 20),
        offset=0,
        scope_mode="GLOBAL",
        apply_scope_policy=False,
        visibility_scope="all" if include_private_notes else "default",
    )
    if not ctx:
        raise RuntimeError(f"No topic bundle content found for query: {query}")

    rows: list[dict[str, Any]] = []
    seen_keys = set()
    item_ids: list[str] = []
    for chunk in ctx.get("chunks", []):
        key = (chunk.get("id"), chunk.get("content_chunk"))
        if key in seen_keys:
            continue
        seen_keys.add(key)
        item_id = str(chunk.get("book_id") or "").strip() or None
        if item_id and item_id not in item_ids:
            item_ids.append(item_id)
        rows.append(
            {
                "id": chunk.get("id"),
                "item_id": item_id,
                "content_type": str(chunk.get("source_type") or ""),
                "title": str(chunk.get("title") or ""),
                "content_chunk": _normalize_text(chunk.get("content_chunk"), 4000),
                "page_number": chunk.get("page_number"),
                "comment_text": _normalize_text(chunk.get("comment"), 800),
                "tags": _parse_tags(chunk.get("tags")),
                "author": "",
            }
        )

    pdf_rows: list[dict[str, Any]] = []
    if include_pdf_chunks:
        for item_id in item_ids[:8]:
            pdf_rows.extend(
                _fetch_content_rows(
                    owner_uid=owner_uid,
                    content_types=PDF_TYPES,
                    item_id=item_id,
                    limit=12,
                    text_query=query,
                )[:12]
            )

    lines = [
        "# TomeHub Topic Bundle",
        "",
        f"- Query: {query}",
        f"- Generated At: {datetime.now(UTC).isoformat()}",
        f"- Visibility Scope: {'all' if include_private_notes else 'default'}",
        "",
        "## Topic Evidence",
        "",
    ]
    for row in rows:
        lines.extend(_render_row(row))

    if pdf_rows:
        lines.extend(["## Related PDF Chunks", ""])
        for row in pdf_rows:
            lines.extend(_render_row(row))

    metadata = {
        "bundle_type": "topic",
        "query": query,
        "evidence_count": len(rows),
        "pdf_chunk_count": len(pdf_rows),
        "matched_item_count": len(item_ids),
    }
    return "\n".join(lines).strip() + "\n", metadata


def build_library_index_bundle(owner_uid: str, max_items: int) -> tuple[str, dict[str, Any]]:
    items = _fetch_library_items(owner_uid, limit=max_items)
    lines = [
        "# TomeHub Library Index",
        "",
        f"- Generated At: {datetime.now(UTC).isoformat()}",
        f"- Item Count: {len(items)}",
        "",
        "## Items",
        "",
    ]
    for item in items:
        lines.extend(
            [
                f"### {item['title'] or item['item_id']}",
                f"- Item ID: {item['item_id']}",
                f"- Author: {item['author']}",
                f"- Item Type: {item['item_type']}",
                f"- Search Visibility: {item['search_visibility']}",
            ]
        )
        if item.get("personal_note_category"):
            lines.append(f"- Personal Note Category: {item['personal_note_category']}")
        if item.get("rating") is not None:
            lines.append(f"- Rating: {item['rating']}")
        if item.get("tags"):
            lines.append(f"- Tags: {', '.join(item['tags'])}")
        lines.append("")
        if item.get("summary_text"):
            lines.extend([item["summary_text"], ""])

    metadata = {
        "bundle_type": "library_index",
        "item_count": len(items),
    }
    return "\n".join(lines).strip() + "\n", metadata


def build_all_books_bundles(
    owner_uid: str,
    *,
    include_pdf_chunks: bool,
    per_book_limit: int,
    max_books: int,
) -> list[tuple[str, str, dict[str, Any]]]:
    active_item_ids = _fetch_distinct_item_ids_for_types(
        owner_uid=owner_uid,
        content_types=("HIGHLIGHT", "INSIGHT", "PERSONAL_NOTE"),
        limit=max_books,
    )
    bundles: list[tuple[str, str, dict[str, Any]]] = []
    for item_id in active_item_ids:
        item = _fetch_library_item(owner_uid, item_id)
        if not item:
            continue
        markdown, metadata = build_book_bundle(
            owner_uid,
            item["item_id"],
            include_pdf_chunks,
            per_book_limit,
        )
        title_base = item["title"] or item["item_id"]
        bundles.append((f"TomeHub Book - {title_base[:80]}", markdown, metadata))
    return bundles


def write_markdown_file(content: str, output_path: str | None) -> str:
    if output_path:
        target = Path(output_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return str(target)

    fd, temp_path = tempfile.mkstemp(prefix="tomehub_bundle_", suffix=".md")
    os.close(fd)
    Path(temp_path).write_text(content, encoding="utf-8")
    return temp_path


def write_markdown_files(
    bundles: list[tuple[str, str, dict[str, Any]]],
    output_dir: str | None,
) -> list[dict[str, Any]]:
    if output_dir:
        target_dir = Path(output_dir)
        target_dir.mkdir(parents=True, exist_ok=True)
    else:
        target_dir = Path(tempfile.mkdtemp(prefix="tomehub_bundle_batch_"))

    written: list[dict[str, Any]] = []
    for idx, (title, content, metadata) in enumerate(bundles, start=1):
        safe_slug = "".join(ch.lower() if ch.isalnum() else "-" for ch in title).strip("-")
        safe_slug = "-".join(part for part in safe_slug.split("-") if part)[:80] or f"bundle-{idx}"
        path = target_dir / f"{idx:03d}_{safe_slug}.md"
        path.write_text(content, encoding="utf-8")
        written.append(
            {
                "title": title,
                "path": str(path),
                "metadata": metadata,
            }
        )
    return written


def maybe_add_to_notebooklm(
    *,
    notebooklm_path: str,
    notebook_id: str | None,
    markdown_path: str,
    title: str,
) -> None:
    if not notebook_id:
        return
    if not os.path.exists(notebooklm_path):
        raise RuntimeError(f"notebooklm executable not found: {notebooklm_path}")

    completed = subprocess.run(
        [notebooklm_path, "source", "add", markdown_path, "-n", notebook_id, "--title", title],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or completed.stdout.strip() or "NotebookLM source add failed")
    if completed.stdout.strip():
        print(completed.stdout.strip())


def maybe_add_many_to_notebooklm(
    *,
    notebooklm_path: str,
    notebook_id: str | None,
    written_files: list[dict[str, Any]],
) -> None:
    if not notebook_id:
        return
    for entry in written_files:
        maybe_add_to_notebooklm(
            notebooklm_path=notebooklm_path,
            notebook_id=notebook_id,
            markdown_path=entry["path"],
            title=entry["title"],
        )


def resolve_owner_uid_from_api_key(api_key: str) -> str:
    record = resolve_external_api_key(api_key)
    if record is None:
        raise RuntimeError("Invalid external API key")
    return record.owner_firebase_uid


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Export TomeHub bundles to Markdown and optionally add them to NotebookLM."
    )
    parser.add_argument("--api-key", default=None, help="TomeHub external API key")
    parser.add_argument("--owner-uid", default=None, help="Direct owner Firebase UID for local export workflows")
    parser.add_argument(
        "--bundle",
        required=True,
        choices=("book", "highlights", "notes", "topic", "library-index", "all-books"),
        help="Bundle type to export",
    )
    parser.add_argument("--item-id", default=None, help="Library item id for book/highlights/notes bundles")
    parser.add_argument("--query", default=None, help="Topic query for topic bundles")
    parser.add_argument("--limit", type=int, default=120, help="Max rows to fetch")
    parser.add_argument("--max-books", type=int, default=50, help="Max library items for all-books/library-index")
    parser.add_argument("--include-private-notes", action="store_true", help="Allow private notes in topic bundle")
    parser.add_argument("--include-pdf-chunks", action="store_true", help="Append related PDF/EPUB/PDF_CHUNK rows")
    parser.add_argument("--output", default=None, help="Write markdown bundle to this file")
    parser.add_argument("--notebook-id", default=None, help="NotebookLM notebook id")
    parser.add_argument("--title", default=None, help="NotebookLM source title")
    parser.add_argument("--notebooklm-path", default=DEFAULT_NOTEBOOKLM_PATH)
    args = parser.parse_args()

    owner_uid = str(args.owner_uid or "").strip()
    if not owner_uid:
        api_key = str(args.api_key or "").strip()
        if not api_key:
            raise RuntimeError("Either --owner-uid or --api-key is required")
        owner_uid = resolve_owner_uid_from_api_key(api_key)
    limit = max(1, min(int(args.limit), 500))

    try:
        if args.bundle == "book":
            if not args.item_id:
                raise RuntimeError("--item-id is required for bundle=book")
            markdown, metadata = build_book_bundle(owner_uid, args.item_id, args.include_pdf_chunks, limit)
            title = args.title or f"TomeHub Book - {args.item_id}"
            markdown_path = write_markdown_file(markdown, args.output)
            maybe_add_to_notebooklm(
                notebooklm_path=args.notebooklm_path,
                notebook_id=args.notebook_id,
                markdown_path=markdown_path,
                title=title,
            )
            output_payload: dict[str, Any] = {
                "saved_markdown": markdown_path,
                "title": title,
                "notebook_id": args.notebook_id,
                "metadata": metadata,
                "added_to_notebooklm": bool(args.notebook_id),
            }
        elif args.bundle == "highlights":
            markdown, metadata = build_highlights_bundle(owner_uid, args.item_id, args.include_pdf_chunks, limit)
            title = args.title or f"TomeHub Highlights - {args.item_id or 'all'}"
            markdown_path = write_markdown_file(markdown, args.output)
            maybe_add_to_notebooklm(
                notebooklm_path=args.notebooklm_path,
                notebook_id=args.notebook_id,
                markdown_path=markdown_path,
                title=title,
            )
            output_payload = {
                "saved_markdown": markdown_path,
                "title": title,
                "notebook_id": args.notebook_id,
                "metadata": metadata,
                "added_to_notebooklm": bool(args.notebook_id),
            }
        elif args.bundle == "notes":
            markdown, metadata = build_notes_bundle(owner_uid, args.item_id, args.include_pdf_chunks, limit)
            title = args.title or f"TomeHub Notes - {args.item_id or 'all'}"
            markdown_path = write_markdown_file(markdown, args.output)
            maybe_add_to_notebooklm(
                notebooklm_path=args.notebooklm_path,
                notebook_id=args.notebook_id,
                markdown_path=markdown_path,
                title=title,
            )
            output_payload = {
                "saved_markdown": markdown_path,
                "title": title,
                "notebook_id": args.notebook_id,
                "metadata": metadata,
                "added_to_notebooklm": bool(args.notebook_id),
            }
        elif args.bundle == "library-index":
            markdown, metadata = build_library_index_bundle(owner_uid, max(1, min(int(args.max_books), 500)))
            title = args.title or "TomeHub Library Index"
            markdown_path = write_markdown_file(markdown, args.output)
            maybe_add_to_notebooklm(
                notebooklm_path=args.notebooklm_path,
                notebook_id=args.notebook_id,
                markdown_path=markdown_path,
                title=title,
            )
            output_payload = {
                "saved_markdown": markdown_path,
                "title": title,
                "notebook_id": args.notebook_id,
                "metadata": metadata,
                "added_to_notebooklm": bool(args.notebook_id),
            }
        elif args.bundle == "all-books":
            bundles = build_all_books_bundles(
                owner_uid,
                include_pdf_chunks=args.include_pdf_chunks,
                per_book_limit=limit,
                max_books=max(1, min(int(args.max_books), 500)),
            )
            written_files = write_markdown_files(bundles, args.output)
            maybe_add_many_to_notebooklm(
                notebooklm_path=args.notebooklm_path,
                notebook_id=args.notebook_id,
                written_files=written_files,
            )
            output_payload = {
                "bundle": "all-books",
                "notebook_id": args.notebook_id,
                "file_count": len(written_files),
                "files": written_files,
                "added_to_notebooklm": bool(args.notebook_id),
            }
        else:
            if not args.query:
                raise RuntimeError("--query is required for bundle=topic")
            markdown, metadata = build_topic_bundle(
                owner_uid,
                args.query,
                args.include_private_notes,
                args.include_pdf_chunks,
                limit,
            )
            title = args.title or f"TomeHub Topic - {args.query[:80]}"
            markdown_path = write_markdown_file(markdown, args.output)
            maybe_add_to_notebooklm(
                notebooklm_path=args.notebooklm_path,
                notebook_id=args.notebook_id,
                markdown_path=markdown_path,
                title=title,
            )
            output_payload = {
                "saved_markdown": markdown_path,
                "title": title,
                "notebook_id": args.notebook_id,
                "metadata": metadata,
                "added_to_notebooklm": bool(args.notebook_id),
            }

        print(json.dumps(output_payload, ensure_ascii=True, indent=2))
        return 0
    finally:
        DatabaseManager.close_pool()


if __name__ == "__main__":
    raise SystemExit(main())
