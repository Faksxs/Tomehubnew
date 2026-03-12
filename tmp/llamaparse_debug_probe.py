from __future__ import annotations

import json
import sys
import traceback

from services.pdf_classifier_service import classify_pdf
from services.pdf_parser_adapters import LlamaParseAdapter


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: llamaparse_debug_probe.py <pdf_path>", file=sys.stderr)
        return 2

    pdf_path = sys.argv[1]
    classifier_result = classify_pdf(pdf_path)
    adapter = LlamaParseAdapter()
    try:
        document = adapter.parse(
            pdf_path=pdf_path,
            document_id="llamaparse-debug",
            route="IMAGE_SCAN",
            classifier_result=classifier_result,
        )
        print(
            json.dumps(
                {
                    "ok": True,
                    "parser_engine": document.parser_engine,
                    "pages": len(document.pages or []),
                    "blocks": len(document.blocks or []),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    except Exception as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error_type": exc.__class__.__name__,
                    "error_message": str(exc),
                    "traceback": traceback.format_exc(),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
