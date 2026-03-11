from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

from utils.text_utils import deaccent_text


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


def _tokens(text: str) -> set[str]:
    toks = re.findall(r"[a-z0-9]+", _norm(text))
    return {t for t in toks if len(t) >= 2 and t not in _STOP}


def _sim_jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a.intersection(b))
    if inter <= 0:
        return 0.0
    union = len(a.union(b))
    if union <= 0:
        return 0.0
    return inter / float(union)


def _base_relevance(item: Dict[str, Any]) -> float:
    for key in ("rerank_score", "blended_rank_score", "score", "rrf_score"):
        if key not in item:
            continue
        try:
            value = float(item.get(key) or 0.0)
        except Exception:
            continue
        if key in {"rerank_score", "score"}:
            return max(0.0, min(1.0, value / 100.0))
        return max(0.0, value)
    return 0.0


def _normalize(values: List[float]) -> List[float]:
    if not values:
        return []
    vmin = min(values)
    vmax = max(values)
    if vmax <= vmin:
        return [0.0 for _ in values]
    return [(v - vmin) / (vmax - vmin) for v in values]


def apply_mmr_diversity(
    query: str,
    candidates: List[Dict[str, Any]],
    *,
    candidate_limit: int,
    top_n: int,
    lambda_weight: float,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Reorder top head with MMR to reduce near-duplicate chunks.
    Does not remove rows; only reorders top portion.
    """
    if not candidates:
        return [], {"model": "mmr_jaccard_v1", "candidate_count": 0, "status": "empty"}

    head_count = max(1, min(len(candidates), int(candidate_limit or 1)))
    head = [dict(item) for item in candidates[:head_count]]
    tail = [dict(item) for item in candidates[head_count:]]
    mmr_top_n = max(1, min(head_count, int(top_n or head_count)))
    lam = max(0.0, min(1.0, float(lambda_weight or 0.0)))

    query_toks = _tokens(query)
    row_toks: List[set[str]] = []
    for row in head:
        title = str(row.get("title", "") or "")
        text = str(row.get("content_chunk", "") or "")[:2500]
        row_toks.append(_tokens(f"{title} {text}"))

    rel_raw = []
    for idx, row in enumerate(head):
        rel = _base_relevance(row)
        if query_toks:
            lex_cov = _sim_jaccard(query_toks, row_toks[idx])
            rel = (0.75 * rel) + (0.25 * lex_cov)
        rel_raw.append(rel)
    rel = _normalize(rel_raw)

    selected: List[int] = []
    remaining = set(range(len(head)))
    while remaining and len(selected) < mmr_top_n:
        best_idx = None
        best_score = float("-inf")
        for idx in remaining:
            novelty_penalty = 0.0
            if selected:
                novelty_penalty = max(_sim_jaccard(row_toks[idx], row_toks[s]) for s in selected)
            score = (lam * rel[idx]) - ((1.0 - lam) * novelty_penalty)
            if score > best_score:
                best_score = score
                best_idx = idx
        if best_idx is None:
            break
        selected.append(best_idx)
        remaining.remove(best_idx)

    selected_set = set(selected)
    ordered_head = [head[i] for i in selected]
    for i in range(len(head)):
        if i not in selected_set:
            ordered_head.append(head[i])
    ordered = ordered_head + tail

    return ordered, {
        "model": "mmr_jaccard_v1",
        "candidate_count": len(candidates),
        "head_count": head_count,
        "top_n": mmr_top_n,
        "lambda_weight": lam,
        "status": "ok",
    }
