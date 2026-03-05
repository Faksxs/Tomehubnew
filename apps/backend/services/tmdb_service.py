from __future__ import annotations

import json
import threading
import time
from typing import Any, Dict, List, Optional
from urllib import parse as urllib_parse
from urllib import request as urllib_request
from urllib.error import HTTPError, URLError

from config import settings
from utils.logger import get_logger

logger = get_logger("tmdb_service")

_CACHE_LOCK = threading.Lock()
_CACHE_TTL_SEC = 600
_CACHE_MAX_ENTRIES = 256
_CACHE: Dict[str, tuple[float, Any]] = {}


def _cache_get(key: str) -> Any:
    now = time.time()
    with _CACHE_LOCK:
        hit = _CACHE.get(key)
        if not hit:
            return None
        ts, payload = hit
        if now - ts > _CACHE_TTL_SEC:
            _CACHE.pop(key, None)
            return None
        return payload


def _cache_set(key: str, payload: Any) -> None:
    with _CACHE_LOCK:
        if len(_CACHE) >= _CACHE_MAX_ENTRIES:
            # Simple bounded cache eviction: drop oldest key.
            oldest_key = min(_CACHE.items(), key=lambda kv: kv[1][0])[0]
            _CACHE.pop(oldest_key, None)
        _CACHE[key] = (time.time(), payload)


def _tmdb_enabled() -> bool:
    return bool(getattr(settings, "MEDIA_TMDB_SYNC_ENABLED", True)) and bool(getattr(settings, "TMDB_API_KEY", ""))


def _tmdb_request(path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    if not _tmdb_enabled():
        return {}

    query = dict(params or {})
    query["api_key"] = settings.TMDB_API_KEY
    url = f"{settings.TMDB_BASE_URL}{path}?{urllib_parse.urlencode(query)}"
    cache_key = f"tmdb:{url}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    req = urllib_request.Request(url=url, method="GET")
    timeout = float(getattr(settings, "TMDB_TIMEOUT_SEC", 8) or 8)
    max_attempts = 2
    for attempt in range(1, max_attempts + 1):
        try:
            with urllib_request.urlopen(req, timeout=timeout) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
                _cache_set(cache_key, payload)
                return payload
        except HTTPError as e:
            body = ""
            try:
                body = e.read().decode("utf-8")
            except Exception:
                body = ""
            logger.warning(f"TMDb HTTP error {e.code} for {path}: {body[:240]}")
            if e.code == 404:
                return {"_not_found": True}
            # Retry only transient HTTP failures.
            if attempt < max_attempts and e.code in {408, 425, 429, 500, 502, 503, 504}:
                continue
            return {}
        except URLError as e:
            logger.warning(f"TMDb URL error for {path}: {e}")
            if attempt < max_attempts:
                continue
            return {}
        except Exception as e:
            logger.warning(f"TMDb unexpected error for {path}: {e}")
            if attempt < max_attempts:
                continue
            return {}
    return {}


def _poster_url(path: Optional[str]) -> Optional[str]:
    p = str(path or "").strip()
    if not p:
        return None
    return f"https://image.tmdb.org/t/p/w500{p}"


def _extract_year_from_date(raw_date: Optional[str]) -> Optional[str]:
    text = str(raw_date or "").strip()
    if len(text) >= 4 and text[:4].isdigit():
        return text[:4]
    return None


def _extract_movie_directors(crew: Any) -> str:
    if not isinstance(crew, list):
        return ""
    names: List[str] = []
    for row in crew:
        if not isinstance(row, dict):
            continue
        if str(row.get("job") or "").strip().lower() != "director":
            continue
        name = str(row.get("name") or "").strip()
        if not name:
            continue
        if name in names:
            continue
        names.append(name)
    return ", ".join(names)


def _extract_series_creators(details: Dict[str, Any], crew: Any) -> str:
    creators: List[str] = []
    for creator in details.get("created_by") or []:
        if not isinstance(creator, dict):
            continue
        name = str(creator.get("name") or "").strip()
        if name and name not in creators:
            creators.append(name)
    if creators:
        return ", ".join(creators)
    # Fallback for sparse TV data.
    if isinstance(crew, list):
        for row in crew:
            if not isinstance(row, dict):
                continue
            job = str(row.get("job") or "").strip().lower()
            if job not in {"creator", "series director"}:
                continue
            name = str(row.get("name") or "").strip()
            if name and name not in creators:
                creators.append(name)
    return ", ".join(creators)


def _extract_cast_top(cast_rows: Any, limit: int = 6) -> List[str]:
    out: List[str] = []
    if not isinstance(cast_rows, list):
        return out
    for row in cast_rows:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or "").strip()
        if not name:
            continue
        if name in out:
            continue
        out.append(name)
        if len(out) >= limit:
            break
    return out


def search_tmdb_media(query: str, kind: str = "multi", page: int = 1, max_results: int = 10, **kwargs) -> List[Dict[str, Any]]:
    text = str(query or "").strip()
    if not text:
        return []
    if not _tmdb_enabled():
        return []

    normalized_kind = str(kind or "multi").strip().lower()
    if normalized_kind not in {"multi", "movie", "tv"}:
        normalized_kind = "multi"

    params: Dict[str, Any] = {
        "query": text,
        "include_adult": "false",
        "page": max(1, int(page or 1)),
    }
    
    # Extract year if provided as a parameter (e.g. from app.py parsing)
    year = kwargs.get("year")
    if year:
        if normalized_kind == "movie":
            params["primary_release_year"] = year
        elif normalized_kind == "tv":
            params["first_air_date_year"] = year

    payload = _tmdb_request(
        f"/search/{normalized_kind}",
        params,
    )
    rows = payload.get("results") if isinstance(payload, dict) else []
    if not isinstance(rows, list):
        return []

    mapped: List[Dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        media_type = str(row.get("media_type") or normalized_kind).strip().lower()
        if media_type == "multi":
            continue
        if media_type not in {"movie", "tv"}:
            continue
        tmdb_id = row.get("id")
        if tmdb_id is None:
            continue
        title = str(row.get("title") or row.get("name") or "").strip()
        if not title:
            continue
        original_title = str(row.get("original_title") or row.get("original_name") or "").strip() or None
        release_date = row.get("release_date") if media_type == "movie" else row.get("first_air_date")
        mapped.append(
            {
                "type": "MOVIE" if media_type == "movie" else "SERIES",
                "tmdbId": int(tmdb_id),
                "tmdbKind": media_type,
                "title": title,
                "originalTitle": original_title,
                "year": _extract_year_from_date(release_date),
                "summary": str(row.get("overview") or "").strip() or None,
                "coverUrl": _poster_url(row.get("poster_path")),
                "tmdbToken": f"tmdb:{media_type}:{int(tmdb_id)}",
            }
        )
        if len(mapped) >= max_results:
            break
    return mapped


def get_tmdb_media_details(kind: str, tmdb_id: int) -> Optional[Dict[str, Any]]:
    normalized_kind = str(kind or "").strip().lower()
    if normalized_kind in {"series", "tv"}:
        normalized_kind = "tv"
    elif normalized_kind == "movie":
        normalized_kind = "movie"
    else:
        return None

    if not _tmdb_enabled():
        return None

    payload = _tmdb_request(
        f"/{normalized_kind}/{int(tmdb_id)}",
        {"append_to_response": "credits,external_ids"},
    )
    if not isinstance(payload, dict) or not payload:
        return None
    if payload.get("_not_found"):
        return {"deleted": True, "tmdbId": int(tmdb_id), "tmdbKind": normalized_kind}

    credits = payload.get("credits") if isinstance(payload.get("credits"), dict) else {}
    external_ids = payload.get("external_ids") if isinstance(payload.get("external_ids"), dict) else {}
    cast_top = _extract_cast_top(credits.get("cast"), limit=6)
    
    genres = []
    if isinstance(payload.get("genres"), list):
        for genre in payload.get("genres"):
            if isinstance(genre, dict) and genre.get("name"):
                genres.append(genre["name"])
                if len(genres) >= 4:
                    break

    if normalized_kind == "movie":
        author = _extract_movie_directors(credits.get("crew"))
    else:
        author = _extract_series_creators(payload, credits.get("crew"))

    imdb_id = str(external_ids.get("imdb_id") or "").strip() or None
    imdb_url = f"https://www.imdb.com/title/{imdb_id}/" if imdb_id else None
    title = str(payload.get("title") or payload.get("name") or "").strip()
    original_title = str(payload.get("original_title") or payload.get("original_name") or "").strip() or None
    summary = str(payload.get("overview") or "").strip() or None
    release_date = payload.get("release_date") if normalized_kind == "movie" else payload.get("first_air_date")
    year = _extract_year_from_date(release_date)

    return {
        "type": "MOVIE" if normalized_kind == "movie" else "SERIES",
        "tmdbId": int(tmdb_id),
        "tmdbKind": normalized_kind,
        "tmdbToken": f"tmdb:{normalized_kind}:{int(tmdb_id)}",
        "title": title or None,
        "originalTitle": original_title,
        "author": author or None,
        "publicationYear": year,
        "summaryText": summary,
        "coverUrl": _poster_url(payload.get("poster_path")),
        "url": imdb_url or f"https://www.themoviedb.org/{'movie' if normalized_kind == 'movie' else 'tv'}/{int(tmdb_id)}",
        "castTop": cast_top,
        "tags": genres,
        "deleted": False,
    }
