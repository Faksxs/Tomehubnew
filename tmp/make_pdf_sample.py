from __future__ import annotations

import sys

import fitz  # type: ignore


def main() -> int:
    if len(sys.argv) != 4:
        print("usage: make_pdf_sample.py <source> <target> <page_count>", file=sys.stderr)
        return 2

    source_path = sys.argv[1]
    target_path = sys.argv[2]
    page_count = max(1, int(sys.argv[3]))

    source = fitz.open(source_path)
    target = fitz.open()
    stop = min(len(source), page_count)
    target.insert_pdf(source, from_page=0, to_page=stop - 1)
    target.save(target_path)
    target.close()
    source.close()
    print(target_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
