import json
import re
import time
from typing import Any, Dict, List, Optional, Sequence, Tuple
from urllib import error as urllib_error
from urllib import request as urllib_request

from config import settings
from services.circuit_breaker_service import CircuitBreaker, CircuitBreakerConfig, CircuitBreakerOpenException
from services.monitoring import (
    CIRCUIT_BREAKER_STATE,
    RELIGIOUS_DATASET_SEARCH_LATENCY_MS,
    RELIGIOUS_DATASET_SEARCH_RESULTS,
    RELIGIOUS_DATASET_SEARCH_TOTAL,
)
from utils.logger import get_logger

logger = get_logger("religious_dataset_search_service")

_VERSE_KEY_RE = re.compile(r"\b(?P<surah>\d{1,3})\s*[:/]\s*(?P<ayah>\d{1,3})\b")
_HADITH_NUMBER_RE = re.compile(r"\b(?:hadis|hadith)?\s*(?:no|numara|number)?\s*[:#]?\s*(\d{1,5})\b", re.IGNORECASE)
_COLLECTION_TOKENS = {
    "buhari": "bukhari",
    "bukhari": "bukhari",
    "muslim": "muslim",
    "müslim": "muslim",
    "tirmizi": "tirmidhi",
    "tirmidhi": "tirmidhi",
    "ebu davud": "abu_dawud",
    "abu dawud": "abu_dawud",
    "nesai": "nasai",
    "ibn mace": "ibn_majah",
    "ibn majah": "ibn_majah",
    "mace": "ibn_majah",
    "majah": "ibn_majah",
}
_TURKISH_HINT_TOKENS = {
    "ayet",
    "hadis",
    "hakkinda",
    "ilgili",
    "nedir",
    "ne",
    "namaz",
    "dua",
    "rahmet",
    "merhamet",
    "sabir",
    "niyet",
    "oruç",
    "oruc",
    "zekat",
    "hac",
    "tevbe",
    "gunah",
}
_QURAN_HINT_TOKENS = {"ayet", "ayeti", "ayetler", "ayetleri", "sure", "sura", "surah", "kuran", "quran", "meal", "tefsir"}
_HADITH_HINT_TOKENS = {"hadis", "hadith", "rivayet", "sahih", "bukhari", "buhari", "muslim", "tirmizi", "tirmidhi"}
_QURAN_QUERY_EXPANSIONS: Sequence[Tuple[str, Sequence[str]]] = (
    ("rahmet", ("mercy", "compassion")),
    ("merhamet", ("mercy", "compassion")),
    ("sabir", ("patience", "perseverance")),
    ("namaz", ("prayer", "salah", "salat")),
    ("dua", ("supplication", "invocation")),
    ("zekat", ("charity", "alms", "zakat")),
    ("oruc", ("fasting", "sawm")),
    ("hac", ("pilgrimage", "hajj")),
    ("iman", ("faith", "belief")),
    ("tevhid", ("monotheism", "tawhid")),
    ("tevbe", ("repentance", "tawbah")),
    ("gunah", ("sin", "sins")),
    ("cennet", ("paradise", "garden")),
    ("cehennem", ("hellfire", "hell")),
    ("adalet", ("justice",)),
    ("faiz", ("usury", "interest", "riba")),
    ("nikah", ("marriage", "spouse")),
    ("evlilik", ("marriage", "spouse")),
    ("bosanma", ("divorce",)),
    ("anne baba", ("parents", "mother", "father")),
)

_dataset_breaker: Optional[CircuitBreaker] = None


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


def _extract_verse_key(question: str) -> Optional[str]:
    match = _VERSE_KEY_RE.search(str(question or ""))
    if not match:
        return None
    surah = int(match.group("surah"))
    ayah = int(match.group("ayah"))
    if surah < 1 or surah > 114 or ayah < 1:
        return None
    return f"{surah}:{ayah}"


def _extract_hadith_number(question: str) -> Optional[str]:
    match = _HADITH_NUMBER_RE.search(str(question or ""))
    if not match:
        return None
    return str(match.group(1))


def _infer_hadith_collection(question: str) -> Optional[str]:
    norm = _normalize_ascii(question)
    for token, collection in _COLLECTION_TOKENS.items():
        if token in norm:
            return collection
    return None


def _query_prefers_turkish(question: str) -> bool:
    original = str(question or "")
    if re.search(r"[çğıöşüÇĞİÖŞÜ]", original):
        return True
    return any(token in set(_tokenize(original)) for token in _TURKISH_HINT_TOKENS)


def _query_prefers_quran(question: str) -> bool:
    return any(token in set(_tokenize(question)) for token in _QURAN_HINT_TOKENS)


def _query_prefers_hadith(question: str) -> bool:
    return any(token in set(_tokenize(question)) for token in _HADITH_HINT_TOKENS)


def _expand_quran_query(question: str) -> str:
    original = str(question or "").strip()
    if not original:
        return original
    norm = _normalize_ascii(original)
    extras: List[str] = []
    for phrase, expansion_terms in _QURAN_QUERY_EXPANSIONS:
        if phrase in norm:
            for term in expansion_terms:
                if term not in extras:
                    extras.append(term)
    if not extras:
        return original
    return f"{original} {' '.join(extras)}"


def _build_candidate(
    *,
    provider: str,
    kind: str,
    title: str,
    content_chunk: str,
    score: float,
    external_weight: float,
    reference: Optional[str] = None,
    canonical_reference: Optional[str] = None,
    source_url: Optional[str] = None,
    religious_query_kind: Optional[str] = None,
    is_exact_match: bool = False,
    source_language: Optional[str] = None,
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
        "source_language": source_language,
    }


def _breaker_gauge_value(state: str) -> int:
    return {"closed": 0, "half_open": 1, "open": 2}.get(str(state or "").strip().lower(), 0)


def get_religious_dataset_circuit_breaker() -> CircuitBreaker:
    global _dataset_breaker
    if _dataset_breaker is None:
        _dataset_breaker = CircuitBreaker(
            CircuitBreakerConfig(
                name="religious_dataset_search",
                failure_threshold=max(2, int(getattr(settings, "RELIGIOUS_DATASET_CB_FAILURE_THRESHOLD", 3) or 3)),
                recovery_timeout=max(5, int(getattr(settings, "RELIGIOUS_DATASET_CB_RECOVERY_TIMEOUT_SEC", 30) or 30)),
            )
        )
    return _dataset_breaker


def _update_breaker_metric() -> None:
    try:
        status = get_religious_dataset_circuit_breaker().get_status()
        CIRCUIT_BREAKER_STATE.labels(service="religious_dataset").set(_breaker_gauge_value(status.get("state")))
    except Exception:
        pass


def religious_dataset_search_enabled() -> bool:
    if not bool(getattr(settings, "RELIGIOUS_DATASET_SEARCH_ENABLED", False)):
        return False
    return bool(str(getattr(settings, "RELIGIOUS_DATASET_TYPESENSE_URL", "") or "").strip())


def _typesense_headers() -> Dict[str, str]:
    return {
        "Content-Type": "application/json",
        "X-TYPESENSE-API-KEY": str(getattr(settings, "RELIGIOUS_DATASET_TYPESENSE_API_KEY", "") or "").strip(),
        "User-Agent": "TomeHub-ReligiousDataset/1.0",
    }


def _typesense_request_json(method: str, path: str, payload: Optional[Dict[str, Any]] = None) -> Any:
    base_url = str(getattr(settings, "RELIGIOUS_DATASET_TYPESENSE_URL", "") or "").strip().rstrip("/")
    if not base_url:
        raise RuntimeError("RELIGIOUS_DATASET_TYPESENSE_URL missing")
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib_request.Request(
        url=f"{base_url}{path}",
        method=method.upper(),
        data=data,
        headers=_typesense_headers(),
    )
    timeout_sec = float(getattr(settings, "RELIGIOUS_DATASET_TIMEOUT_SEC", 0.45) or 0.45)
    with urllib_request.urlopen(req, timeout=timeout_sec) as resp:
        charset = resp.headers.get_content_charset() or "utf-8"
        return json.loads(resp.read().decode(charset, errors="replace"))


def _checked_typesense_request(method: str, path: str, payload: Optional[Dict[str, Any]] = None) -> Any:
    started = time.perf_counter()
    try:
        out = get_religious_dataset_circuit_breaker().call(_typesense_request_json, method, path, payload)
        RELIGIOUS_DATASET_SEARCH_TOTAL.labels(status="success", lane="typesense").inc()
        return out
    except CircuitBreakerOpenException:
        RELIGIOUS_DATASET_SEARCH_TOTAL.labels(status="circuit_open", lane="typesense").inc()
        raise
    except urllib_error.HTTPError as exc:
        RELIGIOUS_DATASET_SEARCH_TOTAL.labels(status=f"http_{int(getattr(exc, 'code', 0) or 0)}", lane="typesense").inc()
        raise
    except Exception:
        RELIGIOUS_DATASET_SEARCH_TOTAL.labels(status="error", lane="typesense").inc()
        raise
    finally:
        try:
            RELIGIOUS_DATASET_SEARCH_LATENCY_MS.labels(lane="typesense").observe(
                (time.perf_counter() - started) * 1000.0
            )
        except Exception:
            pass
        _update_breaker_metric()


def _search_payload(
    *,
    collection: str,
    question: str,
    query_by: Sequence[str],
    query_by_weights: Sequence[int],
    limit: int,
    filter_by: Optional[str] = None,
) -> Dict[str, Any]:
    query_by_list = list(query_by)
    payload: Dict[str, Any] = {
        "searches": [
            {
                "collection": collection,
                "q": str(question or "*").strip() or "*",
                "query_by": ",".join(query_by_list),
                "query_by_weights": ",".join(str(int(w)) for w in query_by_weights[: len(query_by_list)]),
                "per_page": max(1, limit),
                "num_typos": ",".join(["1"] * len(query_by_list)),
                "prefix": ",".join(["false"] * len(query_by_list)),
                "highlight_fields": ",".join(query_by_list[:4]),
            }
        ]
    }
    if filter_by:
        payload["searches"][0]["filter_by"] = filter_by
    return payload


def _extract_hits(payload: Any) -> List[Dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    if isinstance(payload.get("results"), list):
        hits: List[Dict[str, Any]] = []
        for result in payload.get("results") or []:
            if not isinstance(result, dict):
                continue
            hits.extend([hit for hit in result.get("hits") or [] if isinstance(hit, dict)])
        return hits
    if isinstance(payload.get("hits"), list):
        return [hit for hit in payload.get("hits") or [] if isinstance(hit, dict)]
    return []


def _query_overlap_score(query: str, candidate: str) -> float:
    q_tokens = set(_tokenize(query))
    if not q_tokens:
        return 0.0
    c_text = _normalize_ascii(candidate)
    hits = sum(1 for tok in q_tokens if tok in c_text)
    return min(1.0, hits / max(1, len(q_tokens)))


def _normalize_quran_doc(doc: Dict[str, Any], *, idx: int, question: str, query_kind: str, exact_ref: Optional[str]) -> Dict[str, Any]:
    translation = str(doc.get("translation_text") or "").strip()
    arabic = str(doc.get("verse_text_ar") or "").strip()
    canonical_ref = str(doc.get("canonical_ref") or "").strip()
    content = "\n".join(part for part in [translation, arabic, "Kaynak: quran-nlp"] if part)
    overlap = _query_overlap_score(question, " ".join([translation, arabic, str(doc.get("lemmas") or ""), str(doc.get("roots") or "")]))
    exact_bonus = 0.12 if exact_ref and canonical_ref == exact_ref else 0.0
    score = max(0.46, 0.69 - (idx * 0.04) + exact_bonus + min(0.08, overlap * 0.10))
    return _build_candidate(
        provider="QURAN_NLP_DATASET",
        kind="QURAN",
        title=f"Quran NLP - Ayet {canonical_ref or 'Quran'}",
        content_chunk=content,
        score=score,
        external_weight=float(getattr(settings, "RELIGIOUS_DATASET_QURAN_WEIGHT", 0.14)),
        reference=canonical_ref or None,
        canonical_reference=canonical_ref or None,
        source_url=str(doc.get("source_url") or "").strip() or None,
        religious_query_kind=query_kind,
        is_exact_match=bool(exact_ref and canonical_ref == exact_ref),
        source_language=str(doc.get("language") or "").strip() or None,
    )


def _normalize_hadith_doc(
    doc: Dict[str, Any],
    *,
    idx: int,
    question: str,
    query_kind: str,
    exact_no: Optional[str],
    exact_collection: Optional[str],
) -> Dict[str, Any]:
    collection = str(doc.get("collection") or "").strip()
    hadith_no = str(doc.get("hadith_no") or "").strip()
    canonical_ref = str(doc.get("canonical_ref") or "").strip()
    grade = str(doc.get("grade") or "").strip()
    text = str(doc.get("text") or "").strip()
    language = str(doc.get("language") or "").strip().lower()
    overlap = _query_overlap_score(question, " ".join([text, collection, grade, str(doc.get("chapter") or "")]))
    exact_bonus = 0.12 if exact_no and hadith_no == exact_no else 0.0
    collection_bonus = 0.05 if exact_collection and collection == exact_collection else 0.0
    language_bonus = 0.03 if _query_prefers_turkish(question) and language == "tur" else 0.0
    score = max(0.50, 0.72 - (idx * 0.03) + exact_bonus + collection_bonus + language_bonus + min(0.12, overlap * 0.15))
    content = "\n".join(part for part in [text, f"Hukum: {grade}" if grade else "", f"Ref: {canonical_ref}" if canonical_ref else ""] if part)
    return _build_candidate(
        provider="HADITH_API_DATASET",
        kind="HADITH",
        title=f"Hadith API - {collection or 'Hadith'} {hadith_no}".strip(),
        content_chunk=content,
        score=score,
        external_weight=float(getattr(settings, "RELIGIOUS_DATASET_HADITH_WEIGHT", 0.13)),
        reference=canonical_ref or hadith_no or None,
        canonical_reference=canonical_ref or hadith_no or None,
        source_url=str(doc.get("source_url") or "").strip() or None,
        religious_query_kind=query_kind,
        is_exact_match=bool(exact_no and hadith_no == exact_no),
        source_language=language or None,
    )


def _search_collection(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    response = _checked_typesense_request("POST", "/multi_search", payload)
    return _extract_hits(response)


def get_religious_dataset_candidates(
    question: str,
    *,
    query_kind: str,
    limit: int = 3,
    skip_exact: bool = False,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    query = str(question or "").strip()
    if not religious_dataset_search_enabled():
        return [], {"used": False, "providers": {}, "reason": "disabled"}
    if not query or skip_exact:
        return [], {"used": False, "providers": {}, "reason": "skipped"}

    topk = max(1, min(int(limit or getattr(settings, "RELIGIOUS_DATASET_TOPK", 3) or 3), 6))
    verse_key = _extract_verse_key(query)
    hadith_no = _extract_hadith_number(query)
    hadith_collection = _infer_hadith_collection(query)
    expanded_quran_query = _expand_quran_query(query)

    quran_collection = str(getattr(settings, "RELIGIOUS_DATASET_QURAN_COLLECTION", "religious_quran_current") or "religious_quran_current").strip()
    hadith_collection_name = str(getattr(settings, "RELIGIOUS_DATASET_HADITH_COLLECTION", "religious_hadith_current") or "religious_hadith_current").strip()

    searches: List[Tuple[str, Dict[str, Any]]] = []
    if query_kind in {"EXACT_QURAN_VERSE", "TOPICAL_QURAN"}:
        searches.append(
            (
                "QURAN",
                _search_payload(
                    collection=quran_collection,
                    question=verse_key or expanded_quran_query,
                    query_by=["canonical_ref", "translation_text", "normalized_text", "lemmas", "roots", "morphology_tags", "verse_text_ar", "embedding_text"],
                    query_by_weights=[16, 12, 10, 7, 6, 6, 2, 1],
                    limit=topk,
                    filter_by=f"canonical_ref:={verse_key}" if verse_key else None,
                ),
            )
        )
    elif query_kind in {"EXACT_HADITH", "TOPICAL_HADITH"}:
        clauses: List[str] = []
        if query_kind == "EXACT_HADITH" and hadith_no:
            clauses.append(f"hadith_no:={hadith_no}")
        if hadith_collection:
            clauses.append(f"collection:={hadith_collection}")
        searches.append(
            (
                "HADITH",
                _search_payload(
                    collection=hadith_collection_name,
                    question=hadith_no or query,
                    query_by=["canonical_ref", "collection", "hadith_no", "tags", "normalized_text", "text", "grade", "embedding_text"],
                    query_by_weights=[16, 12, 11, 8, 7, 6, 3, 1],
                    limit=topk,
                    filter_by=" && ".join(clauses) if clauses else None,
                ),
            )
        )
    else:
        prefer_quran = _query_prefers_quran(query)
        prefer_hadith = _query_prefers_hadith(query) and not prefer_quran
        quran_topk = topk if prefer_quran else max(1, min(2, topk))
        hadith_topk = topk if prefer_hadith else max(0, topk - quran_topk)
        searches.append(
            (
                "QURAN",
                _search_payload(
                    collection=quran_collection,
                    question=expanded_quran_query,
                    query_by=["translation_text", "normalized_text", "lemmas", "roots", "morphology_tags", "verse_text_ar", "embedding_text"],
                    query_by_weights=[14 if prefer_quran else 12, 12 if prefer_quran else 10, 8, 7, 7, 2, 1],
                    limit=quran_topk,
                ),
            )
        )
        if hadith_topk > 0:
            hadith_filter = f"collection:={hadith_collection}" if hadith_collection else None
            searches.append(
                (
                    "HADITH",
                    _search_payload(
                        collection=hadith_collection_name,
                        question=query,
                        query_by=["collection", "tags", "normalized_text", "text", "grade", "embedding_text"],
                        query_by_weights=[14, 8, 8, 7, 3, 1],
                        limit=hadith_topk,
                        filter_by=hadith_filter,
                    ),
                )
            )

    providers: Dict[str, int] = {}
    candidates: List[Dict[str, Any]] = []
    try:
        for lane, payload in searches:
            for idx, hit in enumerate(_search_collection(payload)):
                doc = hit.get("document") if isinstance(hit.get("document"), dict) else {}
                if lane == "QURAN":
                    candidate = _normalize_quran_doc(doc, idx=idx, question=query, query_kind=query_kind, exact_ref=verse_key)
                else:
                    candidate = _normalize_hadith_doc(
                        doc,
                        idx=idx,
                        question=query,
                        query_kind=query_kind,
                        exact_no=hadith_no,
                        exact_collection=hadith_collection,
                    )
                provider = str(candidate.get("provider") or "UNKNOWN").strip().upper()
                providers[provider] = providers.get(provider, 0) + 1
                candidates.append(candidate)
                if len(candidates) >= topk:
                    break
            if len(candidates) >= topk:
                break
    except CircuitBreakerOpenException:
        logger.warning("Religious dataset lane skipped because circuit breaker is open")
        return [], {"used": False, "providers": {}, "reason": "circuit_open"}
    except urllib_error.HTTPError as exc:
        logger.warning("Religious dataset lane HTTP error status=%s", getattr(exc, "code", None))
        return [], {"used": False, "providers": {}, "reason": f"http_{getattr(exc, 'code', 'error')}"}
    except Exception as exc:
        logger.warning("Religious dataset lane failed: %s", exc)
        return [], {"used": False, "providers": {}, "reason": "error"}

    deduped_by_key: Dict[Tuple[str, str], Dict[str, Any]] = {}
    floor = float(getattr(settings, "ISLAMIC_API_MIN_CONFIDENCE", 0.45))
    for candidate in candidates:
        if float(candidate.get("score") or 0.0) < floor:
            continue
        key = (
            str(candidate.get("provider") or "").strip().upper(),
            str(candidate.get("canonical_reference") or candidate.get("reference") or candidate.get("title") or "").strip(),
        )
        existing = deduped_by_key.get(key)
        if existing is None or float(candidate.get("score") or 0.0) > float(existing.get("score") or 0.0):
            deduped_by_key[key] = candidate
    deduped = sorted(
        deduped_by_key.values(),
        key=lambda item: float(item.get("score") or 0.0),
        reverse=True,
    )
    deduped = deduped[:topk]
    try:
        RELIGIOUS_DATASET_SEARCH_RESULTS.labels(lane="typesense").observe(len(deduped))
    except Exception:
        pass
    return deduped, {"used": bool(deduped), "providers": providers, "reason": "ok"}
