from __future__ import annotations

import asyncio
import json
import random
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib import parse as urllib_parse
from urllib import request as urllib_request
from urllib.error import HTTPError, URLError

from config import settings
from utils.isbn_utils import equivalent_isbn_set, normalize_valid_isbn
from utils.logger import get_logger

logger = get_logger("book_metadata_resolver")

GOOGLE_MAX_RESULTS = 12
OPENLIB_MAX_RESULTS = 12
NEGATIVE_CACHE_TTL_SEC = 180.0
COVER_CHECK_TTL_SEC = 900.0

_NEGATIVE_CACHE_LOCK = threading.Lock()
_NEGATIVE_CACHE: Dict[str, float] = {}
_COVER_CHECK_CACHE_LOCK = threading.Lock()
_COVER_CHECK_CACHE: Dict[str, Tuple[float, bool]] = {}
_RESOLVER_EXECUTOR = ThreadPoolExecutor(max_workers=6, thread_name_prefix="book-resolver-main")
_PROVIDER_EXECUTOR = ThreadPoolExecutor(max_workers=8, thread_name_prefix="book-resolver-provider")
_CYRILLIC_RE = re.compile(r"[\u0400-\u04FF]")
_LATIN_RE = re.compile(r"[A-Za-z]")

_CYRILLIC_TO_LATIN = {
    "\u0410": "A",
    "\u0411": "B",
    "\u0412": "V",
    "\u0413": "G",
    "\u0414": "D",
    "\u0415": "E",
    "\u0401": "Yo",
    "\u0416": "Zh",
    "\u0417": "Z",
    "\u0418": "I",
    "\u0419": "Y",
    "\u041A": "K",
    "\u041B": "L",
    "\u041C": "M",
    "\u041D": "N",
    "\u041E": "O",
    "\u041F": "P",
    "\u0420": "R",
    "\u0421": "S",
    "\u0422": "T",
    "\u0423": "U",
    "\u0424": "F",
    "\u0425": "Kh",
    "\u0426": "Ts",
    "\u0427": "Ch",
    "\u0428": "Sh",
    "\u0429": "Shch",
    "\u042A": "",
    "\u042B": "Y",
    "\u042C": "",
    "\u042D": "E",
    "\u042E": "Yu",
    "\u042F": "Ya",
    "\u0430": "a",
    "\u0431": "b",
    "\u0432": "v",
    "\u0433": "g",
    "\u0434": "d",
    "\u0435": "e",
    "\u0451": "yo",
    "\u0436": "zh",
    "\u0437": "z",
    "\u0438": "i",
    "\u0439": "y",
    "\u043A": "k",
    "\u043B": "l",
    "\u043C": "m",
    "\u043D": "n",
    "\u043E": "o",
    "\u043F": "p",
    "\u0440": "r",
    "\u0441": "s",
    "\u0442": "t",
    "\u0443": "u",
    "\u0444": "f",
    "\u0445": "kh",
    "\u0446": "ts",
    "\u0447": "ch",
    "\u0448": "sh",
    "\u0449": "shch",
    "\u044A": "",
    "\u044B": "y",
    "\u044C": "",
    "\u044D": "e",
    "\u044E": "yu",
    "\u044F": "ya",
}


def _normalize_query(query: str) -> str:
    return (
        query.strip()
        .lower()
        .replace("ı", "i")
        .replace("İ", "i")
        .replace("ç", "c")
        .replace("ğ", "g")
        .replace("ö", "o")
        .replace("ş", "s")
        .replace("ü", "u")
    )


def _tokenize(query: str) -> List[str]:
    return [t for t in re.split(r"\s+", _normalize_query(query)) if len(t) >= 2]


def _to_ascii_basic(text: str) -> str:
    return (
        text.replace("ç", "c")
        .replace("Ç", "C")
        .replace("ğ", "g")
        .replace("Ğ", "G")
        .replace("ı", "i")
        .replace("İ", "I")
        .replace("ö", "o")
        .replace("Ö", "O")
        .replace("ş", "s")
        .replace("Ş", "S")
        .replace("ü", "u")
        .replace("Ü", "U")
    )


def _build_query_variants(query: str) -> List[str]:
    base = query.strip()
    if not base:
        return []
    variants: List[str] = []
    for candidate in (base, _to_ascii_basic(base)):
        normalized = " ".join(candidate.split())
        if normalized and normalized not in variants:
            variants.append(normalized)
    return variants[:3]


def _build_relaxed_query_fallbacks(query: str) -> List[str]:
    compact = " ".join(str(query or "").split())
    if not compact:
        return []

    tokens = [token for token in compact.split(" ") if token]
    candidates: List[str] = []

    if len(tokens) >= 4:
        candidates.append(" ".join(tokens[:3]))
    if len(tokens) >= 3:
        candidates.append(" ".join(tokens[:-1]))
    if len(tokens) >= 5:
        candidates.append(" ".join(tokens[:4]))

    deduped: List[str] = []
    for candidate in candidates:
        normalized = " ".join(candidate.split()).strip()
        if not normalized or normalized == compact:
            continue
        if normalized in deduped:
            continue
        deduped.append(normalized)
    return deduped[:2]


def _contains_cyrillic(value: str) -> bool:
    return bool(_CYRILLIC_RE.search(str(value or "")))


def _contains_latin(value: str) -> bool:
    return bool(_LATIN_RE.search(str(value or "")))


def _latinize_cyrillic(value: str) -> str:
    if not value:
        return ""
    out: List[str] = []
    for ch in str(value):
        out.append(_CYRILLIC_TO_LATIN.get(ch, ch))
    text = "".join(out)
    text = re.sub(r"\s{2,}", " ", text).strip()
    return text


def _normalize_author_script(
    author: str,
    *,
    title: str = "",
    publisher: str = "",
    source_language_hint: str = "",
) -> str:
    raw_author = str(author or "").strip()
    if not raw_author or not _contains_cyrillic(raw_author):
        return raw_author

    # Keep original script unless surrounding metadata indicates a Latin/Turkish catalog context.
    hint = str(source_language_hint or "").strip().lower()
    latin_context = _contains_latin(title) or _contains_latin(publisher) or hint in {"tr", "en", "tur", "eng"}
    if not latin_context:
        return raw_author

    latinized = _latinize_cyrillic(raw_author)
    return latinized or raw_author


def _is_negative_cached(cache_key: str) -> bool:
    now = time.time()
    with _NEGATIVE_CACHE_LOCK:
        exp = _NEGATIVE_CACHE.get(cache_key)
        if exp is None:
            return False
        if exp < now:
            _NEGATIVE_CACHE.pop(cache_key, None)
            return False
        return True


def _mark_negative_cache(cache_key: str, ttl_sec: float = NEGATIVE_CACHE_TTL_SEC) -> None:
    with _NEGATIVE_CACHE_LOCK:
        _NEGATIVE_CACHE[cache_key] = time.time() + max(1.0, float(ttl_sec))


def _fetch_json_with_retry(
    url: str,
    *,
    provider: str,
    cache_key: str,
    timeout_sec: float,
    max_attempts: int = 3,
) -> Optional[Dict[str, Any]]:
    if _is_negative_cached(cache_key):
        return None

    user_agent = "TomeHub-BookResolver/1.0"
    if provider == "open-library":
        user_agent = "TomeHub-BookResolver/1.0 (+https://tomehub.local)"

    for attempt in range(max_attempts):
        req = urllib_request.Request(
            url=url,
            headers={"User-Agent": user_agent},
            method="GET",
        )
        try:
            with urllib_request.urlopen(req, timeout=timeout_sec) as resp:
                charset = resp.headers.get_content_charset() or "utf-8"
                raw = resp.read().decode(charset, errors="replace")
                return json.loads(raw)
        except HTTPError as exc:
            code = int(getattr(exc, "code", 0) or 0)
            retryable = code in {429, 500, 502, 503, 504}
            if retryable and attempt + 1 < max_attempts:
                wait_s = (0.35 * (2 ** attempt)) + random.uniform(0.05, 0.20)
                time.sleep(wait_s)
                continue
            if retryable:
                _mark_negative_cache(cache_key, ttl_sec=120.0 if code == 429 else 90.0)
            return None
        except (URLError, TimeoutError):
            if attempt + 1 < max_attempts:
                wait_s = (0.30 * (2 ** attempt)) + random.uniform(0.05, 0.15)
                time.sleep(wait_s)
                continue
            _mark_negative_cache(cache_key, ttl_sec=60.0)
            return None
        except Exception:
            return None
    return None


def _normalize_isbn_list(candidates: Any) -> List[str]:
    values = candidates if isinstance(candidates, list) else []
    unique: Set[str] = set()
    for raw in values:
        normalized = normalize_valid_isbn(raw)
        if normalized:
            unique.add(normalized)
    return sorted(unique)


def _pick_preferred_isbn(all_isbns: List[str], query_isbns: Set[str]) -> str:
    if query_isbns:
        for isbn in all_isbns:
            if isbn in query_isbns:
                return isbn
    for isbn in all_isbns:
        if len(isbn) == 13:
            return isbn
    return all_isbns[0] if all_isbns else ""


def _has_isbn_match(item_isbns: List[str], query_isbns: Set[str]) -> bool:
    if not query_isbns:
        return False
    return any(isbn in query_isbns for isbn in item_isbns)


def _sanitize_cover_url(url: Optional[str]) -> Optional[str]:
    raw = str(url or "").strip()
    if not raw:
        return None
    raw = raw.replace("http://", "https://")
    if "edge=curl" in raw:
        raw = raw.replace("&edge=curl", "").replace("?edge=curl", "")
    if "covers.openlibrary.org" in raw and "default=false" not in raw:
        raw = f"{raw}{'&' if '?' in raw else '?'}default=false"
    return raw


def _cover_cache_get(url: str) -> Optional[bool]:
    now = time.time()
    with _COVER_CHECK_CACHE_LOCK:
        hit = _COVER_CHECK_CACHE.get(url)
        if not hit:
            return None
        exp, value = hit
        if exp < now:
            _COVER_CHECK_CACHE.pop(url, None)
            return None
        return value


def _cover_cache_set(url: str, value: bool, ttl: float = COVER_CHECK_TTL_SEC) -> None:
    with _COVER_CHECK_CACHE_LOCK:
        _COVER_CHECK_CACHE[url] = (time.time() + ttl, value)


def _is_viable_cover_url(url: Optional[str]) -> bool:
    raw = _sanitize_cover_url(url)
    if not raw:
        return False
    lowered = raw.lower()
    if any(x in lowered for x in ("placeholder", "default.jpg", "no-cover")):
        return False

    cached = _cover_cache_get(raw)
    if cached is not None:
        return cached

    req = urllib_request.Request(raw, headers={"User-Agent": "TomeHub-BookResolver/1.0"}, method="HEAD")
    try:
        with urllib_request.urlopen(req, timeout=3.0) as resp:
            status_ok = int(getattr(resp, "status", 200) or 200) < 400
            content_type = str(resp.headers.get("Content-Type") or "").lower()
            ok = status_ok and ("image" in content_type or "octet-stream" in content_type)
            _cover_cache_set(raw, ok)
            return ok
    except Exception:
        _cover_cache_set(raw, False, ttl=180.0)
        return False


def _map_openlibrary_bib_entry(entry: Dict[str, Any], query_isbns: Set[str]) -> Optional[Dict[str, Any]]:
    identifiers = entry.get("identifiers") if isinstance(entry, dict) else {}
    all_isbns = _normalize_isbn_list(
        [
            *((identifiers.get("isbn_13") if isinstance(identifiers, dict) else []) or []),
            *((identifiers.get("isbn_10") if isinstance(identifiers, dict) else []) or []),
        ]
    )
    if query_isbns and not _has_isbn_match(all_isbns, query_isbns):
        return None

    publishers = (
        [str(p.get("name") or "").strip() for p in (entry.get("publishers") or []) if isinstance(p, dict)]
        if isinstance(entry, dict)
        else []
    )
    authors = (
        [str(a.get("name") or "").strip() for a in (entry.get("authors") or []) if isinstance(a, dict)]
        if isinstance(entry, dict)
        else []
    )
    cover = entry.get("cover") if isinstance(entry, dict) else {}
    cover_url = _sanitize_cover_url(
        (cover.get("large") if isinstance(cover, dict) else None)
        or (cover.get("medium") if isinstance(cover, dict) else None)
        or (cover.get("small") if isinstance(cover, dict) else None)
    )

    title = str(entry.get("title") or "").strip()
    publisher = publishers[0] if publishers else ""
    author = authors[0] if authors else "Unknown"
    author = _normalize_author_script(author, title=title, publisher=publisher)

    return {
        "title": title,
        "author": author,
        "publisher": publisher,
        "isbn": _pick_preferred_isbn(all_isbns, query_isbns),
        "allIsbns": all_isbns,
        "translator": "",
        "tags": [],
        "summary": str(entry.get("notes") or "").strip(),
        "publishedDate": str(entry.get("publish_date") or "").strip(),
        "url": f"https://openlibrary.org{entry.get('url')}" if entry.get("url") else "",
        "coverUrl": cover_url,
        "pageCount": int(entry.get("number_of_pages") or 0) or None,
        "sourceLanguageHint": "",
        "_provider": "open-library-bib",
    }


def _map_openlibrary_doc(doc: Dict[str, Any], query_isbns: Set[str]) -> Optional[Dict[str, Any]]:
    all_isbns = _normalize_isbn_list(doc.get("isbn") or [])
    if query_isbns and not _has_isbn_match(all_isbns, query_isbns):
        return None
    cover_i = doc.get("cover_i")
    cover_url = _sanitize_cover_url(
        f"https://covers.openlibrary.org/b/id/{cover_i}-M.jpg" if cover_i else None
    )

    title = str(doc.get("title") or "").strip()
    publisher = str((doc.get("publisher") or [""])[0] or "").strip()
    source_lang = str((doc.get("language") or [""])[0] or "").strip()
    author = str((doc.get("author_name") or ["Unknown"])[0] or "Unknown").strip()
    author = _normalize_author_script(author, title=title, publisher=publisher, source_language_hint=source_lang)

    return {
        "title": title,
        "author": author,
        "publisher": publisher,
        "isbn": _pick_preferred_isbn(all_isbns, query_isbns),
        "allIsbns": all_isbns,
        "translator": "",
        "tags": [str(s).strip() for s in (doc.get("subject") or [])[:5] if str(s).strip()],
        "summary": "",
        "publishedDate": str(doc.get("first_publish_year") or "").strip(),
        "url": f"https://openlibrary.org{doc.get('key')}" if doc.get("key") else "",
        "coverUrl": cover_url,
        "pageCount": int(doc.get("number_of_pages_median") or doc.get("number_of_pages") or 0) or None,
        "sourceLanguageHint": source_lang,
        "_provider": "open-library",
    }


def _map_google_item(item: Dict[str, Any], query_isbns: Set[str]) -> Optional[Dict[str, Any]]:
    volume = item.get("volumeInfo") if isinstance(item, dict) else {}
    ids = volume.get("industryIdentifiers") if isinstance(volume, dict) else []
    all_isbns = _normalize_isbn_list([i.get("identifier") for i in ids if isinstance(i, dict)])
    if query_isbns and not _has_isbn_match(all_isbns, query_isbns):
        return None
    links = volume.get("imageLinks") if isinstance(volume, dict) else {}
    cover_url = _sanitize_cover_url(
        (links.get("thumbnail") if isinstance(links, dict) else None)
        or (links.get("smallThumbnail") if isinstance(links, dict) else None)
    )
    source_language_hint = str(volume.get("language") or "").strip()
    title = str(volume.get("title") or "").strip()
    publisher = str(volume.get("publisher") or "").strip()
    author = str((volume.get("authors") or ["Unknown"])[0] or "Unknown").strip()
    author = _normalize_author_script(
        author,
        title=title,
        publisher=publisher,
        source_language_hint=source_language_hint,
    )

    return {
        "title": title,
        "author": author,
        "publisher": publisher,
        "isbn": _pick_preferred_isbn(all_isbns, query_isbns),
        "allIsbns": all_isbns,
        "translator": "",
        "tags": [str(t).strip() for t in (volume.get("categories") or []) if str(t).strip()],
        "summary": str(volume.get("description") or "").strip(),
        "publishedDate": str(volume.get("publishedDate") or "").strip(),
        "url": str(volume.get("infoLink") or "").strip(),
        "coverUrl": cover_url,
        "pageCount": int(volume.get("pageCount") or 0) or None,
        "sourceLanguageHint": source_language_hint,
        "_provider": "google-books",
    }


def _dedupe_results(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen: Set[str] = set()
    unique: List[Dict[str, Any]] = []
    for item in items:
        all_isbns = [i for i in item.get("allIsbns") or [] if i]
        isbn_key = ",".join(sorted(all_isbns))
        fallback_key = f"{_normalize_query(str(item.get('title') or ''))}|{_normalize_query(str(item.get('author') or ''))}"
        key = isbn_key or fallback_key
        if not key or key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def _similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, _normalize_query(a), _normalize_query(b)).ratio()


def _rank_results(query: str, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    query_isbns = equivalent_isbn_set(query)
    q_tokens = set(_tokenize(query))
    if query_isbns:
        provider_bonus = {
            "open-library-bib": 0.12,
            "open-library": 0.08,
            "google-books": 0.05,
        }
        scored: List[Tuple[float, Dict[str, Any]]] = []
        for item in items:
            item_isbns = [i for i in item.get("allIsbns") or [] if i]
            direct = 1.0 if any(i in query_isbns for i in item_isbns) else 0.0
            score = direct + provider_bonus.get(str(item.get("_provider") or ""), 0.0)
            scored.append((score, item))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [s[1] for s in scored]

    scored_text: List[Tuple[float, Dict[str, Any]]] = []
    for item in items:
        title = str(item.get("title") or "")
        author = str(item.get("author") or "")
        title_score = _similarity(query, title)
        author_score = _similarity(query, author)
        token_overlap = 0.0
        title_tokens = set(_tokenize(title))
        if q_tokens and title_tokens:
            token_overlap = len(q_tokens.intersection(title_tokens)) / float(max(1, len(q_tokens)))
        provider_bonus = 0.04 if str(item.get("_provider") or "") == "google-books" else 0.03
        score = (title_score * 0.58) + (author_score * 0.22) + (token_overlap * 0.20) + provider_bonus
        scored_text.append((score, item))
    scored_text.sort(key=lambda x: x[0], reverse=True)
    return [s[1] for s in scored_text]


def _fetch_openlibrary_by_bib(isbn_set: Set[str]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for isbn in isbn_set:
        api_url = (
            "https://openlibrary.org/api/books?"
            + urllib_parse.urlencode({"bibkeys": f"ISBN:{isbn}", "format": "json", "jscmd": "data"})
        )
        data = _fetch_json_with_retry(
            api_url,
            provider="open-library",
            cache_key=f"ol-bib:{isbn}",
            timeout_sec=4.0,
            max_attempts=2,
        )
        entry = (data or {}).get(f"ISBN:{isbn}") if isinstance(data, dict) else None
        if not isinstance(entry, dict):
            continue
        mapped = _map_openlibrary_bib_entry(entry, isbn_set)
        if mapped:
            out.append(mapped)
    return out


def _fetch_openlibrary_search(query: str, *, isbn_mode: bool, isbn_set: Set[str]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    variants = list(isbn_set) if isbn_mode else _build_query_variants(query)
    for variant in variants[:2]:
        params = {
            "limit": OPENLIB_MAX_RESULTS,
            "fields": "key,title,author_name,publisher,first_publish_year,isbn,cover_i,number_of_pages_median,subject",
        }
        if isbn_mode:
            params["isbn"] = variant
        else:
            params["q"] = variant
        api_url = f"https://openlibrary.org/search.json?{urllib_parse.urlencode(params)}"
        data = _fetch_json_with_retry(
            api_url,
            provider="open-library",
            cache_key=f"ol-search:{variant}",
            timeout_sec=4.0,
            max_attempts=2,
        )
        docs = (data or {}).get("docs", []) if isinstance(data, dict) else []
        for doc in docs if isinstance(docs, list) else []:
            if not isinstance(doc, dict):
                continue
            mapped = _map_openlibrary_doc(doc, isbn_set if isbn_mode else set())
            if mapped:
                out.append(mapped)
        if len(out) >= OPENLIB_MAX_RESULTS:
            break
    return out


def _google_query_variants(query: str, isbn_set: Set[str]) -> List[str]:
    if isbn_set:
        return [f"isbn:{isbn}" for isbn in list(isbn_set)[:2]]
    variants = _build_query_variants(query)
    if not variants:
        return []
    out: List[str] = []
    for v in variants[:2]:
        out.append(v)
        out.append(f"intitle:{v}")
    deduped: List[str] = []
    for item in out:
        if item not in deduped:
            deduped.append(item)
    return deduped[:3]


def _fetch_google_books(query: str, isbn_set: Set[str]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    variants = _google_query_variants(query, isbn_set)
    if not variants:
        return out

    api_key = str(getattr(settings, "GOOGLE_BOOKS_API_KEY", "") or "").strip()
    for variant in variants:
        params: Dict[str, Any] = {
            "q": variant,
            "maxResults": GOOGLE_MAX_RESULTS,
            "printType": "books",
        }
        if not isbn_set:
            params["langRestrict"] = "tr"
        if api_key:
            params["key"] = api_key
        api_url = f"https://www.googleapis.com/books/v1/volumes?{urllib_parse.urlencode(params)}"
        data = _fetch_json_with_retry(
            api_url,
            provider="google-books",
            cache_key=f"gbooks:{variant}",
            timeout_sec=4.5,
            max_attempts=3,
        )
        items = (data or {}).get("items", []) if isinstance(data, dict) else []
        for item in items if isinstance(items, list) else []:
            if not isinstance(item, dict):
                continue
            mapped = _map_google_item(item, isbn_set)
            if mapped:
                out.append(mapped)
        if len(out) >= GOOGLE_MAX_RESULTS:
            break
    return out


def _run_provider_fetches_parallel(tasks: List[Tuple[str, Any]]) -> List[Dict[str, Any]]:
    merged: List[Dict[str, Any]] = []
    if not tasks:
        return merged

    futures = [(name, _PROVIDER_EXECUTOR.submit(fn)) for name, fn in tasks]
    for name, future in futures:
        try:
            rows = future.result()
            if isinstance(rows, list):
                merged.extend(rows)
        except Exception as exc:
            logger.warning(
                "Provider fetch failed during parallel resolve",
                extra={"provider_task": name, "error": str(exc)},
            )
    return merged


def _verify_cover_urls(items: List[Dict[str, Any]], top_n: int = 3) -> None:
    checks: List[Tuple[Dict[str, Any], str, Any]] = []
    for idx, item in enumerate(items):
        cover = _sanitize_cover_url(item.get("coverUrl"))
        item["coverUrl"] = cover
        if idx < top_n and cover:
            checks.append((item, cover, _PROVIDER_EXECUTOR.submit(_is_viable_cover_url, cover)))

    for item, cover, future in checks:
        try:
            if not bool(future.result()):
                item["coverUrl"] = None
        except Exception:
            item["coverUrl"] = None

    for item in items:
        item["coverVerified"] = bool(item.get("coverUrl"))


def resolve_book_metadata(query: str, limit: int = 10) -> List[Dict[str, Any]]:
    trimmed = str(query or "").strip()
    if not trimmed:
        return []

    isbn_set = equivalent_isbn_set(trimmed)
    isbn_mode = bool(isbn_set)

    if isbn_mode:
        merged = _run_provider_fetches_parallel(
            [
                ("openlibrary_bib", lambda: _fetch_openlibrary_by_bib(isbn_set)),
                (
                    "openlibrary_search_isbn",
                    lambda: _fetch_openlibrary_search(trimmed, isbn_mode=True, isbn_set=isbn_set),
                ),
                ("google_books_isbn", lambda: _fetch_google_books(trimmed, isbn_set)),
            ]
        )
    else:
        merged = _run_provider_fetches_parallel(
            [
                (
                    "openlibrary_search_text",
                    lambda: _fetch_openlibrary_search(trimmed, isbn_mode=False, isbn_set=set()),
                ),
                ("google_books_text", lambda: _fetch_google_books(trimmed, set())),
            ]
        )

    deduped = _dedupe_results(merged)
    if not deduped and not isbn_mode:
        for relaxed_query in _build_relaxed_query_fallbacks(trimmed):
            relaxed_items = _fetch_openlibrary_search(relaxed_query, isbn_mode=False, isbn_set=set())
            deduped = _dedupe_results(relaxed_items)
            if deduped:
                logger.info(
                    "Book resolver used relaxed query fallback",
                    extra={"query": trimmed, "relaxed_query": relaxed_query, "hits": len(deduped)},
                )
                break

    ranked = _rank_results(trimmed, deduped)
    _verify_cover_urls(ranked, top_n=3)

    for item in ranked:
        all_isbns = [i for i in item.get("allIsbns") or [] if i]
        item["isbnConfidence"] = "high" if item.get("isbn") and normalize_valid_isbn(item.get("isbn")) else "low"
        item["allIsbns"] = all_isbns
        if "coverVerified" not in item:
            item["coverVerified"] = bool(item.get("coverUrl"))
    return ranked[: max(1, int(limit))]


async def resolve_book_metadata_async(query: str, limit: int = 10) -> List[Dict[str, Any]]:
    # Use dedicated resolver executor to avoid blocking LLM/default thread pools.
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_RESOLVER_EXECUTOR, resolve_book_metadata, query, limit)
