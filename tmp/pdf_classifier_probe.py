from __future__ import annotations

import json
import sys

from services.pdf_classifier_service import classify_pdf


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: pdf_classifier_probe.py <pdf_path>", file=sys.stderr)
        return 2

    result = classify_pdf(sys.argv[1])
    payload = {
        "route": result.route,
        "metrics": result.classifier_metrics,
        "sample_pages": [
            {
                "page_number": page.page_number,
                "has_text_layer": page.has_text_layer,
                "char_count": page.char_count,
                "word_count": page.word_count,
                "image_heavy_suspected": page.image_heavy_suspected,
                "garbled_ratio": page.garbled_ratio,
            }
            for page in result.pages[:5]
        ],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
