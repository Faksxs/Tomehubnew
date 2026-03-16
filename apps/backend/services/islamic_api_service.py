import base64
import html
import json
import re
import threading
import time
from typing import Any, Dict, List, Optional, Tuple
from urllib import parse as urllib_parse
from urllib import request as urllib_request
from urllib.error import HTTPError

from config import settings
from utils.logger import get_logger

logger = get_logger("islamic_api_service")

_QURAN_SIGNAL_TOKENS = {
    "ayet", "ayeti", "ayetler", "sure", "sura", "surah", "kuran", "quran", "meal", "tefsir",
}
_HADITH_SIGNAL_TOKENS = {
    "hadis", "hadith", "sunnet", "sunnah", "sünnet", "buhari", "muslim", "tirmizi",
    "ebu", "ebu davud", "ebu davud", "nesai", "majah", "mace", "müslim",
}
_RELIGIOUS_SIGNAL_TOKENS = _QURAN_SIGNAL_TOKENS.union(
    {
        "allah", "peygamber", "rasul", "resul", "dua", "namaz", "oruç", "oruc",
        "zekat", "fıkıh", "fikih", "akaid", "akide", "iman",
    }
)
_VERSE_KEY_RE = re.compile(r"\b(?P<surah>\d{1,3})\s*[:/]\s*(?P<ayah>\d{1,3})\b")
_HADITH_NUMBER_RE = re.compile(r"\b(?:hadis|hadith)\s*(?:no|numara|number)?\s*[:#]?\s*(\d{1,5})\b", re.IGNORECASE)

_QURAN_TOKEN_CACHE: Dict[str, Any] = {"token": None, "expires_at": 0.0}
_QURAN_TOKEN_LOCK = threading.Lock()
_CATEGORY_CACHE: Dict[str, Dict[str, Any]] = {}
_CATEGORY_CACHE_LOCK = threading.Lock()


def _normalize_ascii(text: str) -> str:
    return (
        str(text or "")
        .lower()
        .replace("ç", "c")
        .replace("ğ", "g")
        .replace("ı", "i")
        .replace("ö", "o")
        .replace("ş", "s")
        .replace("ü", "u")
    )


def _tokenize(text: str) -> List[str]:
    return [tok for tok in re.findall(r"[^\W_]+", _normalize_ascii(text), flags=re.UNICODE) if len(tok) >= 2]


def _query_overlap_score(query: str, candidate: str) -> float:
    q_tokens = set(_tokenize(query))
    if not q_tokens:
        return 0.0
    c_text = _normalize_ascii(candidate)
    hits = sum(1 for tok in q_tokens if tok in c_text)
    return min(1.0, hits / max(1, len(q_tokens)))


def _extract_verse_key(question: str) -> Optional[str]:
    match = _VERSE_KEY_RE.search(str(question or ""))
    if not match:
        return None
    surah = int(match.group("surah"))
    ayah = int(match.group("ayah"))
    if surah < 1 or surah > 114 or ayah < 1:
        return None
    return f"{surah}:{ayah}"


def _looks_quran_query(question: str) -> bool:
    lowered = set(_tokenize(question))
    return bool(lowered.intersection({_normalize_ascii(tok) for tok in _QURAN_SIGNAL_TOKENS})) or bool(
        _extract_verse_key(question)
    )


def _looks_hadith_query(question: str) -> bool:
    lowered = set(_tokenize(question))
    return bool(lowered.intersection({_normalize_ascii(tok) for tok in _HADITH_SIGNAL_TOKENS})) or bool(
        _HADITH_NUMBER_RE.search(str(question or ""))
    )


def is_religious_query(question: str) -> bool:
    lowered = set(_tokenize(question))
    normalized_signals = {_normalize_ascii(tok) for tok in _RELIGIOUS_SIGNAL_TOKENS}
    return bool(lowered.intersection(normalized_signals)) or _looks_quran_query(question) or _looks_hadith_query(question)


def _http_json(
    url: str,
    *,
    timeout_sec: Optional[float] = None,
    headers: Optional[Dict[str, str]] = None,
    data: Optional[bytes] = None,
    method: str = "GET",
) -> Optional[Any]:
    retries = max(0, int(getattr(settings, "ISLAMIC_API_HTTP_MAX_RETRY", 1)))
    req_headers = {"User-Agent": "TomeHub-IslamicExplorer/1.0"}
    if headers:
        req_headers.update({str(k): str(v) for k, v in headers.items()})
    req = urllib_request.Request(url=url, data=data, headers=req_headers, method=method)
    effective_timeout = float(timeout_sec or getattr(settings, "ISLAMIC_API_HTTP_TIMEOUT_SEC", 6.0))
    for idx in range(retries + 1):
        try:
            with urllib_request.urlopen(req, timeout=effective_timeout) as resp:
                charset = resp.headers.get_content_charset() or "utf-8"
                payload = resp.read().decode(charset, errors="replace")
                return json.loads(payload)
        except HTTPError as exc:
            code = int(getattr(exc, "code", 0) or 0)
            if idx < retries and (code == 429 or code >= 500):
                time.sleep(0.2 * (idx + 1))
                continue
            logger.warning("Islamic API HTTP error status=%s url=%s", code, url)
            return None
        except Exception as exc:
            if idx < retries:
                time.sleep(0.2 * (idx + 1))
                continue
            logger.warning("Islamic API HTTP error url=%s error=%s", url, exc)
            return None
    return None


def _build_candidate(
    *,
    provider: str,
    kind: str,
    title: str,
    content_chunk: str,
    score: float,
    external_weight: float,
    reference: Optional[str] = None,
    source_url: Optional[str] = None,
    canonical_reference: Optional[str] = None,
    is_exact_match: bool = False,
    religious_query_kind: Optional[str] = None,
) -> Dict[str, Any]:
    return {
        "title": title,
        "content_chunk": content_chunk.strip(),
        "page_number": 0,
        "source_type": "ISLAMIC_EXTERNAL",
        "score": max(0.0, float(score)),
        "external_weight": float(external_weight),
        "provider": provider,
        "religious_source_kind": kind,
        "reference": reference,
        "canonical_reference": canonical_reference or reference,
        "source_url": source_url,
        "is_exact_match": bool(is_exact_match),
        "religious_query_kind": religious_query_kind,
    }


def _infer_religious_query_kind(question: str) -> str:
    query = str(question or "").strip()
    if _looks_quran_query(query):
        if _extract_verse_key(query):
            if any(tok in _normalize_ascii(query) for tok in ("tefsir", "tafsir")):
                return "TAFSIR_REQUEST"
            return "EXACT_QURAN_VERSE"
        return "TOPICAL_QURAN"
    if _looks_hadith_query(query):
        if _HADITH_NUMBER_RE.search(query):
            return "EXACT_HADITH"
        return "TOPICAL_HADITH"
    return "GENERAL_RELIGIOUS"


def _quran_foundation_token() -> Optional[str]:
    if not bool(getattr(settings, "QURAN_FOUNDATION_ENABLED", False)):
        return None
    now = time.time()
    with _QURAN_TOKEN_LOCK:
        token = str(_QURAN_TOKEN_CACHE.get("token") or "").strip()
        expires_at = float(_QURAN_TOKEN_CACHE.get("expires_at") or 0.0)
        if token and expires_at > now + 30:
            return token

    client_id = str(getattr(settings, "QURAN_FOUNDATION_CLIENT_ID", "") or "").strip()
    client_secret = str(getattr(settings, "QURAN_FOUNDATION_CLIENT_SECRET", "") or "").strip()
    if not client_id or not client_secret:
        return None

    basic = base64.b64encode(f"{client_id}:{client_secret}".encode("utf-8")).decode("ascii")
    token_url = f"{str(getattr(settings, 'QURAN_FOUNDATION_OAUTH_URL', '')).rstrip('/')}/oauth2/token"
    payload = urllib_parse.urlencode(
        {
            "grant_type": "client_credentials",
            "scope": str(getattr(settings, "QURAN_FOUNDATION_CONTENT_SCOPE", "content") or "content"),
        }
    ).encode("utf-8")
    response = _http_json(
        token_url,
        method="POST",
        data=payload,
        headers={
            "Authorization": f"Basic {basic}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    if not isinstance(response, dict):
        return None
    token = str(response.get("access_token") or "").strip()
    expires_in = int(response.get("expires_in") or 0)
    if not token:
        return None
    with _QURAN_TOKEN_LOCK:
        _QURAN_TOKEN_CACHE["token"] = token
        _QURAN_TOKEN_CACHE["expires_at"] = time.time() + max(60, expires_in - 30)
    return token


def _quran_foundation_headers() -> Optional[Dict[str, str]]:
    token = _quran_foundation_token()
    client_id = str(getattr(settings, "QURAN_FOUNDATION_CLIENT_ID", "") or "").strip()
    if not token or not client_id:
        return None
    return {
        "x-auth-token": token,
        "x-client-id": client_id,
    }


def _quran_foundation_search(question: str, limit: int) -> List[Dict[str, Any]]:
    headers = _quran_foundation_headers()
    if not headers:
        return []
    params = {
        "q": question,
        "language": str(getattr(settings, "QURAN_FOUNDATION_DEFAULT_LANGUAGE", "tr") or "tr"),
        "size": max(1, min(int(limit), 5)),
    }
    url = f"{str(getattr(settings, 'QURAN_FOUNDATION_API_BASE_URL', '')).rstrip('/')}/search?{urllib_parse.urlencode(params)}"
    response = _http_json(url, headers=headers)
    rows = (((response or {}).get("search") or {}).get("results") or []) if isinstance(response, dict) else []
    return rows if isinstance(rows, list) else []


def _quran_foundation_fetch_verse(verse_key: str) -> Optional[Dict[str, Any]]:
    headers = _quran_foundation_headers()
    if not headers:
        return None
    params = {
        "language": str(getattr(settings, "QURAN_FOUNDATION_DEFAULT_LANGUAGE", "tr") or "tr"),
        "words": "true",
        "fields": "text_uthmani",
        "translations": ",".join(getattr(settings, "QURAN_FOUNDATION_DEFAULT_TRANSLATION_IDS", ["77"]) or ["77"]),
    }
    url = (
        f"{str(getattr(settings, 'QURAN_FOUNDATION_API_BASE_URL', '')).rstrip('/')}"
        f"/verses/by_key/{verse_key}?{urllib_parse.urlencode(params)}"
    )
    response = _http_json(url, headers=headers)
    verse = (response or {}).get("verse") if isinstance(response, dict) else None
    return verse if isinstance(verse, dict) else None


def _normalize_quran_foundation_search(question: str, rows: List[Dict[str, Any]], limit: int) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    weight = float(getattr(settings, "ISLAMIC_API_QURAN_WEIGHT", 0.22))
    for row in rows[: max(1, limit)]:
        verse_key = str(row.get("verse_key") or "").strip()
        arabic = str(row.get("text") or "").strip()
        translations = row.get("translations") or []
        translation = ""
        translation_name = ""
        if isinstance(translations, list):
            for item in translations:
                if isinstance(item, dict):
                    translation = html.unescape(str(item.get("text") or "")).strip()
                    translation_name = str(item.get("name") or "").strip()
                    if translation:
                        break
        combined = f"{translation} {arabic}".strip()
        overlap = _query_overlap_score(question, combined)
        score = 0.70 + min(0.20, overlap * 0.25)
        provider_title = "Quran.Foundation"
        title = f"{provider_title} - Ayet {verse_key}" if verse_key else provider_title
        content = "\n".join(
            part
            for part in [
                translation,
                arabic,
                f"Kaynak: {translation_name}" if translation_name else "",
            ]
            if part
        )
        if not content:
            continue
        out.append(
            _build_candidate(
                provider="QURAN_FOUNDATION",
                kind="QURAN",
                title=title,
                content_chunk=content,
                score=score,
                external_weight=weight,
                reference=verse_key or None,
                canonical_reference=verse_key or None,
                source_url=f"https://quran.com/{verse_key}" if verse_key else None,
                religious_query_kind="TOPICAL_QURAN",
            )
        )
    return out


def _normalize_quran_foundation_exact(verse: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not isinstance(verse, dict):
        return None
    verse_key = str(verse.get("verse_key") or "").strip()
    arabic = str(verse.get("text_uthmani") or "").strip()
    translations = verse.get("translations") or []
    translation = ""
    translation_name = ""
    if isinstance(translations, list):
        for item in translations:
            if isinstance(item, dict):
                translation = html.unescape(str(item.get("text") or "")).strip()
                translation_name = str(item.get("resource_name") or item.get("name") or "").strip()
                if translation:
                    break
    content = "\n".join(
        part
        for part in [
            translation,
            arabic,
            f"Kaynak: {translation_name}" if translation_name else "",
        ]
        if part
    )
    if not content:
        return None
    return _build_candidate(
        provider="QURAN_FOUNDATION",
        kind="QURAN",
        title=f"Quran.Foundation - Ayet {verse_key}",
        content_chunk=content,
        score=0.86,
        external_weight=float(getattr(settings, "ISLAMIC_API_QURAN_WEIGHT", 0.22)),
        reference=verse_key or None,
        canonical_reference=verse_key or None,
        source_url=f"https://quran.com/{verse_key}" if verse_key else None,
        is_exact_match=True,
        religious_query_kind="EXACT_QURAN_VERSE",
    )


def _diyanet_fetch_chapter(surah_id: int) -> Optional[List[Dict[str, Any]]]:
    if not bool(getattr(settings, "DIYANET_QURAN_ENABLED", False)):
        return None
    api_key = str(getattr(settings, "DIYANET_QURAN_API_KEY", "") or "").strip()
    base_url = str(getattr(settings, "DIYANET_QURAN_BASE_URL", "") or "").strip().rstrip("/")
    if not api_key or not base_url:
        return None
    url = f"{base_url}/api/v1/chapters/{surah_id}"
    response = _http_json(
        url,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )
    rows = (response or {}).get("data") if isinstance(response, dict) else None
    return rows if isinstance(rows, list) else None


def _diyanet_fetch_verse(verse_key: str) -> Optional[Dict[str, Any]]:
    parts = verse_key.split(":", 1)
    if len(parts) != 2:
        return None
    try:
        surah_id = int(parts[0])
        ayah_id = int(parts[1])
    except ValueError:
        return None
    rows = _diyanet_fetch_chapter(surah_id)
    if not rows:
        return None
    for row in rows:
        if int(row.get("verse_id_in_surah") or 0) != ayah_id:
            continue
        arabic = str(((row.get("arabic_script") or {}).get("text")) or "").strip()
        translation = str(((row.get("translation") or {}).get("text")) or "").strip()
        content = "\n".join(part for part in [translation, arabic, "Kaynak: Diyanet"] if part)
        return _build_candidate(
            provider="DIYANET_QURAN",
            kind="QURAN",
            title=f"Diyanet - Ayet {verse_key}",
            content_chunk=content,
            score=0.80,
            external_weight=float(getattr(settings, "ISLAMIC_API_QURAN_WEIGHT", 0.22)),
            reference=verse_key,
            canonical_reference=verse_key,
            source_url=f"{str(getattr(settings, 'DIYANET_QURAN_BASE_URL', '')).rstrip('/')}/api/v1/chapters/{surah_id}",
            is_exact_match=True,
            religious_query_kind="EXACT_QURAN_VERSE",
        )
    return None


def _get_hadeethenc_categories(language: str) -> List[Dict[str, Any]]:
    lang = str(language or "tr").strip().lower() or "tr"
    now = time.time()
    ttl = max(300, int(getattr(settings, "HADEETHENC_CATEGORY_CACHE_TTL_SEC", 21600) or 21600))
    with _CATEGORY_CACHE_LOCK:
        cached = _CATEGORY_CACHE.get(lang)
        if cached and float(cached.get("expires_at") or 0.0) > now:
            return list(cached.get("data") or [])
    url = f"{str(getattr(settings, 'HADEETHENC_API_BASE_URL', '')).rstrip('/')}/categories/list/?language={urllib_parse.quote(lang)}"
    response = _http_json(url)
    rows = response if isinstance(response, list) else []
    with _CATEGORY_CACHE_LOCK:
        _CATEGORY_CACHE[lang] = {"expires_at": now + ttl, "data": rows}
    return rows


def _pick_hadeethenc_category_ids(question: str, limit: int) -> List[str]:
    language = str(getattr(settings, "HADEETHENC_LANGUAGE_PRIMARY", "tr") or "tr")
    categories = _get_hadeethenc_categories(language)
    scored: List[Tuple[float, str]] = []
    query_norm = _normalize_ascii(question)
    for category in categories:
        category_id = str(category.get("id") or "").strip()
        title = str(category.get("title") or "").strip()
        if not category_id or not title:
            continue
        title_norm = _normalize_ascii(title)
        overlap = _query_overlap_score(question, title)
        if overlap <= 0:
            continue
        score = overlap
        if query_norm in title_norm:
            score += 0.25
        scored.append((score, category_id))
    scored.sort(key=lambda item: item[0], reverse=True)
    ordered: List[str] = []
    seen = set()
    for _, category_id in scored:
        if category_id in seen:
            continue
        seen.add(category_id)
        ordered.append(category_id)
        if len(ordered) >= max(1, limit):
            break
    return ordered


def _hadeethenc_fetch_list(category_id: str, limit: int) -> List[Dict[str, Any]]:
    language = str(getattr(settings, "HADEETHENC_LANGUAGE_PRIMARY", "tr") or "tr")
    base_url = str(getattr(settings, "HADEETHENC_API_BASE_URL", "") or "").strip().rstrip("/")
    url = (
        f"{base_url}/hadeeths/list/?language={urllib_parse.quote(language)}"
        f"&category_id={urllib_parse.quote(str(category_id))}&page=1&per_page={max(1, min(limit, 5))}"
    )
    response = _http_json(url)
    rows = (response or {}).get("data") if isinstance(response, dict) else None
    return rows if isinstance(rows, list) else []


def _hadeethenc_fetch_one(hadith_id: str) -> Optional[Dict[str, Any]]:
    language = str(getattr(settings, "HADEETHENC_LANGUAGE_PRIMARY", "tr") or "tr")
    base_url = str(getattr(settings, "HADEETHENC_API_BASE_URL", "") or "").strip().rstrip("/")
    url = f"{base_url}/hadeeths/one/?language={urllib_parse.quote(language)}&id={urllib_parse.quote(str(hadith_id))}"
    response = _http_json(url)
    return response if isinstance(response, dict) else None


def _hadeethenc_candidates(question: str, limit: int) -> List[Dict[str, Any]]:
    if not bool(getattr(settings, "HADEETHENC_ENABLED", False)):
        return []
    category_ids = _pick_hadeethenc_category_ids(question, limit=2)
    if not category_ids:
        return []
    out: List[Dict[str, Any]] = []
    weight = float(getattr(settings, "ISLAMIC_API_HADITH_WEIGHT", 0.18))
    for category_id in category_ids:
        rows = _hadeethenc_fetch_list(category_id, limit=max(2, limit))
        for row in rows:
            hadith_id = str(row.get("id") or "").strip()
            detail = _hadeethenc_fetch_one(hadith_id) if hadith_id else None
            payload = detail or row
            title = str(payload.get("title") or "").strip()
            hadith_text = str(payload.get("hadeeth") or "").strip()
            attribution = str(payload.get("attribution") or "").strip()
            grade = str(payload.get("grade") or "").strip()
            explanation = str(payload.get("explanation") or "").strip()
            combined = " ".join(part for part in [title, hadith_text, explanation] if part)
            overlap = _query_overlap_score(question, combined)
            if overlap <= 0:
                continue
            score = 0.66 + min(0.18, overlap * 0.22)
            content = "\n".join(
                part
                for part in [
                    hadith_text,
                    f"Hukum: {grade}" if grade else "",
                    f"Atif: {attribution}" if attribution else "",
                    explanation,
                ]
                if part
            )
            out.append(
                _build_candidate(
                    provider="HADEETHENC",
                    kind="HADITH",
                    title=f"HadeethEnc - {title or 'Hadis'}",
                    content_chunk=content,
                    score=score,
                    external_weight=weight,
                    reference=hadith_id or None,
                    source_url=f"https://hadeethenc.com/tr/browse/hadith/{hadith_id}" if hadith_id else None,
                    religious_query_kind="TOPICAL_HADITH",
                )
            )
            if len(out) >= max(1, limit):
                return out
    return out


def get_islamic_external_candidates(question: str, limit: int = 4) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    if not bool(getattr(settings, "ISLAMIC_API_ENABLED", False)):
        return [], {"used": False, "providers": {}, "quran_used": False, "hadith_used": False}

    query = str(question or "").strip()
    if not query or not is_religious_query(query):
        return [], {"used": False, "providers": {}, "quran_used": False, "hadith_used": False}

    hard_limit = max(1, min(int(limit or 4), int(getattr(settings, "ISLAMIC_API_MAX_CANDIDATES", 4) or 4)))
    candidates: List[Dict[str, Any]] = []
    provider_counts: Dict[str, int] = {}

    verse_key = _extract_verse_key(query)
    quran_used = False
    hadith_used = False
    religious_query_kind = _infer_religious_query_kind(query)

    if _looks_quran_query(query):
        quran_used = True
        quran_candidates: List[Dict[str, Any]] = []
        if verse_key:
            qf_exact = _normalize_quran_foundation_exact(_quran_foundation_fetch_verse(verse_key) or {})
            if qf_exact:
                quran_candidates.append(qf_exact)
            diyanet_exact = _diyanet_fetch_verse(verse_key)
            if diyanet_exact:
                quran_candidates.append(diyanet_exact)
        else:
            quran_candidates.extend(_normalize_quran_foundation_search(query, _quran_foundation_search(query, hard_limit), hard_limit))
        candidates.extend(quran_candidates[:hard_limit])

    should_use_hadith = _looks_hadith_query(query) or (is_religious_query(query) and not verse_key)
    if should_use_hadith:
        hadith_used = True
        hadith_candidates = _hadeethenc_candidates(query, hard_limit)
        candidates.extend(hadith_candidates[:hard_limit])

    deduped: List[Dict[str, Any]] = []
    seen = set()
    floor = float(getattr(settings, "ISLAMIC_API_MIN_CONFIDENCE", 0.45))
    for candidate in candidates:
        candidate["religious_query_kind"] = candidate.get("religious_query_kind") or religious_query_kind
        if religious_query_kind in {"EXACT_HADITH", "EXACT_QURAN_VERSE"}:
            candidate["is_exact_match"] = bool(candidate.get("is_exact_match", False) or candidate.get("reference"))
        key = (
            str(candidate.get("provider") or "").strip().upper(),
            str(candidate.get("reference") or "").strip(),
            str(candidate.get("content_chunk") or "")[:120],
        )
        if key in seen:
            continue
        seen.add(key)
        if float(candidate.get("score") or 0.0) < floor:
            continue
        deduped.append(candidate)

    deduped.sort(key=lambda item: float(item.get("score") or 0.0), reverse=True)
    deduped = deduped[:hard_limit]
    for candidate in deduped:
        provider = str(candidate.get("provider") or "UNKNOWN").strip().upper()
        provider_counts[provider] = provider_counts.get(provider, 0) + 1

    return deduped, {
        "used": bool(deduped),
        "providers": provider_counts,
        "quran_used": quran_used and any(str(c.get("religious_source_kind")) == "QURAN" for c in deduped),
        "hadith_used": hadith_used and any(str(c.get("religious_source_kind")) == "HADITH" for c in deduped),
        "religious_query_kind": religious_query_kind,
    }
