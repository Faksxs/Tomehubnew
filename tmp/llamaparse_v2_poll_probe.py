from __future__ import annotations

import json
import os
import sys
import time

import requests

from config import settings


def _languages():
    return [part.strip() for part in str(getattr(settings, "PDF_OCR_LANGUAGES", "tr,en") or "tr,en").split(",") if part.strip()]


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: llamaparse_v2_poll_probe.py <pdf_path>", file=sys.stderr)
        return 2

    api_key = str(getattr(settings, "LLAMA_CLOUD_API_KEY", "") or "").strip()
    upload_url = "https://api.cloud.llamaindex.ai/api/parsing/upload"
    pdf_path = sys.argv[1]

    data = [("language", value) for value in _languages()]
    data.extend(
        [
            ("extract_layout", "true"),
            ("spatial_text", "true"),
            ("preserve_layout_alignment_across_pages", "true"),
        ]
    )
    with open(pdf_path, "rb") as handle:
        upload_response = requests.post(
            upload_url,
            headers={"Authorization": f"Bearer {api_key}"},
            data=data,
            files={"file": (os.path.basename(pdf_path), handle, "application/pdf")},
            timeout=120,
        )
    upload_response.raise_for_status()
    upload_payload = upload_response.json()
    job_id = str(upload_payload.get("id") or upload_payload.get("job_id") or "")

    result_url = f"https://api.cloud.llamaindex.ai/api/v2/parse/{job_id}"
    deadline = time.time() + 300
    last_payload = None
    while time.time() < deadline:
        response = requests.get(
            result_url,
            headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json"},
            params=[("expand", "items")],
            timeout=120,
        )
        response.raise_for_status()
        payload = response.json()
        last_payload = payload
        job = payload.get("job") or {}
        status = job.get("status")
        if status == "COMPLETED":
            print(
                json.dumps(
                    {
                        "job_id": job_id,
                        "status": status,
                        "job": job,
                        "items_preview": payload.get("items"),
                    },
                    ensure_ascii=False,
                    indent=2,
                )[:16000]
            )
            return 0
        if status in {"FAILED", "CANCELLED"}:
            print(json.dumps(payload, ensure_ascii=False, indent=2)[:16000])
            return 1
        time.sleep(5)

    print(json.dumps({"job_id": job_id, "status": "TIMEOUT", "last_payload": last_payload}, ensure_ascii=False, indent=2)[:16000])
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
