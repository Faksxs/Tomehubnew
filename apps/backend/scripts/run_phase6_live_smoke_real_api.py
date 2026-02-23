"""
Phase 6 live smoke against real local API + real Oracle DB.

Starts a temporary uvicorn process (default lifespan off), uses dev auth bypass,
hits critical endpoints, and writes a markdown report.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

CURRENT_FILE = Path(__file__).resolve()
REPO_ROOT = CURRENT_FILE.parents[3]
BACKEND_DIR = CURRENT_FILE.parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from infrastructure.db_manager import DatabaseManager  # noqa: E402
from services.change_event_service import emit_change_event  # noqa: E402


DEFAULT_REPORT_PATH = REPO_ROOT / "documentation" / "reports" / "PHASE6_LIVE_SMOKE_REAL_API_2026-02-22.md"


@dataclass
class Check:
    name: str
    status: str  # pass|fail|warn
    detail: str
    http_status: int | None = None


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _http_json(method: str, url: str, payload: dict | None = None, timeout: float = 30.0) -> tuple[int, dict]:
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url=url, method=method.upper(), data=data, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = int(resp.getcode())
            raw = resp.read().decode("utf-8", errors="replace")
            return status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(raw) if raw else {}
        except Exception:
            parsed = {"raw": raw}
        return int(e.code), parsed


def _wait_for_docs(base_url: str, timeout_s: float = 30.0) -> bool:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(base_url + "/docs", timeout=2.0) as resp:
                if int(resp.getcode()) >= 200:
                    return True
        except Exception:
            pass
        time.sleep(0.5)
    return False


def _sample_uid_and_book() -> tuple[str, str]:
    DatabaseManager.init_pool()
    with DatabaseManager.get_read_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT li.FIREBASE_UID, li.ITEM_ID
                FROM TOMEHUB_LIBRARY_ITEMS li
                WHERE li.ITEM_TYPE = 'BOOK'
                  AND EXISTS (
                      SELECT 1 FROM TOMEHUB_INGESTED_FILES f
                      WHERE f.FIREBASE_UID = li.FIREBASE_UID
                        AND f.BOOK_ID = li.ITEM_ID
                  )
                ORDER BY li.UPDATED_AT DESC NULLS LAST
                FETCH FIRST 1 ROWS ONLY
                """
            )
            row = cursor.fetchone()
            if not row:
                raise RuntimeError("Could not resolve sample FIREBASE_UID/BOOK_ID with ingestion data")
            return str(row[0]), str(row[1])


def _spawn_server(port: int, lifespan_off: bool) -> subprocess.Popen:
    env = os.environ.copy()
    env["ENVIRONMENT"] = "development"
    env["DEV_UNSAFE_AUTH_BYPASS"] = "true"
    # Force Firebase init off so dev bypass path remains active.
    env["GOOGLE_APPLICATION_CREDENTIALS"] = "__missing__.json"

    cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        "app:app",
        "--app-dir",
        str(BACKEND_DIR),
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
    ]
    if lifespan_off:
        cmd.extend(["--lifespan", "off"])

    stdout_path = REPO_ROOT / "tmp_phase6_live_smoke_stdout.log"
    stderr_path = REPO_ROOT / "tmp_phase6_live_smoke_stderr.log"
    stdout_f = open(stdout_path, "w", encoding="utf-8", errors="replace")
    stderr_f = open(stderr_path, "w", encoding="utf-8", errors="replace")
    proc = subprocess.Popen(cmd, cwd=str(REPO_ROOT), env=env, stdout=stdout_f, stderr=stderr_f)
    proc._phase6_stdout_path = str(stdout_path)  # type: ignore[attr-defined]
    proc._phase6_stderr_path = str(stderr_path)  # type: ignore[attr-defined]
    proc._phase6_stdout_file = stdout_f  # type: ignore[attr-defined]
    proc._phase6_stderr_file = stderr_f  # type: ignore[attr-defined]
    return proc


def _cleanup_server(proc: subprocess.Popen) -> tuple[str, str]:
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)
    # Close redirected files
    try:
        proc._phase6_stdout_file.close()  # type: ignore[attr-defined]
        proc._phase6_stderr_file.close()  # type: ignore[attr-defined]
    except Exception:
        pass
    stdout_text = ""
    stderr_text = ""
    try:
        stdout_text = Path(proc._phase6_stdout_path).read_text(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except Exception:
        pass
    try:
        stderr_text = Path(proc._phase6_stderr_path).read_text(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except Exception:
        pass
    return stdout_text, stderr_text


def main() -> int:
    ap = argparse.ArgumentParser(description="Run Phase 6 live smoke against real API + DB")
    ap.add_argument("--port", type=int, default=0, help="Port (0=auto)")
    ap.add_argument("--lifespan-off", action="store_true", help="Start uvicorn with --lifespan off")
    ap.add_argument("--report-path", help="Output markdown path")
    ap.add_argument("--uid", help="Optional FIREBASE_UID override")
    ap.add_argument("--book-id", help="Optional BOOK_ID override")
    args = ap.parse_args()

    report_path = Path(args.report_path).resolve() if args.report_path else DEFAULT_REPORT_PATH
    port = int(args.port or 0) or _find_free_port()
    base_url = f"http://127.0.0.1:{port}"
    checks: list[Check] = []

    uid = str(args.uid) if args.uid else None
    book_id = str(args.book_id) if args.book_id else None
    if not uid or not book_id:
        uid, book_id = _sample_uid_and_book()

    # Insert an outbox event so realtime poll can prove outbox-first path.
    try:
        event_id = emit_change_event(
            firebase_uid=uid,
            item_id=book_id,
            entity_type="SMOKE",
            event_type="phase6.live_smoke",
            payload={"ts": datetime.now(timezone.utc).isoformat()},
        )
        checks.append(Check("seed_outbox_event", "pass", f"event_id={event_id}"))
    except Exception as e:
        checks.append(Check("seed_outbox_event", "warn", f"{e}"))

    proc = _spawn_server(port=port, lifespan_off=bool(args.lifespan_off))
    stdout_text = ""
    stderr_text = ""
    try:
        if _wait_for_docs(base_url, timeout_s=40.0):
            checks.append(Check("server_ready", "pass", f"{base_url}/docs reachable"))
        else:
            checks.append(Check("server_ready", "fail", "server did not become ready"))
            raise RuntimeError("server not ready")

        # /api/realtime/poll
        q = urllib.parse.urlencode({"firebase_uid": uid, "since_ms": "0", "limit": "10"})
        status, payload = _http_json("GET", f"{base_url}/api/realtime/poll?{q}", timeout=30.0)
        if status == 200 and isinstance(payload, dict) and "changes" in payload and "last_event_id" in payload:
            source = payload.get("source")
            checks.append(Check("realtime_poll", "pass", f"source={source} count={len(payload.get('changes') or [])}", status))
        else:
            checks.append(Check("realtime_poll", "fail", f"unexpected response keys/status payload={str(payload)[:300]}", status))

        # /api/books/{book_id}/ingestion-status
        status, payload = _http_json(
            "GET",
            f"{base_url}/api/books/{urllib.parse.quote(book_id)}/ingestion-status?{urllib.parse.urlencode({'firebase_uid': uid})}",
            timeout=30.0,
        )
        needed = {"match_source", "match_confidence", "item_index_state"}
        if status == 200 and isinstance(payload, dict) and needed.issubset(set(payload.keys())):
            checks.append(
                Check(
                    "ingestion_status",
                    "pass",
                    f"match_source={payload.get('match_source')} confidence={payload.get('match_confidence')}",
                    status,
                )
            )
        else:
            checks.append(Check("ingestion_status", "fail", f"missing fields/status payload={str(payload)[:300]}", status))

        # /api/smart-search
        smart_body = {
            "question": "bilhassa",
            "firebase_uid": uid,
            "limit": 8,
            "offset": 0,
            "include_private_notes": False,
            "visibility_scope": "default",
            "content_type": "HIGHLIGHT",
            "ingestion_type": "MANUAL",
        }
        status, payload = _http_json("POST", f"{base_url}/api/smart-search", smart_body, timeout=90.0)
        md = payload.get("metadata") if isinstance(payload, dict) else None
        if (
            status == 200
            and isinstance(payload, dict)
            and isinstance(md, dict)
            and "visibility_scope" in md
            and "content_type_filter" in md
            and "ingestion_type_filter" in md
        ):
            checks.append(Check("smart_search", "pass", f"total={payload.get('total')} vis={md.get('visibility_scope')}", status))
        else:
            checks.append(Check("smart_search", "fail", f"unexpected response/status payload={str(payload)[:500]}", status))

        # /api/search
        search_body = {
            "question": "bilhassa",
            "firebase_uid": uid,
            "include_private_notes": False,
            "visibility_scope": "default",
        }
        status, payload = _http_json("POST", f"{base_url}/api/search", search_body, timeout=120.0)
        if status == 200 and isinstance(payload, dict) and "answer" in payload and "metadata" in payload:
            checks.append(Check("search", "pass", f"answer_len={len(str(payload.get('answer') or ''))}", status))
        else:
            checks.append(Check("search", "fail", f"unexpected response/status payload={str(payload)[:500]}", status))

    finally:
        stdout_text, stderr_text = _cleanup_server(proc)

    verdict = "PASS" if not any(c.status == "fail" for c in checks) else "FAIL"
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    lines: list[str] = []
    lines.append("# Phase 6 Live Smoke (Real API + DB) Report (2026-02-22)")
    lines.append("")
    lines.append(f"- Generated: `{now}`")
    lines.append(f"- Verdict: `{verdict}`")
    lines.append(f"- Base URL: `{base_url}`")
    lines.append(f"- Uvicorn lifespan off: `{bool(args.lifespan_off)}`")
    lines.append(f"- Sample uid: `{uid}`")
    lines.append(f"- Sample book_id: `{book_id}`")
    lines.append("")
    lines.append("## Checks")
    lines.append("")
    for c in checks:
        lines.append(f"- `{c.name}`: `{c.status}`" + (f" (http={c.http_status})" if c.http_status is not None else "") + f" - {c.detail}")
    lines.append("")
    lines.append("## Server Logs (stderr tail)")
    lines.append("")
    lines.append("```text")
    lines.append("\n".join(stderr_text.splitlines()[-120:]))
    lines.append("```")
    lines.append("")
    lines.append("## Server Logs (stdout tail)")
    lines.append("")
    lines.append("```text")
    lines.append("\n".join(stdout_text.splitlines()[-80:]))
    lines.append("```")
    lines.append("")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[OK] Wrote report: {report_path}")
    print(f"[VERDICT] {verdict}")
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

