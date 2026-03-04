from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

from utils.text_utils import deaccent_text


_STOP_TOKENS = {
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

_MATCH_PRIOR = {
    "exact": 0.24,
    "lemma": 0.12,
    "semantic": 0.04,
}

_SOURCE_PRIOR = {
    "HIGHLIGHT": 0.16,
    "INSIGHT": 0.14,
    "PERSONAL_NOTE": 0.08,
    "BOOK": 0.03,
    "ARTICLE": 0.03,
    "WEBSITE": 0.02,
    "PDF": -0.02,
    "EPUB": -0.02,
    "PDF_CHUNK": -0.03,
    "BOOK_CHUNK": -0.03,
}

_LOW_SIGNAL_PATTERNS = (
    "icindekiler",
    "table of contents",
    "index",
    "copyright",
    "isbn",
)


def _norm_text(text: str) -> str:
    value = deaccent_text(str(text or "")).lower()
    value = re.sub(r"[^a-z0-9\s]+", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def _tokens(text: str) -> List[str]:
    return [
        tok
        for tok in re.findall(r"[a-z0-9]+", _norm_text(text))
        if len(tok) >= 2 and tok not in _STOP_TOKENS
    ]


def _match_family(match_type: str) -> str:
    mt = str(match_type or "").strip().lower()
    if "exact" in mt:
        return "exact"
    if "lemma" in mt:
        return "lemma"
    return "semantic"


def _quality_adjustment(text: str) -> float:
    content = str(text or "").strip()
    if not content:
        return -0.30
    lowered = _norm_text(content)
    if len(content) < 40:
        return -0.10
    penalty = 0.0
    for marker in _LOW_SIGNAL_PATTERNS:
        if marker in lowered:
            penalty -= 0.05
    density_bonus = min(0.06, len(content) / 7000.0)
    return penalty + density_bonus


def rerank_candidates_fast(
    query: str,
    candidates: List[Dict[str, Any]],
    *,
    top_n: int,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Low-latency deterministic reranker.
    Goal: improve ranking stability without extra LLM/network calls.
    """
    query_tokens = _tokens(query)
    query_norm = _norm_text(query)
    unique_q = set(query_tokens)

    if not candidates:
        return [], {"model": "fast_heuristic_v1", "candidate_count": 0}

    scored: List[Tuple[float, int, Dict[str, Any]]] = []
    for idx, row in enumerate(candidates):
        item = dict(row)
        text = str(item.get("content_chunk", "") or "")
        title = str(item.get("title", "") or "")
        doc_text_norm = _norm_text(f"{title} {text}")
        doc_tokens = set(_tokens(doc_text_norm))

        try:
            base_score = float(item.get("score", 0.0) or 0.0) / 100.0
        except Exception:
            base_score = 0.0
        base_score = max(0.0, min(1.0, base_score))

        if unique_q:
            overlap = len(unique_q.intersection(doc_tokens))
            coverage = overlap / float(max(1, len(unique_q)))
        else:
            coverage = 0.0

        term_tf = 0
        if query_tokens:
            for token in unique_q:
                if token in doc_text_norm:
                    term_tf += 1
        tf_score = min(1.0, term_tf / float(max(1, len(unique_q))))

        source_type = str(item.get("source_type", "") or "").strip().upper()
        source_prior = _SOURCE_PRIOR.get(source_type, 0.0)
        match_prior = _MATCH_PRIOR.get(_match_family(item.get("match_type", "")), 0.0)
        title_hit = 0.08 if (query_norm and query_norm in _norm_text(title)) else 0.0
        phrase_hit = 0.10 if (query_norm and query_norm in doc_text_norm) else 0.0
        quality = _quality_adjustment(text)

        final = (
            (base_score * 0.48)
            + (coverage * 0.24)
            + (tf_score * 0.10)
            + source_prior
            + match_prior
            + title_hit
            + phrase_hit
            + quality
        )

        item["rerank_score"] = round(final * 100.0, 4)
        scored.append((final, idx, item))

    scored.sort(key=lambda x: (x[0], -x[1]), reverse=True)
    ordered = [row for _, _, row in scored]

    diagnostics = {
        "model": "fast_heuristic_v1",
        "candidate_count": len(candidates),
        "query_token_count": len(query_tokens),
        "top_n_requested": max(1, int(top_n or 1)),
    }
    return ordered, diagnostics
