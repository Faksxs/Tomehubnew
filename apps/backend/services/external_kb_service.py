import json
import re
import threading
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from urllib import parse as urllib_parse
from urllib import request as urllib_request
from urllib.error import HTTPError

import oracledb

from config import settings
from infrastructure.db_manager import DatabaseManager, safe_read_clob
from utils.logger import get_logger

logger = get_logger("external_kb_service")

_ACTIVE_LOCK = threading.Lock()
_ACTIVE_KEYS: set[Tuple[str, str, str]] = set()

_BACKFILL_LOCK = threading.Lock()
_BACKFILL_STATUS: Dict[str, Any] = {
    "running": False,
    "started_at": None,
    "finished_at": None,
    "processed": 0,
    "total": 0,
    "last_error": None,
    "scope_uid": None,
}


def _norm(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def _norm_tags(tags: Any) -> List[str]:
    if tags is None:
        return []
    if isinstance(tags, str):
        text = tags.strip()
        if not text:
            return []
        if text.startswith("[") and text.endswith("]"):
            try:
                arr = json.loads(text)
                if isinstance(arr, list):
                    return [_norm(x) for x in arr if str(x or "").strip()]
            except Exception:
                pass
        return [_norm(x) for x in re.split(r"[;,]", text) if str(x or "").strip()]
    if isinstance(tags, (list, tuple, set)):
        return [_norm(x) for x in tags if str(x or "").strip()]
    return []


def compute_academic_scope(tags: List[str]) -> bool:
    source = set(_norm_tags(tags))
    target = {_norm(t) for t in (getattr(settings, "ACADEMIC_TAG_SET", set()) or set())}
    return bool(source and target and source.intersection(target))


def _as_json(value: Any) -> str:
    return json.dumps(value or {}, ensure_ascii=False)


def _provider_graph_weight(provider: str) -> float:
    p = str(provider or "").strip().upper()
    if p == "DBPEDIA":
        return float(getattr(settings, "EXTERNAL_KB_DBPEDIA_WEIGHT", 0.08))
    if p == "ORKG":
        return float(getattr(settings, "EXTERNAL_KB_ORKG_WEIGHT", 0.10))
    return float(getattr(settings, "EXTERNAL_KB_GRAPH_WEIGHT", 0.15))


def _compact_uri_label(uri: str) -> str:
    text = str(uri or "").strip()
    if not text:
        return ""
    if "/" in text:
        text = text.rsplit("/", 1)[-1]
    if "#" in text:
        text = text.rsplit("#", 1)[-1]
    text = text.replace("_", " ").strip()
    return text[:256]


def _from_json(value: Any) -> Dict[str, Any]:
    raw = value if isinstance(value, str) else safe_read_clob(value)
    try:
        parsed = json.loads(raw or "{}")
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def _pick_lang(bucket: Dict[str, Any]) -> str:
    if not isinstance(bucket, dict):
        return ""
    for lang in ("tr", "en"):
        item = bucket.get(lang)
        if isinstance(item, dict):
            value = str(item.get("value") or "").strip()
            if value:
                return value
    for item in bucket.values():
        if isinstance(item, dict):
            value = str(item.get("value") or "").strip()
            if value:
                return value
    return ""


def _http_get_json(
    url: str,
    timeout_sec: float,
    headers: Optional[Dict[str, str]] = None,
) -> Optional[Dict[str, Any]]:
    retries = max(0, int(getattr(settings, "EXTERNAL_KB_HTTP_MAX_RETRY", 1)))
    request_headers = {"User-Agent": "TomeHub-ExternalKB/1.0"}
    if headers:
        request_headers.update({str(k): str(v) for k, v in headers.items()})
    req = urllib_request.Request(url=url, headers=request_headers, method="GET")
    for idx in range(retries + 1):
        try:
            with urllib_request.urlopen(req, timeout=timeout_sec) as resp:
                charset = resp.headers.get_content_charset() or "utf-8"
                return json.loads(resp.read().decode(charset, errors="replace"))
        except HTTPError as e:
            code = int(getattr(e, "code", 0) or 0)
            if idx < retries and (code == 429 or code >= 500):
                time.sleep(0.2 * (idx + 1))
                continue
            return None
        except Exception:
            if idx < retries:
                time.sleep(0.2 * (idx + 1))
                continue
            return None
    return None


def _wikidata_ids(entity: Dict[str, Any], prop: str) -> List[str]:
    out: List[str] = []
    for claim in (entity.get("claims", {}) or {}).get(prop, []) or []:
        try:
            value = claim["mainsnak"]["datavalue"]["value"]
            if isinstance(value, dict):
                qid = str(value.get("id") or "").strip()
                if qid:
                    out.append(qid)
        except Exception:
            continue
    return list(dict.fromkeys(out))


def _wikidata_strings(entity: Dict[str, Any], prop: str) -> List[str]:
    out: List[str] = []
    for claim in (entity.get("claims", {}) or {}).get(prop, []) or []:
        try:
            value = claim["mainsnak"]["datavalue"]["value"]
            if isinstance(value, str) and value.strip():
                out.append(value.strip())
        except Exception:
            continue
    return list(dict.fromkeys(out))


def _sanitize_wikidata_title(title: str) -> str:
    text = str(title or "").strip()
    if not text:
        return ""
    text = re.sub(r"\(.*?\)", " ", text).strip()
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _iter_wikidata_queries(title: str, author: Optional[str]) -> List[Tuple[str, str]]:
    t_raw = str(title or "").strip()
    t_clean = _sanitize_wikidata_title(t_raw)
    author_raw = str(author or "").strip()
    author_surname = author_raw.split()[-1] if author_raw else ""

    queries: List[str] = []
    if t_raw and author_raw:
        queries.append(f"{t_raw} {author_raw}".strip())
    if t_raw:
        queries.append(t_raw)
    if t_clean and t_clean != t_raw:
        queries.append(t_clean)
    if t_clean and author_surname:
        queries.append(f"{t_clean} {author_surname}".strip())

    deduped = []
    seen = set()
    for q in queries:
        nq = re.sub(r"\s+", " ", q).strip()
        if not nq:
            continue
        key = nq.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(nq)

    langs = ["tr", "en"]
    return [(q, lang) for q in deduped for lang in langs]


def _search_wikidata_hits(query: str, language: str) -> List[Dict[str, Any]]:
    params = {
        "action": "wbsearchentities",
        "search": query,
        "language": language,
        "type": "item",
        "format": "json",
        "limit": 7,
    }
    url = f"https://www.wikidata.org/w/api.php?{urllib_parse.urlencode(params)}"
    data = _http_get_json(url, timeout_sec=float(getattr(settings, "EXTERNAL_KB_WIKIDATA_TIMEOUT_SEC", 2.5)))
    hits = (data or {}).get("search", []) if isinstance(data, dict) else []
    return hits if isinstance(hits, list) else []


def _fetch_wikidata(title: str, author: Optional[str]) -> Optional[Dict[str, Any]]:
    query_plan = _iter_wikidata_queries(title, author)
    if not query_plan:
        return None

    hit = None
    for search_query, lang in query_plan:
        hits = _search_wikidata_hits(search_query, lang)
        if not hits:
            continue
        chosen = hits[0]
        for candidate in hits:
            desc = str(candidate.get("description") or "").lower()
            if any(term in desc for term in ("book", "novel", "work", "kitap", "roman", "eser", "yazar", "author")):
                chosen = candidate
                break
        hit = chosen
        if hit:
            break
    if not hit:
        return None

    qid = str(hit.get("id") or "").strip()
    if not qid:
        return None
    detail = _http_get_json(
        f"https://www.wikidata.org/wiki/Special:EntityData/{qid}.json",
        timeout_sec=float(getattr(settings, "EXTERNAL_KB_WIKIDATA_TIMEOUT_SEC", 2.5)),
    )
    entity = ((detail or {}).get("entities", {}) or {}).get(qid, {}) if isinstance(detail, dict) else {}
    dois = _wikidata_strings(entity, "P356")
    return {
        "qid": qid,
        "label": _pick_lang(entity.get("labels", {}) if isinstance(entity, dict) else {}) or str(hit.get("label") or ""),
        "description": _pick_lang(entity.get("descriptions", {}) if isinstance(entity, dict) else {}) or str(hit.get("description") or ""),
        "doi": dois[0] if dois else None,
        "author_ids": _wikidata_ids(entity, "P50"),
        "genre_ids": _wikidata_ids(entity, "P136"),
    }


def _fetch_openalex(title: str, author: Optional[str]) -> Optional[Dict[str, Any]]:
    query = " ".join(x for x in [str(title or "").strip(), str(author or "").strip()] if x).strip()
    if not query:
        return None
    params = {"search": query, "per-page": 5}
    url = f"https://api.openalex.org/works?{urllib_parse.urlencode(params)}"
    data = _http_get_json(url, timeout_sec=float(getattr(settings, "EXTERNAL_KB_OPENALEX_TIMEOUT_SEC", 3.0)))
    rows = (data or {}).get("results", []) if isinstance(data, dict) else []
    if not rows:
        return None
    best = sorted(rows, key=lambda x: float(x.get("relevance_score") or 0.0), reverse=True)[0]
    return {
        "id": str(best.get("id") or "").strip(),
        "display_name": str(best.get("display_name") or "").strip(),
        "doi": str(best.get("doi") or "").strip() or None,
        "concepts": [
            {
                "id": str(c.get("id") or "").strip(),
                "display_name": str(c.get("display_name") or "").strip(),
                "score": float(c.get("score") or 0.0),
            }
            for c in (best.get("concepts", []) or [])
            if str(c.get("id") or "").strip()
        ][:12],
        "authors": [
            {
                "id": str((a.get("author") or {}).get("id") or "").strip(),
                "display_name": str((a.get("author") or {}).get("display_name") or "").strip(),
            }
            for a in (best.get("authorships", []) or [])
            if str((a.get("author") or {}).get("id") or "").strip()
        ][:10],
    }


def _iter_dbpedia_queries(title: str, author: Optional[str]) -> List[str]:
    t = str(title or "").strip()
    a = str(author or "").strip()
    queries = [t]
    if t and a:
        queries.append(f"{t} {a}")
    deduped: List[str] = []
    seen = set()
    for q in queries:
        nq = re.sub(r"\s+", " ", q).strip()
        if not nq:
            continue
        key = nq.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(nq)
    return deduped


def _dbpedia_lookup_hits(query: str) -> List[Dict[str, Any]]:
    if not query:
        return []

    headers = {"Accept": "application/json"}
    params = {"query": query, "maxResults": 5, "format": "json"}
    urls = [
        f"https://lookup.dbpedia.org/api/search?{urllib_parse.urlencode(params)}",
        f"https://lookup.dbpedia.org/api/search/KeywordSearch?{urllib_parse.urlencode({'QueryString': query, 'MaxHits': 5})}",
    ]
    for url in urls:
        data = _http_get_json(
            url,
            timeout_sec=float(getattr(settings, "EXTERNAL_KB_DBPEDIA_TIMEOUT_SEC", 2.5)),
            headers=headers,
        )
        docs = (data or {}).get("docs", []) if isinstance(data, dict) else []
        if isinstance(docs, list) and docs:
            return docs
    return []


def _fetch_dbpedia(title: str, author: Optional[str]) -> Optional[Dict[str, Any]]:
    for query in _iter_dbpedia_queries(title, author):
        hits = _dbpedia_lookup_hits(query)
        if not hits:
            continue
        doc = hits[0]
        resource_arr = doc.get("resource", []) if isinstance(doc.get("resource"), list) else []
        uri = str(resource_arr[0] or "").strip() if resource_arr else ""
        if not uri:
            continue
        labels = doc.get("label", []) if isinstance(doc.get("label"), list) else []
        comments = doc.get("comment", []) if isinstance(doc.get("comment"), list) else []
        raw_types = doc.get("type", []) if isinstance(doc.get("type"), list) else []
        types = [str(t or "").strip() for t in raw_types if str(t or "").strip()][:8]
        return {
            "resource_uri": uri,
            "label": str(labels[0] or "").strip() if labels else _compact_uri_label(uri),
            "description": str(comments[0] or "").strip() if comments else "",
            "types": types,
            "ref_count": int(float(doc.get("refCount", 0) or 0)),
        }
    return None


def _fetch_orkg(title: str, author: Optional[str]) -> Optional[Dict[str, Any]]:
    query_title = str(title or "").strip()
    if not query_title:
        return None

    timeout = float(getattr(settings, "EXTERNAL_KB_ORKG_TIMEOUT_SEC", 3.0))
    urls = [
        f"https://orkg.org/api/papers?{urllib_parse.urlencode({'title': query_title, 'size': 5})}",
        f"https://orkg.org/api/papers?{urllib_parse.urlencode({'q': query_title, 'size': 5})}",
    ]
    rows: List[Dict[str, Any]] = []
    for url in urls:
        data = _http_get_json(url, timeout_sec=timeout)
        if not isinstance(data, dict):
            continue
        content = data.get("content", [])
        if isinstance(content, list) and content:
            rows = content
            break
    if not rows:
        return None

    author_hint = str(author or "").strip().lower()
    best = rows[0]
    for row in rows:
        row_title = str(row.get("title") or "").strip().lower()
        if row_title and row_title == query_title.lower():
            best = row
            break
        if author_hint:
            joined = " ".join(
                str(a.get("name") or "")
                for a in (row.get("authors", []) or [])
                if isinstance(a, dict)
            ).lower()
            if author_hint and author_hint in joined:
                best = row
                break

    rid = str(best.get("id") or "").strip()
    if not rid:
        return None

    research_fields = []
    for rf in (best.get("research_fields", []) or []):
        if not isinstance(rf, dict):
            continue
        rf_id = str(rf.get("id") or "").strip()
        if not rf_id:
            continue
        research_fields.append({"id": rf_id, "label": str(rf.get("label") or "").strip() or _compact_uri_label(rf_id)})

    authors = []
    for a in (best.get("authors", []) or []):
        if not isinstance(a, dict):
            continue
        name = str(a.get("name") or "").strip()
        aid = str(a.get("id") or "").strip() or f"author:{_norm(name)}"
        if not name:
            continue
        authors.append({"id": aid, "display_name": name})

    identifiers = best.get("identifiers", {}) if isinstance(best.get("identifiers"), dict) else {}
    doi = str(identifiers.get("doi") or "").strip() or None

    return {
        "id": rid,
        "title": str(best.get("title") or "").strip(),
        "doi": doi,
        "url": f"https://orkg.org/{rid}",
        "authors": authors[:10],
        "research_fields": research_fields[:12],
    }


def _split_title(raw_title: str) -> Tuple[str, str]:
    text = str(raw_title or "").strip()
    if " - " in text:
        left, right = text.split(" - ", 1)
        return left.strip(), right.strip()
    return text, ""


def _load_book_context(book_id: str, firebase_uid: str) -> Dict[str, Any]:
    out = {"title": "", "author": "", "tags": []}
    try:
        with DatabaseManager.get_read_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT TITLE, AUTHOR FROM TOMEHUB_LIBRARY_ITEMS WHERE ITEM_ID=:p_book AND FIREBASE_UID=:p_uid",
                    {"p_book": book_id, "p_uid": firebase_uid},
                )
                row = cursor.fetchone()
                if row:
                    out["title"] = str(row[0] or "").strip()
                    out["author"] = str(row[1] or "").strip()
                else:
                    cursor.execute(
                        """
                        SELECT TITLE FROM TOMEHUB_CONTENT_V2
                        WHERE ITEM_ID=:p_book AND FIREBASE_UID=:p_uid
                        ORDER BY ID DESC FETCH FIRST 1 ROWS ONLY
                        """,
                        {"p_book": book_id, "p_uid": firebase_uid},
                    )
                    row2 = cursor.fetchone()
                    if row2:
                        parsed_title, parsed_author = _split_title(str(row2[0] or ""))
                        out["title"] = parsed_title
                        out["author"] = parsed_author

                cursor.execute(
                    """
                    SELECT DISTINCT t.TAG
                    FROM TOMEHUB_CONTENT_TAGS t
                    JOIN TOMEHUB_CONTENT_V2 c ON c.ID=t.CONTENT_ID
                    WHERE c.ITEM_ID=:p_book AND c.FIREBASE_UID=:p_uid
                    FETCH FIRST 50 ROWS ONLY
                    """,
                    {"p_book": book_id, "p_uid": firebase_uid},
                )
                out["tags"] = [str(r[0] or "").strip() for r in (cursor.fetchall() or []) if str(r[0] or "").strip()]
    except Exception as e:
        logger.warning("external_kb context load failed", extra={"book_id": book_id, "uid": firebase_uid, "error": str(e)})
    return out


def get_external_meta(book_id: str, firebase_uid: str) -> Dict[str, Any]:
    if not book_id or not firebase_uid:
        return {}
    try:
        with DatabaseManager.get_read_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                        ACADEMIC_SCOPE, WIKIDATA_QID, OPENALEX_ID, DOI,
                        EXTERNAL_JSON, LAST_SYNC_AT, SYNC_STATUS,
                        WIKIDATA_SYNC_AT, OPENALEX_SYNC_AT,
                        WIKIDATA_STATUS, OPENALEX_STATUS
                    FROM TOMEHUB_EXTERNAL_BOOK_META
                    WHERE BOOK_ID=:p_book AND FIREBASE_UID=:p_uid
                    """,
                    {"p_book": book_id, "p_uid": firebase_uid},
                )
                row = cursor.fetchone()
                if not row:
                    return {}
                external_json = _from_json(row[4])
                provider_status = external_json.get("_provider_status", {}) if isinstance(external_json.get("_provider_status", {}), dict) else {}
                provider_sync = external_json.get("_provider_sync", {}) if isinstance(external_json.get("_provider_sync", {}), dict) else {}
                return {
                    "academic_scope": bool(int(row[0] or 0)),
                    "wikidata_qid": str(row[1] or "").strip() or None,
                    "openalex_id": str(row[2] or "").strip() or None,
                    "doi": str(row[3] or "").strip() or None,
                    "external_json": external_json,
                    "last_sync_at": row[5],
                    "sync_status": str(row[6] or "").strip() or None,
                    "wikidata_sync_at": row[7],
                    "openalex_sync_at": row[8],
                    "wikidata_status": str(row[9] or "").strip() or None,
                    "openalex_status": str(row[10] or "").strip() or None,
                    "dbpedia_uri": str((external_json.get("dbpedia") or {}).get("resource_uri") or "").strip() or None,
                    "orkg_id": str((external_json.get("orkg") or {}).get("id") or "").strip() or None,
                    "dbpedia_status": str(provider_status.get("dbpedia") or "").strip() or None,
                    "orkg_status": str(provider_status.get("orkg") or "").strip() or None,
                    "provider_sync": provider_sync,
                }
    except Exception as e:
        if "ORA-00942" in str(e):
            return {}
        logger.warning("external_kb meta read failed", extra={"book_id": book_id, "uid": firebase_uid, "error": str(e)})
        return {}


def _is_stale(meta: Dict[str, Any], provider: str, ttl_hours: Optional[int] = None) -> bool:
    ttl = max(1, int(ttl_hours or getattr(settings, "EXTERNAL_KB_SYNC_TTL_HOURS", 72)))
    provider_norm = str(provider or "").strip().lower()
    if provider_norm == "wikidata":
        ts = meta.get("wikidata_sync_at")
    elif provider_norm == "openalex":
        ts = meta.get("openalex_sync_at")
    else:
        provider_sync = meta.get("provider_sync") if isinstance(meta.get("provider_sync"), dict) else {}
        raw = str(provider_sync.get(provider_norm) or "").strip()
        if not raw:
            return True
        try:
            ts = datetime.fromisoformat(raw.replace("Z", "+00:00")).replace(tzinfo=None)
        except Exception:
            return True

    if not isinstance(ts, datetime):
        return True
    return ts < datetime.utcnow() - timedelta(hours=ttl)


def normalize_external_entities(provider: str, payload: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not payload:
        return {"entities": [], "edges": [], "meta": {}}
    p = str(provider or "").strip().lower()
    entities: List[Dict[str, Any]] = []
    edges: List[Dict[str, Any]] = []
    meta: Dict[str, Any] = {}

    if p == "wikidata":
        qid = str(payload.get("qid") or "").strip()
        if qid:
            entities.append({"provider": "WIKIDATA", "external_id": qid, "entity_type": "BOOK", "label": str(payload.get("label") or qid), "payload": payload})
            for aid in payload.get("author_ids", []) or []:
                aid = str(aid or "").strip()
                if not aid:
                    continue
                entities.append({"provider": "WIKIDATA", "external_id": aid, "entity_type": "AUTHOR", "label": aid, "payload": {"id": aid}})
                edges.append({"sp": "WIKIDATA", "sid": qid, "dp": "WIKIDATA", "did": aid, "rel": "AUTHORED_BY", "weight": 0.72, "provider": "WIKIDATA"})
            for gid in payload.get("genre_ids", []) or []:
                gid = str(gid or "").strip()
                if not gid:
                    continue
                entities.append({"provider": "WIKIDATA", "external_id": gid, "entity_type": "TOPIC", "label": gid, "payload": {"id": gid}})
                edges.append({"sp": "WIKIDATA", "sid": qid, "dp": "WIKIDATA", "did": gid, "rel": "HAS_TOPIC", "weight": 0.62, "provider": "WIKIDATA"})
            meta = {"wikidata_qid": qid, "doi": payload.get("doi")}

    if p == "openalex":
        wid = str(payload.get("id") or "").strip()
        if wid:
            entities.append({"provider": "OPENALEX", "external_id": wid, "entity_type": "WORK", "label": str(payload.get("display_name") or wid), "payload": payload})
            for author in payload.get("authors", []) or []:
                aid = str(author.get("id") or "").strip()
                if not aid:
                    continue
                entities.append({"provider": "OPENALEX", "external_id": aid, "entity_type": "AUTHOR", "label": str(author.get("display_name") or aid), "payload": author})
                edges.append({"sp": "OPENALEX", "sid": wid, "dp": "OPENALEX", "did": aid, "rel": "AUTHORED_BY", "weight": 0.74, "provider": "OPENALEX"})
            for concept in payload.get("concepts", []) or []:
                cid = str(concept.get("id") or "").strip()
                if not cid:
                    continue
                score = max(0.35, min(0.95, float(concept.get("score") or 0.0)))
                entities.append({"provider": "OPENALEX", "external_id": cid, "entity_type": "TOPIC", "label": str(concept.get("display_name") or cid), "payload": concept})
                edges.append({"sp": "OPENALEX", "sid": wid, "dp": "OPENALEX", "did": cid, "rel": "HAS_TOPIC", "weight": score, "provider": "OPENALEX"})
            meta = {"openalex_id": wid, "doi": payload.get("doi")}

    if p == "dbpedia":
        rid = str(payload.get("resource_uri") or "").strip()
        if rid:
            entities.append(
                {
                    "provider": "DBPEDIA",
                    "external_id": rid,
                    "entity_type": "WORK",
                    "label": str(payload.get("label") or _compact_uri_label(rid) or rid),
                    "payload": payload,
                }
            )
            type_weight = max(0.25, min(0.75, _provider_graph_weight("DBPEDIA") * 5.2))
            for type_uri in payload.get("types", []) or []:
                tid = str(type_uri or "").strip()
                if not tid:
                    continue
                entities.append(
                    {
                        "provider": "DBPEDIA",
                        "external_id": tid,
                        "entity_type": "TOPIC",
                        "label": _compact_uri_label(tid) or tid,
                        "payload": {"uri": tid},
                    }
                )
                edges.append(
                    {
                        "sp": "DBPEDIA",
                        "sid": rid,
                        "dp": "DBPEDIA",
                        "did": tid,
                        "rel": "HAS_TYPE",
                        "weight": type_weight,
                        "provider": "DBPEDIA",
                    }
                )
            meta = {"dbpedia_uri": rid}

    if p == "orkg":
        pid = str(payload.get("id") or "").strip()
        if pid:
            entities.append(
                {
                    "provider": "ORKG",
                    "external_id": pid,
                    "entity_type": "PAPER",
                    "label": str(payload.get("title") or pid),
                    "payload": payload,
                }
            )
            topic_weight = max(0.25, min(0.85, _provider_graph_weight("ORKG") * 5.0))
            author_weight = max(0.25, min(0.75, _provider_graph_weight("ORKG") * 4.2))
            for rf in payload.get("research_fields", []) or []:
                rf_id = str((rf or {}).get("id") or "").strip()
                if not rf_id:
                    continue
                rf_label = str((rf or {}).get("label") or "").strip() or _compact_uri_label(rf_id)
                entities.append(
                    {
                        "provider": "ORKG",
                        "external_id": rf_id,
                        "entity_type": "TOPIC",
                        "label": rf_label,
                        "payload": rf,
                    }
                )
                edges.append(
                    {
                        "sp": "ORKG",
                        "sid": pid,
                        "dp": "ORKG",
                        "did": rf_id,
                        "rel": "HAS_TOPIC",
                        "weight": topic_weight,
                        "provider": "ORKG",
                    }
                )
            for author in payload.get("authors", []) or []:
                aid = str((author or {}).get("id") or "").strip()
                if not aid:
                    continue
                display = str((author or {}).get("display_name") or "").strip() or _compact_uri_label(aid)
                entities.append(
                    {
                        "provider": "ORKG",
                        "external_id": aid,
                        "entity_type": "AUTHOR",
                        "label": display,
                        "payload": author,
                    }
                )
                edges.append(
                    {
                        "sp": "ORKG",
                        "sid": pid,
                        "dp": "ORKG",
                        "did": aid,
                        "rel": "AUTHORED_BY",
                        "weight": author_weight,
                        "provider": "ORKG",
                    }
                )
            meta = {"orkg_id": pid, "doi": payload.get("doi")}

    dedup_entities = {}
    for ent in entities:
        dedup_entities[(ent["provider"], ent["external_id"])] = ent
    dedup_edges = {}
    for edge in edges:
        dedup_edges[(edge["sp"], edge["sid"], edge["dp"], edge["did"], edge["rel"], edge["provider"])] = edge
    return {"entities": list(dedup_entities.values()), "edges": list(dedup_edges.values()), "meta": meta}


def _ensure_entity(cursor: Any, ent: Dict[str, Any]) -> Optional[int]:
    provider = str(ent.get("provider") or "").strip().upper()
    ext_id = str(ent.get("external_id") or "").strip()
    if not provider or not ext_id:
        return None
    cursor.execute(
        "SELECT ID FROM TOMEHUB_EXTERNAL_ENTITIES WHERE PROVIDER=:p_provider AND EXTERNAL_ID=:p_ext FETCH FIRST 1 ROWS ONLY",
        {"p_provider": provider, "p_ext": ext_id},
    )
    row = cursor.fetchone()
    if row:
        eid = int(row[0])
        cursor.execute(
            """
            UPDATE TOMEHUB_EXTERNAL_ENTITIES
            SET ENTITY_TYPE=:p_type, LABEL=:p_label, PAYLOAD_JSON=:p_payload, UPDATED_AT=CURRENT_TIMESTAMP
            WHERE ID=:p_id
            """,
            {
                "p_type": str(ent.get("entity_type") or "UNKNOWN").strip().upper(),
                "p_label": str(ent.get("label") or "")[:512],
                "p_payload": _as_json(ent.get("payload")),
                "p_id": eid,
            },
        )
        return eid
    out_id = cursor.var(oracledb.NUMBER)
    cursor.execute(
        """
        INSERT INTO TOMEHUB_EXTERNAL_ENTITIES (PROVIDER, EXTERNAL_ID, ENTITY_TYPE, LABEL, PAYLOAD_JSON, UPDATED_AT)
        VALUES (:p_provider, :p_ext, :p_type, :p_label, :p_payload, CURRENT_TIMESTAMP)
        RETURNING ID INTO :p_out_id
        """,
        {
            "p_provider": provider,
            "p_ext": ext_id,
            "p_type": str(ent.get("entity_type") or "UNKNOWN").strip().upper(),
            "p_label": str(ent.get("label") or "")[:512],
            "p_payload": _as_json(ent.get("payload")),
            "p_out_id": out_id,
        },
    )
    inserted = out_id.getvalue()
    if isinstance(inserted, list):
        inserted = inserted[0] if inserted else None
    return int(inserted) if inserted is not None else None


def _upsert_edge(cursor: Any, edge: Dict[str, Any], entity_map: Dict[Tuple[str, str], int], book_id: str, firebase_uid: str) -> bool:
    src_id = entity_map.get((str(edge.get("sp") or "").upper(), str(edge.get("sid") or "").strip()))
    dst_id = entity_map.get((str(edge.get("dp") or "").upper(), str(edge.get("did") or "").strip()))
    if not src_id or not dst_id or src_id == dst_id:
        return False
    rel = str(edge.get("rel") or "RELATED_TO").strip().upper()
    provider = str(edge.get("provider") or "").strip().upper()
    cursor.execute(
        """
        SELECT ID FROM TOMEHUB_EXTERNAL_EDGES
        WHERE SRC_ENTITY_ID=:p_src AND DST_ENTITY_ID=:p_dst AND REL_TYPE=:p_rel
          AND PROVIDER=:p_provider AND BOOK_ID=:p_book AND FIREBASE_UID=:p_uid
        FETCH FIRST 1 ROWS ONLY
        """,
        {"p_src": src_id, "p_dst": dst_id, "p_rel": rel, "p_provider": provider, "p_book": book_id, "p_uid": firebase_uid},
    )
    row = cursor.fetchone()
    if row:
        cursor.execute(
            "UPDATE TOMEHUB_EXTERNAL_EDGES SET WEIGHT=:p_weight, UPDATED_AT=CURRENT_TIMESTAMP WHERE ID=:p_id",
            {"p_weight": float(edge.get("weight") or 0.5), "p_id": int(row[0])},
        )
        return True
    cursor.execute(
        """
        INSERT INTO TOMEHUB_EXTERNAL_EDGES
            (SRC_ENTITY_ID, DST_ENTITY_ID, REL_TYPE, WEIGHT, PROVIDER, BOOK_ID, FIREBASE_UID, UPDATED_AT)
        VALUES
            (:p_src, :p_dst, :p_rel, :p_weight, :p_provider, :p_book, :p_uid, CURRENT_TIMESTAMP)
        """,
        {
            "p_src": src_id,
            "p_dst": dst_id,
            "p_rel": rel,
            "p_weight": float(edge.get("weight") or 0.5),
            "p_provider": provider,
            "p_book": book_id,
            "p_uid": firebase_uid,
        },
    )
    return True


def upsert_external_graph(
    book_id: str,
    firebase_uid: str,
    academic_scope: bool,
    wikidata_payload: Optional[Dict[str, Any]] = None,
    openalex_payload: Optional[Dict[str, Any]] = None,
    dbpedia_payload: Optional[Dict[str, Any]] = None,
    orkg_payload: Optional[Dict[str, Any]] = None,
    provider_status: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    if not book_id or not firebase_uid:
        return {"updated": False, "reason": "missing_identity"}
    current = get_external_meta(book_id, firebase_uid)
    current_json = dict(current.get("external_json") or {})
    provider_status = provider_status or {}
    provider_status_json = dict(current_json.get("_provider_status") or {})
    provider_sync_json = dict(current_json.get("_provider_sync") or {})

    wikidata_meta = normalize_external_entities("wikidata", wikidata_payload) if wikidata_payload else None
    openalex_meta = normalize_external_entities("openalex", openalex_payload) if openalex_payload else None
    dbpedia_meta = normalize_external_entities("dbpedia", dbpedia_payload) if dbpedia_payload else None
    orkg_meta = normalize_external_entities("orkg", orkg_payload) if orkg_payload else None

    wikidata_qid = current.get("wikidata_qid")
    openalex_id = current.get("openalex_id")
    doi = current.get("doi")
    wikidata_status = current.get("wikidata_status")
    openalex_status = current.get("openalex_status")
    wikidata_sync_at = current.get("wikidata_sync_at")
    openalex_sync_at = current.get("openalex_sync_at")
    now = datetime.utcnow()

    if wikidata_meta:
        wikidata_qid = wikidata_meta.get("meta", {}).get("wikidata_qid") or wikidata_qid
        doi = wikidata_meta.get("meta", {}).get("doi") or doi
        current_json["wikidata"] = wikidata_payload
        wikidata_status = "OK"
        wikidata_sync_at = now
        provider_status_json["wikidata"] = "OK"
        provider_sync_json["wikidata"] = now.isoformat() + "Z"
    elif "wikidata_status" in provider_status:
        wikidata_status = provider_status.get("wikidata_status")
        wikidata_sync_at = now
        provider_status_json["wikidata"] = str(provider_status.get("wikidata_status") or "").strip().upper() or "UNKNOWN"
        provider_sync_json["wikidata"] = now.isoformat() + "Z"

    if openalex_meta:
        openalex_id = openalex_meta.get("meta", {}).get("openalex_id") or openalex_id
        doi = openalex_meta.get("meta", {}).get("doi") or doi
        current_json["openalex"] = openalex_payload
        openalex_status = "OK"
        openalex_sync_at = now
        provider_status_json["openalex"] = "OK"
        provider_sync_json["openalex"] = now.isoformat() + "Z"
    elif "openalex_status" in provider_status:
        openalex_status = provider_status.get("openalex_status")
        openalex_sync_at = now
        provider_status_json["openalex"] = str(provider_status.get("openalex_status") or "").strip().upper() or "UNKNOWN"
        provider_sync_json["openalex"] = now.isoformat() + "Z"

    if dbpedia_meta:
        current_json["dbpedia"] = dbpedia_payload
        provider_status_json["dbpedia"] = "OK"
        provider_sync_json["dbpedia"] = now.isoformat() + "Z"
    elif "dbpedia_status" in provider_status:
        provider_status_json["dbpedia"] = str(provider_status.get("dbpedia_status") or "").strip().upper() or "UNKNOWN"
        provider_sync_json["dbpedia"] = now.isoformat() + "Z"

    if orkg_meta:
        doi = orkg_meta.get("meta", {}).get("doi") or doi
        current_json["orkg"] = orkg_payload
        provider_status_json["orkg"] = "OK"
        provider_sync_json["orkg"] = now.isoformat() + "Z"
    elif "orkg_status" in provider_status:
        provider_status_json["orkg"] = str(provider_status.get("orkg_status") or "").strip().upper() or "UNKNOWN"
        provider_sync_json["orkg"] = now.isoformat() + "Z"

    current_json["_provider_status"] = provider_status_json
    current_json["_provider_sync"] = provider_sync_json

    sync_status = "PARTIAL"
    if wikidata_status == "OK" and (openalex_status in {"OK", "SKIPPED_NON_ACADEMIC", "SKIPPED_BY_MODE", None}):
        sync_status = "OK"
    if wikidata_status == "ERROR" and openalex_status == "ERROR":
        sync_status = "ERROR"

    entity_upserts = 0
    edge_upserts = 0
    try:
        with DatabaseManager.get_write_connection() as conn:
            with conn.cursor() as cursor:
                for norm in [wikidata_meta, openalex_meta, dbpedia_meta, orkg_meta]:
                    if not norm:
                        continue
                    entity_map: Dict[Tuple[str, str], int] = {}
                    for ent in norm.get("entities", []):
                        eid = _ensure_entity(cursor, ent)
                        if not eid:
                            continue
                        entity_map[(str(ent.get("provider") or "").strip().upper(), str(ent.get("external_id") or "").strip())] = eid
                        entity_upserts += 1
                    for edge in norm.get("edges", []):
                        if _upsert_edge(cursor, edge, entity_map, book_id, firebase_uid):
                            edge_upserts += 1

                cursor.execute(
                    """
                    MERGE INTO TOMEHUB_EXTERNAL_BOOK_META t
                    USING (SELECT :p_book AS BOOK_ID, :p_uid AS FIREBASE_UID FROM DUAL) s
                    ON (t.BOOK_ID=s.BOOK_ID AND t.FIREBASE_UID=s.FIREBASE_UID)
                    WHEN MATCHED THEN UPDATE SET
                        ACADEMIC_SCOPE=:p_scope,
                        WIKIDATA_QID=:p_w_qid,
                        OPENALEX_ID=:p_o_id,
                        DOI=:p_doi,
                        EXTERNAL_JSON=:p_json,
                        LAST_SYNC_AT=CURRENT_TIMESTAMP,
                        SYNC_STATUS=:p_sync,
                        WIKIDATA_SYNC_AT=:p_w_sync,
                        OPENALEX_SYNC_AT=:p_o_sync,
                        WIKIDATA_STATUS=:p_w_status,
                        OPENALEX_STATUS=:p_o_status,
                        UPDATED_AT=CURRENT_TIMESTAMP
                    WHEN NOT MATCHED THEN INSERT
                        (BOOK_ID, FIREBASE_UID, ACADEMIC_SCOPE, WIKIDATA_QID, OPENALEX_ID, DOI, EXTERNAL_JSON,
                         LAST_SYNC_AT, SYNC_STATUS, WIKIDATA_SYNC_AT, OPENALEX_SYNC_AT, WIKIDATA_STATUS, OPENALEX_STATUS, UPDATED_AT)
                    VALUES
                        (:p_book, :p_uid, :p_scope, :p_w_qid, :p_o_id, :p_doi, :p_json,
                         CURRENT_TIMESTAMP, :p_sync, :p_w_sync, :p_o_sync, :p_w_status, :p_o_status, CURRENT_TIMESTAMP)
                    """,
                    {
                        "p_book": book_id,
                        "p_uid": firebase_uid,
                        "p_scope": 1 if academic_scope else 0,
                        "p_w_qid": wikidata_qid,
                        "p_o_id": openalex_id,
                        "p_doi": doi,
                        "p_json": _as_json(current_json),
                        "p_sync": sync_status,
                        "p_w_sync": wikidata_sync_at,
                        "p_o_sync": openalex_sync_at,
                        "p_w_status": wikidata_status,
                        "p_o_status": openalex_status,
                    },
                )
            conn.commit()
    except Exception as e:
        logger.warning("external_kb upsert failed", extra={"book_id": book_id, "uid": firebase_uid, "error": str(e)})
        return {"updated": False, "reason": str(e)}

    return {
        "updated": True,
        "entity_upserts": entity_upserts,
        "edge_upserts": edge_upserts,
        "academic_scope": academic_scope,
        "wikidata_qid": wikidata_qid,
        "openalex_id": openalex_id,
        "dbpedia_uri": str((current_json.get("dbpedia") or {}).get("resource_uri") or "").strip() or None,
        "orkg_id": str((current_json.get("orkg") or {}).get("id") or "").strip() or None,
        "sync_status": sync_status,
    }


def enrich_book_with_wikidata(book_id: str, firebase_uid: str, title: Optional[str], author: Optional[str], tags: Optional[List[str]]) -> Dict[str, Any]:
    if not getattr(settings, "EXTERNAL_KB_ENABLED", False):
        return {"status": "disabled"}
    context = _load_book_context(book_id, firebase_uid) if not title else {"title": title, "author": author, "tags": tags}
    scope = compute_academic_scope(_norm_tags(tags if tags is not None else context.get("tags")))
    payload = _fetch_wikidata(str(context.get("title") or title or ""), str(context.get("author") or author or ""))
    if not payload:
        upsert_external_graph(book_id, firebase_uid, scope, provider_status={"wikidata_status": "NO_MATCH"})
        return {"status": "no_match", "academic_scope": scope}
    out = upsert_external_graph(book_id, firebase_uid, scope, wikidata_payload=payload)
    out["status"] = "ok" if out.get("updated") else "failed"
    return out


def enrich_book_with_openalex(
    book_id: str,
    firebase_uid: str,
    title: Optional[str],
    author: Optional[str],
    tags: Optional[List[str]],
    mode_hint: Optional[str],
) -> Dict[str, Any]:
    if not getattr(settings, "EXTERNAL_KB_ENABLED", False):
        return {"status": "disabled"}
    scope = compute_academic_scope(_norm_tags(tags))
    if not scope:
        upsert_external_graph(book_id, firebase_uid, False, provider_status={"openalex_status": "SKIPPED_NON_ACADEMIC"})
        return {"status": "skipped_non_academic", "academic_scope": False}
    if getattr(settings, "EXTERNAL_KB_OPENALEX_EXPLORER_ONLY", True) and str(mode_hint or "").upper() != "EXPLORER":
        upsert_external_graph(book_id, firebase_uid, True, provider_status={"openalex_status": "SKIPPED_BY_MODE"})
        return {"status": "skipped_by_mode", "academic_scope": True}
    context = _load_book_context(book_id, firebase_uid) if not title else {"title": title, "author": author}
    payload = _fetch_openalex(str(context.get("title") or title or ""), str(context.get("author") or author or ""))
    if not payload:
        upsert_external_graph(book_id, firebase_uid, True, provider_status={"openalex_status": "NO_MATCH"})
        return {"status": "no_match", "academic_scope": True}
    out = upsert_external_graph(book_id, firebase_uid, True, openalex_payload=payload)
    out["status"] = "ok" if out.get("updated") else "failed"
    return out


def _run_external_enrichment(book_id: str, firebase_uid: str, title: Optional[str], author: Optional[str], tags: Optional[List[str]], mode_hint: str, force: bool) -> None:
    context = {"title": title or "", "author": author or "", "tags": _norm_tags(tags)}
    if not context["title"] or not context["tags"]:
        loaded = _load_book_context(book_id, firebase_uid)
        context["title"] = context["title"] or loaded.get("title") or ""
        context["author"] = context["author"] or loaded.get("author") or ""
        if not context["tags"]:
            context["tags"] = _norm_tags(loaded.get("tags"))
    meta = get_external_meta(book_id, firebase_uid)
    if force or _is_stale(meta, "wikidata"):
        enrich_book_with_wikidata(book_id, firebase_uid, context["title"], context["author"], context["tags"])
    if compute_academic_scope(context["tags"]):
        if force or _is_stale(meta, "openalex"):
            enrich_book_with_openalex(book_id, firebase_uid, context["title"], context["author"], context["tags"], mode_hint=mode_hint)
    else:
        upsert_external_graph(book_id, firebase_uid, False, provider_status={"openalex_status": "SKIPPED_NON_ACADEMIC"})

    if bool(getattr(settings, "EXTERNAL_KB_DBPEDIA_ENABLED", False)):
        if bool(getattr(settings, "EXTERNAL_KB_DBPEDIA_EXPLORER_ONLY", True)) and str(mode_hint or "").upper() != "EXPLORER":
            upsert_external_graph(book_id, firebase_uid, compute_academic_scope(context["tags"]), provider_status={"dbpedia_status": "SKIPPED_BY_MODE"})
        elif force or _is_stale(meta, "dbpedia"):
            dbpedia_payload = _fetch_dbpedia(context["title"], context["author"])
            if dbpedia_payload:
                upsert_external_graph(
                    book_id,
                    firebase_uid,
                    compute_academic_scope(context["tags"]),
                    dbpedia_payload=dbpedia_payload,
                )
            else:
                upsert_external_graph(book_id, firebase_uid, compute_academic_scope(context["tags"]), provider_status={"dbpedia_status": "NO_MATCH"})

    if bool(getattr(settings, "EXTERNAL_KB_ORKG_ENABLED", False)):
        if not compute_academic_scope(context["tags"]):
            upsert_external_graph(book_id, firebase_uid, False, provider_status={"orkg_status": "SKIPPED_NON_ACADEMIC"})
        elif bool(getattr(settings, "EXTERNAL_KB_ORKG_EXPLORER_ONLY", True)) and str(mode_hint or "").upper() != "EXPLORER":
            upsert_external_graph(book_id, firebase_uid, True, provider_status={"orkg_status": "SKIPPED_BY_MODE"})
        elif force or _is_stale(meta, "orkg"):
            orkg_payload = _fetch_orkg(context["title"], context["author"])
            if orkg_payload:
                upsert_external_graph(book_id, firebase_uid, True, orkg_payload=orkg_payload)
            else:
                upsert_external_graph(book_id, firebase_uid, True, provider_status={"orkg_status": "NO_MATCH"})


def maybe_trigger_external_enrichment_async(
    book_id: Optional[str],
    firebase_uid: Optional[str],
    title: Optional[str] = None,
    author: Optional[str] = None,
    tags: Optional[List[str]] = None,
    mode_hint: str = "INGEST",
    force: bool = False,
) -> bool:
    if not getattr(settings, "EXTERNAL_KB_ENABLED", False):
        return False
    if not book_id or not firebase_uid:
        return False
    key = (str(firebase_uid), str(book_id), str(mode_hint or "INGEST").upper())
    with _ACTIVE_LOCK:
        if key in _ACTIVE_KEYS:
            return False
        _ACTIVE_KEYS.add(key)

    def _worker() -> None:
        try:
            _run_external_enrichment(str(book_id), str(firebase_uid), title, author, tags, str(mode_hint or "INGEST").upper(), bool(force))
        except Exception as e:
            logger.warning("external_kb worker failed", extra={"book_id": book_id, "uid": firebase_uid, "error": str(e)})
        finally:
            with _ACTIVE_LOCK:
                _ACTIVE_KEYS.discard(key)

    threading.Thread(target=_worker, daemon=True).start()
    return True


def maybe_refresh_external_for_explorer_async(book_id: Optional[str], firebase_uid: Optional[str], title: Optional[str] = None, author: Optional[str] = None, tags: Optional[List[str]] = None) -> bool:
    force_refresh = False
    if book_id and firebase_uid:
        meta = get_external_meta(book_id, firebase_uid)
        if not meta:
            force_refresh = True
        else:
            if not meta.get("wikidata_qid"):
                force_refresh = True
            if bool(meta.get("academic_scope")) and not meta.get("openalex_id"):
                force_refresh = True
            if bool(getattr(settings, "EXTERNAL_KB_DBPEDIA_ENABLED", False)) and not meta.get("dbpedia_uri"):
                force_refresh = True
            if bool(getattr(settings, "EXTERNAL_KB_ORKG_ENABLED", False)) and bool(meta.get("academic_scope")) and not meta.get("orkg_id"):
                force_refresh = True
    return maybe_trigger_external_enrichment_async(
        book_id=book_id,
        firebase_uid=firebase_uid,
        title=title,
        author=author,
        tags=tags,
        mode_hint="EXPLORER",
        force=force_refresh,
    )


def get_external_graph_candidates(book_id: str, firebase_uid: str, question: str, limit: int = 5, min_confidence: Optional[float] = None) -> List[Dict[str, Any]]:
    if not getattr(settings, "EXTERNAL_KB_ENABLED", False):
        return []
    if not book_id or not firebase_uid:
        return []
    hard_limit = max(1, min(int(limit or 5), 10))
    floor = float(min_confidence if min_confidence is not None else getattr(settings, "EXTERNAL_KB_MIN_CONFIDENCE", 0.45))
    qtokens = {tok for tok in re.findall(r"[^\W_]+", _norm(question), flags=re.UNICODE) if len(tok) >= 3}
    try:
        with DatabaseManager.get_read_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT e.REL_TYPE, e.WEIGHT, e.PROVIDER, src.LABEL, dst.LABEL
                    FROM TOMEHUB_EXTERNAL_EDGES e
                    JOIN TOMEHUB_EXTERNAL_ENTITIES src ON src.ID=e.SRC_ENTITY_ID
                    JOIN TOMEHUB_EXTERNAL_ENTITIES dst ON dst.ID=e.DST_ENTITY_ID
                    WHERE e.BOOK_ID=:p_book AND e.FIREBASE_UID=:p_uid
                    ORDER BY e.UPDATED_AT DESC
                    FETCH FIRST :p_limit ROWS ONLY
                    """,
                    {"p_book": book_id, "p_uid": firebase_uid, "p_limit": hard_limit * 8},
                )
                rows = cursor.fetchall() or []
    except Exception as e:
        if "ORA-00942" in str(e):
            return []
        logger.warning("external_kb candidate read failed", extra={"book_id": book_id, "uid": firebase_uid, "error": str(e)})
        return []
    out: List[Dict[str, Any]] = []
    for rel_type, weight, provider, src_label, dst_label in rows:
        provider_name = str(provider or "EXTERNAL").upper()
        src = str(src_label or "").strip()
        dst = str(dst_label or "").strip()
        text = f"{src} {dst}".lower()
        match = sum(1 for tok in qtokens if tok in text)
        score = float(weight or 0.0) + min(0.35, 0.08 * match)
        # Secondary providers should remain supportive, not dominant.
        if provider_name in {"DBPEDIA", "ORKG"}:
            score *= 0.92
        if score < floor:
            continue
        provider_weight = max(0.03, min(0.30, _provider_graph_weight(provider_name)))
        out.append(
            {
                "title": f"External KB ({provider_name})",
                "content_chunk": f"{src} {str(rel_type or 'RELATED_TO').replace('_', ' ').lower()} {dst}".strip(),
                "page_number": 0,
                "source_type": "EXTERNAL_KB",
                "score": score,
                "external_weight": provider_weight,
                "provider": provider_name,
            }
        )
    out.sort(key=lambda x: float(x.get("score") or 0.0), reverse=True)
    return out[:hard_limit]


def _count_books(scope_uid: Optional[str]) -> int:
    with DatabaseManager.get_read_connection() as conn:
        with conn.cursor() as cursor:
            if scope_uid:
                cursor.execute("SELECT COUNT(*) FROM TOMEHUB_LIBRARY_ITEMS WHERE FIREBASE_UID=:p_uid", {"p_uid": scope_uid})
            else:
                cursor.execute("SELECT COUNT(*) FROM TOMEHUB_LIBRARY_ITEMS")
            row = cursor.fetchone()
            return int(row[0] or 0) if row else 0


def _backfill_worker(scope_uid: Optional[str]) -> None:
    try:
        with _BACKFILL_LOCK:
            _BACKFILL_STATUS["total"] = _count_books(scope_uid)
        batch = max(1, int(getattr(settings, "EXTERNAL_KB_BACKFILL_BATCH_SIZE", 50)))
        with DatabaseManager.get_read_connection() as conn:
            with conn.cursor() as cursor:
                if scope_uid:
                    cursor.execute("SELECT ITEM_ID, FIREBASE_UID, TITLE, AUTHOR FROM TOMEHUB_LIBRARY_ITEMS WHERE FIREBASE_UID=:p_uid ORDER BY ITEM_ID", {"p_uid": scope_uid})
                else:
                    cursor.execute("SELECT ITEM_ID, FIREBASE_UID, TITLE, AUTHOR FROM TOMEHUB_LIBRARY_ITEMS ORDER BY FIREBASE_UID, ITEM_ID")
                while True:
                    rows = cursor.fetchmany(batch)
                    if not rows:
                        break
                    for row in rows:
                        _run_external_enrichment(str(row[0] or ""), str(row[1] or ""), str(row[2] or ""), str(row[3] or ""), None, "BACKFILL", False)
                        with _BACKFILL_LOCK:
                            _BACKFILL_STATUS["processed"] = int(_BACKFILL_STATUS.get("processed", 0)) + 1
    except Exception as e:
        with _BACKFILL_LOCK:
            _BACKFILL_STATUS["last_error"] = str(e)
    finally:
        with _BACKFILL_LOCK:
            _BACKFILL_STATUS["running"] = False
            _BACKFILL_STATUS["finished_at"] = datetime.utcnow()


def start_external_kb_backfill_async(scope_uid: Optional[str] = None) -> Dict[str, Any]:
    if not getattr(settings, "EXTERNAL_KB_ENABLED", False):
        return {"running": False, "reason": "disabled"}
    with _BACKFILL_LOCK:
        if _BACKFILL_STATUS.get("running"):
            return get_external_kb_backfill_status()
        _BACKFILL_STATUS["running"] = True
        _BACKFILL_STATUS["started_at"] = datetime.utcnow()
        _BACKFILL_STATUS["finished_at"] = None
        _BACKFILL_STATUS["processed"] = 0
        _BACKFILL_STATUS["total"] = 0
        _BACKFILL_STATUS["last_error"] = None
        _BACKFILL_STATUS["scope_uid"] = scope_uid
    threading.Thread(target=_backfill_worker, args=(scope_uid,), daemon=True).start()
    return get_external_kb_backfill_status()


def get_external_kb_backfill_status() -> Dict[str, Any]:
    with _BACKFILL_LOCK:
        out = dict(_BACKFILL_STATUS)
    for key in ("started_at", "finished_at"):
        if isinstance(out.get(key), datetime):
            out[key] = out[key].isoformat()
    return out
