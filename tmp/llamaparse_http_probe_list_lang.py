from __future__ import annotations

import json
import os
import sys

import requests

from config import settings


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: llamaparse_http_probe_list_lang.py <pdf_path>", file=sys.stderr)
        return 2

    pdf_path = sys.argv[1]
    api_key = str(getattr(settings, "LLAMA_CLOUD_API_KEY", "") or "").strip()
    upload_url = str(
        getattr(settings, "LLAMA_PARSE_API_URL", "https://api.cloud.llamaindex.ai/api/parsing/upload")
    ).strip()
    languages = [part.strip() for part in str(getattr(settings, "PDF_OCR_LANGUAGES", "tr,en") or "tr,en").split(",") if part.strip()]

    data = []
    for language in languages:
        data.append(("language", language))
    data.extend(
        [
            ("extract_layout", "true"),
            ("spatial_text", "true"),
            ("preserve_layout_alignment_across_pages", "true"),
        ]
    )

    with open(pdf_path, "rb") as handle:
        response = requests.post(
            upload_url,
            headers={"Authorization": f"Bearer {api_key}"},
            data=data,
            files={"file": (os.path.basename(pdf_path), handle, "application/pdf")},
            timeout=120,
        )

    payload = {
        "status_code": response.status_code,
        "headers": dict(response.headers),
        "body_text": response.text[:4000],
    }
    try:
        payload["body_json"] = response.json()
    except Exception:
        payload["body_json"] = None

    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
