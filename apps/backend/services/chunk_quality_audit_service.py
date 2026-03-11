from __future__ import annotations

from collections import Counter, defaultdict
import math
import re
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set


_CONNECTOR_START_RE = re.compile(
    r"^(?:ve|veya|ama|ancak|fakat|lakin|ile|ki|de|da|gibi|icin|için|uzere|üzere|dolayisiyla|dolayısıyla|cunku|çünkü|zira|oysa|ise)\b",
    flags=re.IGNORECASE,
)
_TERMINAL_PUNCT_RE = re.compile(r"[.!?…”\"')\]]\s*$")
_PAGE_ARTIFACT_RE = re.compile(
    r"(?:^|\b)(?:sayfa|page)\s*\d{1,4}(?:\s*/\s*\d{1,4})?(?:\b|$)|^\s*#?\s*\d{1,4}\s*$",
    flags=re.IGNORECASE,
)
_REFERENCE_MARKER_RE = re.compile(
    r"\b(?:kaynakça|kaynakca|kaynaklar|references|bibliography|index|dizin|referanslar)\b",
    flags=re.IGNORECASE,
)
_TOC_MARKER_RE = re.compile(
    r"\b(?:içindekiler|icindekiler|contents|table of contents)\b",
    flags=re.IGNORECASE,
)
_YEAR_RE = re.compile(r"\b(?:18|19|20)\d{2}\b")
_OCR_SPACED_LETTERS_RE = re.compile(
    r"(?:\b[ABCDEFGHIJKLMNOPQRSTUVWXYZÇĞİÖŞÜabcdefghijklmnopqrstuvwxyzçğıöşü]\s+){4,}"
    r"[ABCDEFGHIJKLMNOPQRSTUVWXYZÇĞİÖŞÜabcdefghijklmnopqrstuvwxyzçğıöşü]\b"
)
_OCR_NOISE_RE = re.compile(r"(?:Ã.|Ä.|�|~|<;|;\w)")
_WORD_RE = re.compile(r"[A-Za-zÇĞİÖŞÜçğıöşü0-9]+")
_SECTION_MARKER_RE = re.compile(
    r"\b(?:sunu[şs]|onsoz|önsöz|giris|giriş|takdim|icindekiler|içindekiler|"
    r"sonsöz|sonsoz|prolog|epilog|bolum|bölüm|kisim|kısım|chapter|preface|foreword|introduction)\b",
    flags=re.IGNORECASE,
)
_IMPRINT_MARKER_RE = re.compile(
    r"\b(?:yayınları|yayinlari|yayinevi|publisher|publishing|press|copyright|isbn|derg[âa]h)\b",
    flags=re.IGNORECASE,
)
_FRONT_MATTER_MARKER_RE = re.compile(
    r"\b(?:yayınevimiz|yayinevimiz|bu kitap|bu roman|bu dizinin|dizisi içinde|dizisi icinde|"
    r"yayınlamak kararındadır|yayinlamak kararindadir|baskı|baski|basım|basim|kapak|sunuş)\b",
    flags=re.IGNORECASE,
)
_ADDRESS_MARKER_RE = re.compile(
    r"\b(?:mah\.?|mahallesi|cadde|caddesi|sokak|sk\.?|apt\.?|apartmanı|apartmani|"
    r"iş merkezi|is merkezi|blok|kat|no:|posta|istanbul|ankara|izmir|tel\.?|telefon|faks|fax)\b",
    flags=re.IGNORECASE,
)
_CATALOG_ITEM_RE = re.compile(r"\b\d{1,3}\s*[-–]\s*")

_FLOW_FILTER_SOURCE_TYPES = {
    "PDF",
    "EPUB",
    "PDF_CHUNK",
    "BOOK",
    "ARTICLE",
    "WEBSITE",
    "pdf_chunk",
}


def _normalize_spaces(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _word_count(text: str) -> int:
    return len(_WORD_RE.findall(str(text or "")))


def normalize_line_signature(text: str) -> str:
    value = _normalize_spaces(text).lower()
    value = re.sub(r"\b(?:sayfa|page)\b", "", value)
    value = re.sub(r"\d+", "#", value)
    value = re.sub(r"[^a-z0-9çğıöşü# ]+", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def is_reference_like(text: str) -> bool:
    raw = str(text or "")
    if not raw.strip():
        return False
    lowered = raw.lower()
    if _REFERENCE_MARKER_RE.search(lowered):
        return True
    year_count = len(_YEAR_RE.findall(raw))
    if year_count >= 3 and len(raw) < 900:
        return True
    if len(re.findall(r"\([12]\d{3}[a-z]?\)", raw)) >= 2:
        return True
    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    if len(lines) >= 4:
        index_like = sum(1 for line in lines if re.search(r",\s*\d+(?:,\s*\d+)*\s*$", line))
        if index_like / max(1, len(lines)) >= 0.4:
            return True
    return False


def looks_like_table_of_contents(text: str) -> bool:
    raw = str(text or "")
    if not raw.strip():
        return False
    if _TOC_MARKER_RE.search(raw):
        return True
    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    if len(lines) < 4:
        return False
    toc_like_lines = 0
    for line in lines:
        if re.search(r"(?:\.{3,}|\s{3,})\s*\d{1,4}\s*$", line):
            toc_like_lines += 1
        elif re.search(r"^\d+(?:\.\d+)*\s+.+\s+\d{1,4}$", line):
            toc_like_lines += 1
    return toc_like_lines >= 3


def _isolated_letter_ratio(text: str) -> float:
    letters = re.findall(r"\b[A-Za-zÇĞİÖŞÜçğıöşü]\b", str(text or ""))
    words = _word_count(text)
    if words <= 0:
        return 0.0
    return len(letters) / float(words)


def _uppercase_ratio(text: str) -> float:
    letters = re.findall(r"[A-Za-zÇĞİÖŞÜçğıöşü]", str(text or ""))
    if not letters:
        return 0.0
    uppercase = sum(1 for ch in letters if ch.isupper())
    return uppercase / float(len(letters))


def _titlecase_word_ratio(text: str) -> float:
    words = re.findall(r"[A-Za-zÇĞİÖŞÜçğıöşü][A-Za-zÇĞİÖŞÜçğıöşü'-]*", str(text or ""))
    if not words:
        return 0.0
    titlecase = sum(1 for word in words if len(word) > 1 and word[:1].isupper() and word[1:].islower())
    return titlecase / float(len(words))


def looks_like_heading(text: str) -> bool:
    collapsed = _normalize_spaces(text)
    words = _word_count(collapsed)
    if not collapsed or words <= 0 or words > 12 or len(collapsed) > 120:
        return False
    if _TERMINAL_PUNCT_RE.search(collapsed):
        return False
    uppercase_ratio = _uppercase_ratio(collapsed)
    titlecase_ratio = _titlecase_word_ratio(collapsed)
    return bool(
        uppercase_ratio >= 0.68
        or (titlecase_ratio >= 0.85 and words <= 8)
    )


def analyze_chunk_quality(
    text: str,
    *,
    title: str = "",
    author: str = "",
    page_number: Optional[int] = None,
) -> Dict[str, Any]:
    raw = str(text or "")
    collapsed = _normalize_spaces(raw)
    words = _word_count(collapsed)
    starts_with_quote = collapsed.startswith(("\"", "'", "“", "‘", "(", "["))
    starts_lower = bool(collapsed) and collapsed[0].islower() and not starts_with_quote
    starts_connector = bool(_CONNECTOR_START_RE.search(collapsed))
    broken_start = len(collapsed) >= 40 and (starts_lower or starts_connector)
    broken_end = len(collapsed) >= 80 and not bool(_TERMINAL_PUNCT_RE.search(collapsed))
    short_fragment = len(collapsed) < 40 or words < 6
    page_artifact = bool(_PAGE_ARTIFACT_RE.search(collapsed))
    bibliography_like = is_reference_like(raw)
    toc_like = looks_like_table_of_contents(raw)

    lowered = collapsed.lower()
    title_hits = lowered.count(str(title or "").strip().lower()) if len(str(title or "").strip()) >= 4 else 0
    author_hits = lowered.count(str(author or "").strip().lower()) if len(str(author or "").strip()) >= 4 else 0
    weird_spacing = bool(_OCR_SPACED_LETTERS_RE.search(raw))
    mojibake_like = bool(_OCR_NOISE_RE.search(raw))
    isolated_letter_ratio = _isolated_letter_ratio(raw)
    ocr_noise = weird_spacing or mojibake_like or isolated_letter_ratio >= 0.18
    heading_like = looks_like_heading(collapsed)
    imprint_like = bool(_IMPRINT_MARKER_RE.search(collapsed))
    section_marker_like = bool(_SECTION_MARKER_RE.search(collapsed))
    front_matter_marker_like = bool(_FRONT_MATTER_MARKER_RE.search(collapsed))
    catalog_like = bool(
        page_number
        and int(page_number) <= 12
        and (
            len(_CATALOG_ITEM_RE.findall(raw)) >= 2
            or (bool(_CATALOG_ITEM_RE.search(raw)) and raw.count("/") >= 1 and words <= 30)
        )
    )
    address_like = bool(
        page_number
        and int(page_number) <= 12
        and _ADDRESS_MARKER_RE.search(collapsed)
    )
    front_matter_like = bool(
        page_number
        and int(page_number) <= 12
        and (
            heading_like
            or imprint_like
            or section_marker_like
            or front_matter_marker_like
            or catalog_like
            or address_like
            or (title_hits >= 1 and words <= 12)
            or (author_hits >= 1 and words <= 12)
        )
    )
    orphan_fragment = bool(
        broken_start
        and (
            short_fragment
            or (page_number and int(page_number) <= 12)
            or (heading_like and words <= 16)
        )
    )

    flags: List[str] = []
    if broken_start:
        flags.append("broken_start")
    if broken_end:
        flags.append("broken_end")
    if short_fragment:
        flags.append("short_fragment")
    if bibliography_like:
        flags.append("bibliography_like")
    if toc_like:
        flags.append("toc_like")
    if page_artifact:
        flags.append("page_artifact")
    if ocr_noise:
        flags.append("ocr_noise")
    if title_hits >= 2:
        flags.append("title_repeat")
    if author_hits >= 2:
        flags.append("author_repeat")
    if heading_like:
        flags.append("heading_like")
    if imprint_like:
        flags.append("imprint_like")
    if catalog_like:
        flags.append("catalog_like")
    if address_like:
        flags.append("address_like")
    if front_matter_marker_like:
        flags.append("front_matter_marker_like")
    if front_matter_like:
        flags.append("front_matter_like")
    if orphan_fragment:
        flags.append("orphan_fragment")

    score = 1.0
    if broken_start:
        score -= 0.20
    if broken_end:
        score -= 0.20
    if short_fragment:
        score -= 0.25
    if page_artifact:
        score -= 0.35
    if bibliography_like or toc_like:
        score -= 0.60
    if ocr_noise:
        score -= 0.25
    if title_hits >= 2:
        score -= 0.10
    if author_hits >= 2:
        score -= 0.10
    if heading_like:
        score -= 0.18
    if imprint_like:
        score -= 0.22
    if catalog_like:
        score -= 0.40
    if address_like:
        score -= 0.35
    if front_matter_marker_like:
        score -= 0.22
    if front_matter_like:
        score -= 0.45
    if orphan_fragment:
        score -= 0.35
    score = max(0.0, min(1.0, score))

    return {
        "text": collapsed,
        "word_count": words,
        "score": round(score, 3),
        "broken_start": broken_start,
        "broken_end": broken_end,
        "short_fragment": short_fragment,
        "bibliography_like": bibliography_like,
        "toc_like": toc_like,
        "page_artifact": page_artifact,
        "ocr_noise": ocr_noise,
        "title_hits": title_hits,
        "author_hits": author_hits,
        "heading_like": heading_like,
        "imprint_like": imprint_like,
        "catalog_like": catalog_like,
        "address_like": address_like,
        "front_matter_marker_like": front_matter_marker_like,
        "front_matter_like": front_matter_like,
        "orphan_fragment": orphan_fragment,
        "flags": flags,
    }


def should_skip_for_ingestion(
    text: str,
    *,
    title: str = "",
    author: str = "",
    page_number: Optional[int] = None,
) -> tuple[bool, Dict[str, Any]]:
    analysis = analyze_chunk_quality(text, title=title, author=author, page_number=page_number)
    skip = False
    if not analysis["text"]:
        skip = True
    elif analysis["bibliography_like"] or analysis["toc_like"] or analysis["page_artifact"]:
        skip = True
    elif analysis["front_matter_like"] or analysis["imprint_like"] or analysis["catalog_like"] or analysis["address_like"]:
        skip = True
    elif analysis["heading_like"] and analysis["short_fragment"]:
        skip = True
    elif analysis["orphan_fragment"]:
        skip = True
    elif analysis["ocr_noise"] and analysis["short_fragment"]:
        skip = True
    elif analysis["broken_start"] and analysis["broken_end"]:
        skip = True
    elif analysis["broken_start"] and analysis["short_fragment"]:
        skip = True
    elif analysis["broken_end"] and analysis["short_fragment"]:
        skip = True
    elif analysis["score"] < 0.35:
        skip = True
    return skip, analysis


def should_skip_for_flow(text: str, source_type: Optional[str]) -> bool:
    source = str(source_type or "").strip()
    if source not in _FLOW_FILTER_SOURCE_TYPES:
        return False
    skip, analysis = should_skip_for_ingestion(text)
    if skip:
        return True
    return bool(analysis["bibliography_like"] or analysis["toc_like"] or analysis["page_artifact"])


def detect_repeated_margin_signatures(
    pages: Sequence[Dict[str, Any]],
    *,
    sample_depth: int = 2,
    min_occurrences: int = 3,
    min_ratio: float = 0.2,
) -> Set[str]:
    if not pages:
        return set()

    signatures_to_pages: Dict[str, Set[int]] = defaultdict(set)
    page_count = len(pages)

    for page in pages:
        page_num = int(page.get("page_num", 0) or 0)
        lines = list(page.get("lines") or [])
        if not lines:
            continue
        top_lines = lines[:sample_depth]
        bottom_lines = lines[-sample_depth:] if len(lines) > sample_depth else []
        for candidate in [*top_lines, *bottom_lines]:
            line = _normalize_spaces(candidate.get("text", ""))
            if len(line) < 3 or len(line) > 120:
                continue
            if _word_count(line) > 14:
                continue
            signature = normalize_line_signature(line)
            if not signature or signature == "#":
                continue
            signatures_to_pages[signature].add(page_num)

    threshold = max(min_occurrences, int(math.ceil(page_count * min_ratio)))
    return {
        signature
        for signature, seen_pages in signatures_to_pages.items()
        if len(seen_pages) >= threshold
    }


def analyze_book_chunks(
    rows: Iterable[Dict[str, Any]],
    *,
    title: str = "",
    author: str = "",
) -> Dict[str, Any]:
    metrics = Counter()
    sample_issues: List[Dict[str, Any]] = []
    prefix_signatures: Counter[str] = Counter()
    suffix_signatures: Counter[str] = Counter()
    normalized_rows: List[Dict[str, Any]] = []

    for row in rows:
        content = str(row.get("content_chunk") or "")
        page_number = row.get("page_number")
        chunk_id = row.get("id")
        analysis = analyze_chunk_quality(content, title=title, author=author, page_number=page_number)
        normalized_rows.append(
            {
                "id": chunk_id,
                "page_number": page_number,
                "content_chunk": analysis["text"],
                "analysis": analysis,
            }
        )
        for flag in analysis["flags"]:
            metrics[flag] += 1
        words = analysis["text"].split()
        if words:
            prefix_signatures[normalize_line_signature(" ".join(words[:8]))] += 1
            suffix_signatures[normalize_line_signature(" ".join(words[-8:]))] += 1
        if analysis["flags"] and len(sample_issues) < 12:
            sample_issues.append(
                {
                    "id": chunk_id,
                    "page_number": page_number,
                    "flags": analysis["flags"],
                    "snippet": analysis["text"][:220],
                }
            )

    repeated_prefixes = {
        sig for sig, count in prefix_signatures.items()
        if sig and len(sig) > 6 and count >= 3
    }
    repeated_suffixes = {
        sig for sig, count in suffix_signatures.items()
        if sig and len(sig) > 6 and count >= 3
    }
    header_footer_repeat_count = 0
    for row in normalized_rows:
        words = row["content_chunk"].split()
        if not words:
            continue
        prefix_sig = normalize_line_signature(" ".join(words[:8]))
        suffix_sig = normalize_line_signature(" ".join(words[-8:]))
        if prefix_sig in repeated_prefixes or suffix_sig in repeated_suffixes:
            header_footer_repeat_count += 1

    return {
        "total_chunks": len(normalized_rows),
        "broken_start_count": int(metrics["broken_start"]),
        "broken_end_count": int(metrics["broken_end"]),
        "bibliography_like_count": int(metrics["bibliography_like"] + metrics["toc_like"]),
        "header_footer_repeat_count": header_footer_repeat_count,
        "short_fragment_count": int(metrics["short_fragment"]),
        "ocr_noise_count": int(metrics["ocr_noise"]),
        "sample_issues": sample_issues,
    }
