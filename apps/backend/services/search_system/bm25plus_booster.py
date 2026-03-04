from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

from utils.text_utils import deaccent_text

try:
    from rank_bm25 import BM25Plus
except Exception:  # pragma: no cover - graceful fallback
    BM25Plus = None

try:
    from rank_bm25 import BM25Okapi
except Exception:  # pragma: no cover - graceful fallback
    BM25Okapi = None


_STOP = {
    "ve",
    "veya",
    "ile",
    "ama",
    "fakat",
    "ancak",
    "lakin",
    "ki",
    "de",
    "da",
    "gibi",
    "icin",
    "gore",
    "kadar",
    "hem",
    "bu",
    "su",
    "o",
    "bir",
    "mi",
    "mu",
}


def _norm(text: str) -> str:
    value = deaccent_text(str(text or "")).lower()
    value = re.sub(r"[^a-z0-9\s]+", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def _tokenize(text: str) -> List[str]:
    toks = re.findall(r"[a-z0-9]+", _norm(text))
    return [t for t in toks if len(t) >= 2 and t not in _STOP]


def _safe_base_score(item: Dict[str, Any]) -> float:
    raw = item.get("rrf_score", item.get("score", 0.0))
    try:
        value = float(raw or 0.0)
    except Exception:
        value = 0.0

    # rrf_score is already tiny positive, keep as is; score is in 0..100.
    if "rrf_score" in item:
        return max(0.0, value)
    return max(0.0, min(1.0, value / 100.0))


def _normalize_values(values: List[float]) -> List[float]:
    if not values:
        return []
    vmin = min(values)
    vmax = max(values)
    if vmax <= vmin:
        return [0.0 for _ in values]
    return [(v - vmin) / (vmax - vmin) for v in values]


def bm25plus_blend_rank(
    query: str,
    candidates: List[Dict[str, Any]],
    *,
    candidate_limit: int,
    blend_weight: float,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    if not candidates:
        return [], {"model": "bm25plus", "candidate_count": 0}

    head_count = max(1, min(len(candidates), int(candidate_limit or 1)))
    head = [dict(item) for item in candidates[:head_count]]
    tail = [dict(item) for item in candidates[head_count:]]

    q_tokens = _tokenize(query)
    if not q_tokens:
        return candidates, {
            "model": "bm25plus",
            "candidate_count": len(candidates),
            "head_count": head_count,
            "query_tokens": 0,
            "status": "skipped_empty_query_tokens",
        }

    corpus = []
    for row in head:
        # Keep text bounded for latency.
        snippet = str(row.get("content_chunk", "") or "")[:2500]
        title = str(row.get("title", "") or "")
        corpus.append(_tokenize(f"{title} {snippet}"))

    if not any(corpus):
        return candidates, {
            "model": "bm25plus",
            "candidate_count": len(candidates),
            "head_count": head_count,
            "query_tokens": len(q_tokens),
            "status": "skipped_empty_corpus_tokens",
        }

    ranker = None
    if BM25Plus is not None:
        ranker = BM25Plus(corpus)
        model_name = "bm25plus"
    elif BM25Okapi is not None:
        ranker = BM25Okapi(corpus)
        model_name = "bm25okapi_fallback"
    else:
        return candidates, {
            "model": "none",
            "candidate_count": len(candidates),
            "head_count": head_count,
            "query_tokens": len(q_tokens),
            "status": "skipped_ranker_unavailable",
        }

    bm25_scores = [float(x) for x in ranker.get_scores(q_tokens)]
    norm_bm25 = _normalize_values(bm25_scores)
    weight = max(0.0, min(1.0, float(blend_weight or 0.0)))

    merged = []
    for idx, row in enumerate(head):
        base = _safe_base_score(row)
        lex = norm_bm25[idx] if idx < len(norm_bm25) else 0.0
        blended = ((1.0 - weight) * base) + (weight * lex)
        row["bm25plus_score"] = round(lex * 100.0, 4)
        row["blended_rank_score"] = round(blended, 6)
        merged.append((blended, idx, row))

    merged.sort(key=lambda x: (x[0], -x[1]), reverse=True)
    ordered_head = [row for _, _, row in merged]
    ordered = ordered_head + tail

    return ordered, {
        "model": model_name,
        "candidate_count": len(candidates),
        "head_count": head_count,
        "query_tokens": len(q_tokens),
        "blend_weight": weight,
        "status": "ok",
    }
