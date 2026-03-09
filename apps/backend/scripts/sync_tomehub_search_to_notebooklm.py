import argparse
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, UTC
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


DEFAULT_API_BASE = "http://127.0.0.1:8011"
DEFAULT_NOTEBOOKLM_PATH = (
    r"C:\Users\aksoy\AppData\Local\Python\pythoncore-3.14-64\Scripts\notebooklm.exe"
)


def call_tomehub_search(
    *,
    api_base: str,
    api_key: str,
    query: str,
    limit: int,
    include_private_notes: bool,
) -> dict[str, Any]:
    payload = json.dumps(
        {
            "query": query,
            "limit": limit,
            "include_private_notes": include_private_notes,
        }
    ).encode("utf-8")
    request = Request(
        f"{api_base.rstrip('/')}/ext/v1/search",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "X-API-Key": api_key,
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=60) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"TomeHub search failed ({exc.code}): {body}") from exc
    except URLError as exc:
        raise RuntimeError(f"TomeHub search connection failed: {exc}") from exc


def render_markdown(search_payload: dict[str, Any], query: str) -> str:
    metadata = search_payload.get("metadata", {}) or {}
    results = search_payload.get("results", []) or []
    lines = [
        f"# TomeHub Search Snapshot",
        "",
        f"- Query: {query}",
        f"- Generated At: {datetime.now(UTC).isoformat()}",
        f"- Result Count: {len(results)}",
        f"- Retrieval Path: {metadata.get('retrieval_path')}",
        f"- Visibility Scope: {metadata.get('visibility_scope')}",
        "",
    ]

    for idx, item in enumerate(results, start=1):
        lines.extend(
            [
                f"## Result {idx}",
                f"- Title: {item.get('title')}",
                f"- Source Type: {item.get('source_type')}",
                f"- Item ID: {item.get('item_id')}",
                f"- Chunk ID: {item.get('chunk_id')}",
                f"- Page: {item.get('page_number')}",
                f"- Score: {item.get('score')}",
                "",
                "### Snippet",
                item.get("snippet") or "",
                "",
            ]
        )

        tags = item.get("tags") or []
        if tags:
            lines.append("### Tags")
            lines.append(", ".join(str(tag) for tag in tags))
            lines.append("")

        summary = str(item.get("summary") or "").strip()
        if summary:
            lines.append("### Summary")
            lines.append(summary)
            lines.append("")

        comment = str(item.get("comment") or "").strip()
        if comment:
            lines.append("### Comment")
            lines.append(comment)
            lines.append("")

    return "\n".join(lines).strip() + "\n"


def write_markdown_file(content: str, output_path: str | None) -> str:
    if output_path:
        target = Path(output_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return str(target)

    fd, temp_path = tempfile.mkstemp(prefix="tomehub_notebooklm_", suffix=".md")
    os.close(fd)
    Path(temp_path).write_text(content, encoding="utf-8")
    return temp_path


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

    command = [
        notebooklm_path,
        "source",
        "add",
        markdown_path,
        "-n",
        notebook_id,
        "--title",
        title,
    ]
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        raise RuntimeError(
            "NotebookLM source add failed: "
            + (completed.stderr.strip() or completed.stdout.strip() or "unknown error")
        )
    if completed.stdout.strip():
        print(completed.stdout.strip())


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fetch TomeHub external search results and add them to NotebookLM as a Markdown source."
    )
    parser.add_argument("--query", required=True, help="Search query to send to TomeHub")
    parser.add_argument("--api-key", required=True, help="TomeHub external API key")
    parser.add_argument("--api-base", default=DEFAULT_API_BASE, help="TomeHub API base URL")
    parser.add_argument("--limit", type=int, default=8, help="Max number of results to fetch")
    parser.add_argument(
        "--include-private-notes",
        action="store_true",
        help="Request private-note visibility if the key scope allows it",
    )
    parser.add_argument("--output", default=None, help="Write Markdown snapshot to this file")
    parser.add_argument(
        "--title",
        default=None,
        help="NotebookLM source title (default: TomeHub - <query>)",
    )
    parser.add_argument("--notebook-id", default=None, help="NotebookLM notebook ID")
    parser.add_argument(
        "--notebooklm-path",
        default=DEFAULT_NOTEBOOKLM_PATH,
        help="Path to notebooklm CLI executable",
    )
    args = parser.parse_args()

    title = args.title or f"TomeHub - {args.query[:80]}"

    payload = call_tomehub_search(
        api_base=args.api_base,
        api_key=args.api_key,
        query=args.query,
        limit=max(1, min(int(args.limit), 50)),
        include_private_notes=bool(args.include_private_notes),
    )
    markdown = render_markdown(payload, args.query)
    markdown_path = write_markdown_file(markdown, args.output)

    result = {
        "saved_markdown": markdown_path,
        "title": title,
        "result_count": len(payload.get("results", []) or []),
        "notebook_id": args.notebook_id,
    }

    if args.notebook_id:
        maybe_add_to_notebooklm(
            notebooklm_path=args.notebooklm_path,
            notebook_id=args.notebook_id,
            markdown_path=markdown_path,
            title=title,
        )
        result["added_to_notebooklm"] = True
    else:
        result["added_to_notebooklm"] = False

    print(json.dumps(result, ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
