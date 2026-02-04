# -*- coding: utf-8 -*-
"""
Layer 4: Insight Cards Service
Generates pre-flow insight cards with caching.
"""

import logging
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any

import numpy as np

from infrastructure.db_manager import DatabaseManager, safe_read_clob
from services.cache_service import get_cache, generate_cache_key
from models.flow_models import InsightCard
from utils.text_utils import normalize_text

logger = logging.getLogger(__name__)

INSIGHTS_TTL_SECONDS = 60 * 60 * 24  # 24h
CONCEPT_OVERLAP_TTL_SECONDS = 60 * 60 * 24 * 7  # 7 days
CONCEPT_OVERLAP_SIM_THRESHOLD = 0.70
UNLABELED_CLUSTER_SIM_THRESHOLD = 0.80


def _to_list(vec_data) -> Optional[List[float]]:
    """Convert Oracle vector data to list of floats."""
    if vec_data is None:
        return None
    if isinstance(vec_data, (list, tuple)):
        return [float(x) for x in vec_data]
    if hasattr(vec_data, "tolist"):
        return [float(x) for x in vec_data.tolist()]
    if hasattr(vec_data, "read"):
        try:
            content = vec_data.read()
            if isinstance(content, str):
                import json
                data = json.loads(content)
                return [float(x) for x in data] if isinstance(data, list) else None
            if isinstance(content, bytes):
                import struct
                return list(struct.unpack(f"{len(content)//4}f", content))
        except Exception as e:
            logger.warning(f"Vector conversion error: {e}")
            return None
    return None


def _cosine_similarity(vec_a: List[float], vec_b: List[float]) -> float:
    a = np.array(vec_a)
    b = np.array(vec_b)
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


def get_flow_insights(firebase_uid: str, force_refresh: bool = False) -> Dict[str, Any]:
    cache = get_cache()
    cache_key = generate_cache_key("flow_insights", "insights", firebase_uid, limit=10, version="v1")

    if cache and not force_refresh:
        cached = cache.get(cache_key)
        if cached:
            return {
                "cards": cached.get("cards", []),
                "generated_at": cached.get("generated_at"),
                "cache_hit": True
            }

    cards: List[InsightCard] = []

    # Concept overlap (high prestige, weekly)
    concept_card = _build_concept_overlap(firebase_uid, cache)
    if concept_card:
        cards.append(concept_card)

    # Forgotten knowledge
    forgotten_card = _build_forgotten_knowledge(firebase_uid)
    if forgotten_card:
        cards.append(forgotten_card)

    # Category stats (up to 2 cards)
    cards.extend(_build_category_stats(firebase_uid))

    # Unlabeled cluster
    unlabeled = _build_unlabeled_cluster(firebase_uid)
    if unlabeled:
        cards.append(unlabeled)

    # Trim to 10 max
    cards = cards[:10]

    payload = {
        "cards": [c.model_dump() if hasattr(c, "model_dump") else c.dict() for c in cards],
        "generated_at": datetime.now().isoformat(),
        "cache_hit": False
    }

    if cache:
        cache.set(cache_key, payload, ttl=INSIGHTS_TTL_SECONDS)

    return payload


def _concept_overlap_allowed(cache, firebase_uid: str) -> bool:
    if not cache:
        return True
    key = f"flow:insights:concept_overlap:last:{firebase_uid}"
    last = cache.get(key)
    if not last:
        return True
    try:
        last_dt = datetime.fromisoformat(last)
        return (datetime.now() - last_dt) > timedelta(days=7)
    except Exception:
        return True


def _mark_concept_overlap_shown(cache, firebase_uid: str):
    if not cache:
        return
    key = f"flow:insights:concept_overlap:last:{firebase_uid}"
    cache.set(key, datetime.now().isoformat(), ttl=CONCEPT_OVERLAP_TTL_SECONDS)


def _build_concept_overlap(firebase_uid: str, cache) -> Optional[InsightCard]:
    if not _concept_overlap_allowed(cache, firebase_uid):
        return None

    try:
        with DatabaseManager.get_read_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT c.id, c.name,
                           COUNT(DISTINCT t.book_id) AS book_count,
                           COUNT(DISTINCT cc.category_norm) AS category_count
                    FROM TOMEHUB_CONCEPTS c
                    JOIN TOMEHUB_CONCEPT_CHUNKS link ON c.id = link.concept_id
                    JOIN TOMEHUB_CONTENT t ON link.content_id = t.id
                    LEFT JOIN TOMEHUB_CONTENT_CATEGORIES cc ON cc.content_id = t.id
                    WHERE t.firebase_uid = :p_uid
                      AND t.book_id IS NOT NULL
                    GROUP BY c.id, c.name
                    HAVING COUNT(DISTINCT t.book_id) >= 3
                       AND COUNT(DISTINCT cc.category_norm) >= 2
                    ORDER BY book_count DESC, category_count DESC
                    FETCH FIRST 15 ROWS ONLY
                    """,
                    {"p_uid": firebase_uid},
                )
                candidates = cursor.fetchall()

                for concept_id, concept_name, book_count, category_count in candidates:
                    cursor.execute(
                        """
                        SELECT t.vec_embedding
                        FROM TOMEHUB_CONTENT t
                        JOIN TOMEHUB_CONCEPT_CHUNKS link ON link.content_id = t.id
                        WHERE link.concept_id = :p_cid
                          AND t.firebase_uid = :p_uid
                          AND t.vec_embedding IS NOT NULL
                        FETCH FIRST 15 ROWS ONLY
                        """,
                        {"p_cid": concept_id, "p_uid": firebase_uid},
                    )
                    vec_rows = cursor.fetchall()
                    vectors = []
                    for (vec_data,) in vec_rows:
                        vec = _to_list(vec_data)
                        if vec:
                            vectors.append(vec)

                    if len(vectors) < 3:
                        continue

                    centroid = np.mean(np.array(vectors), axis=0)
                    avg_sim = float(np.mean([_cosine_similarity(centroid, v) for v in vectors]))

                    if avg_sim >= CONCEPT_OVERLAP_SIM_THRESHOLD:
                        title = f'Bu hafta "{concept_name}" kavramı {book_count} kitapta örtüşüyor'
                        body = f"En az {category_count} farklı kategoride anlam örtüşmesi tespit edildi."
                        card = InsightCard(
                            id=f"concept-{concept_id}",
                            type="CONCEPT_OVERLAP",
                            title=title,
                            body=body,
                            meta={
                                "concept_id": str(concept_id),
                                "concept": concept_name,
                                "book_count": int(book_count),
                                "category_count": int(category_count),
                                "avg_cosine": round(avg_sim, 3),
                                "window_days": 7,
                            },
                        )
                        _mark_concept_overlap_shown(cache, firebase_uid)
                        return card
    except Exception as e:
        logger.error(f"Concept overlap insight failed: {e}")

    return None


def _build_forgotten_knowledge(firebase_uid: str) -> Optional[InsightCard]:
    try:
        with DatabaseManager.get_read_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT t.id, t.title, t.content_chunk
                    FROM TOMEHUB_CONTENT t
                    WHERE t.firebase_uid = :p_uid
                      AND t.source_type IN ('HIGHLIGHT','INSIGHT','NOTES','PERSONAL_NOTE','PDF_CHUNK')
                      AND t.id NOT IN (
                        SELECT chunk_id
                        FROM TOMEHUB_FLOW_SEEN
                        WHERE firebase_uid = :p_uid
                          AND seen_at >= (SYSDATE - 30)
                      )
                    ORDER BY t.created_at ASC
                    FETCH FIRST 1 ROW ONLY
                    """,
                    {"p_uid": firebase_uid},
                )
                row = cursor.fetchone()
                if row:
                    content_id, title, content_chunk = row
                    snippet = safe_read_clob(content_chunk or "")[:220]
                    return InsightCard(
                        id=f"forgotten-{content_id}",
                        type="FORGOTTEN",
                        title="Unutulmak üzere olan bilgi",
                        body=f"{title}: {snippet}",
                        meta={"content_id": str(content_id), "title": title, "window_days": 30},
                    )
    except Exception as e:
        logger.error(f"Forgotten insight failed: {e}")

    return None


def _build_category_stats(firebase_uid: str) -> List[InsightCard]:
    cards: List[InsightCard] = []
    try:
        with DatabaseManager.get_read_connection() as conn:
            with conn.cursor() as cursor:
                # Most text by count
                cursor.execute(
                    """
                    SELECT cc.category, COUNT(*) as cnt
                    FROM TOMEHUB_CONTENT_CATEGORIES cc
                    JOIN TOMEHUB_CONTENT t ON t.id = cc.content_id
                    WHERE t.firebase_uid = :p_uid
                    GROUP BY cc.category
                    ORDER BY cnt DESC
                    FETCH FIRST 1 ROW ONLY
                    """,
                    {"p_uid": firebase_uid},
                )
                row = cursor.fetchone()
                if row:
                    category, cnt = row
                    cards.append(
                        InsightCard(
                            id=f"cat-most-{normalize_text(category)}",
                            type="CATEGORY_STATS",
                            title="En çok metin barındıran kategori",
                            body=f"{category} ({int(cnt)} parça)",
                            meta={"category": category, "count": int(cnt)},
                        )
                    )

                # Least text by count
                cursor.execute(
                    """
                    SELECT cc.category, COUNT(*) as cnt
                    FROM TOMEHUB_CONTENT_CATEGORIES cc
                    JOIN TOMEHUB_CONTENT t ON t.id = cc.content_id
                    WHERE t.firebase_uid = :p_uid
                    GROUP BY cc.category
                    ORDER BY cnt ASC
                    FETCH FIRST 1 ROW ONLY
                    """,
                    {"p_uid": firebase_uid},
                )
                row = cursor.fetchone()
                if row:
                    category, cnt = row
                    cards.append(
                        InsightCard(
                            id=f"cat-least-{normalize_text(category)}",
                            type="CATEGORY_STATS",
                            title="En az metin barındıran kategori",
                            body=f"{category} ({int(cnt)} parça)",
                            meta={"category": category, "count": int(cnt)},
                        )
                    )

                # Growth in last 30 days vs previous 30 days
                cursor.execute(
                    """
                    WITH recent AS (
                        SELECT cc.category_norm, cc.category, COUNT(*) cnt
                        FROM TOMEHUB_CONTENT_CATEGORIES cc
                        JOIN TOMEHUB_CONTENT t ON t.id = cc.content_id
                        WHERE t.firebase_uid = :p_uid
                          AND t.created_at >= (SYSDATE - 30)
                        GROUP BY cc.category_norm, cc.category
                    ),
                    prev AS (
                        SELECT cc.category_norm, COUNT(*) cnt
                        FROM TOMEHUB_CONTENT_CATEGORIES cc
                        JOIN TOMEHUB_CONTENT t ON t.id = cc.content_id
                        WHERE t.firebase_uid = :p_uid
                          AND t.created_at < (SYSDATE - 30)
                          AND t.created_at >= (SYSDATE - 60)
                        GROUP BY cc.category_norm
                    )
                    SELECT r.category, (r.cnt - NVL(p.cnt, 0)) AS diff, r.cnt
                    FROM recent r
                    LEFT JOIN prev p ON r.category_norm = p.category_norm
                    ORDER BY diff DESC, r.cnt DESC
                    FETCH FIRST 1 ROW ONLY
                    """,
                    {"p_uid": firebase_uid},
                )
                row = cursor.fetchone()
                if row and row[1] is not None and row[1] > 0:
                    category, diff, recent_cnt = row
                    cards.append(
                        InsightCard(
                            id=f"cat-growth-{normalize_text(category)}",
                            type="CATEGORY_STATS",
                            title="Son 30 günde en çok büyüyen kategori",
                            body=f"{category} (+{int(diff)})",
                            meta={"category": category, "diff": int(diff), "recent_count": int(recent_cnt)},
                        )
                    )

    except Exception as e:
        logger.error(f"Category stats insight failed: {e}")

    # Limit category cards to 2 for balance
    return cards[:2]


def _build_unlabeled_cluster(firebase_uid: str) -> Optional[InsightCard]:
    try:
        with DatabaseManager.get_read_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT t.id, t.title, t.content_chunk, t.vec_embedding
                    FROM TOMEHUB_CONTENT t
                    WHERE t.firebase_uid = :p_uid
                      AND t.source_type IN ('HIGHLIGHT','PERSONAL_NOTE','NOTES','INSIGHT')
                      AND t.vec_embedding IS NOT NULL
                      AND NOT EXISTS (
                        SELECT 1 FROM TOMEHUB_CONCEPT_CHUNKS cc
                        WHERE cc.content_id = t.id
                      )
                    FETCH FIRST 50 ROWS ONLY
                    """,
                    {"p_uid": firebase_uid},
                )
                rows = cursor.fetchall()

                candidates = []
                for content_id, title, content_chunk, vec_data in rows:
                    vec = _to_list(vec_data)
                    if vec:
                        candidates.append((content_id, title, content_chunk, vec))

                for idx, (cid, title, content_chunk, vec) in enumerate(candidates):
                    cluster = [(cid, title, content_chunk)]
                    for j in range(idx + 1, len(candidates)):
                        _, t2, c2, v2 = candidates[j]
                        sim = _cosine_similarity(vec, v2)
                        if sim >= UNLABELED_CLUSTER_SIM_THRESHOLD:
                            cluster.append((candidates[j][0], t2, c2))
                    if len(cluster) >= 2:
                        example = cluster[0][1] or "Benzer notlar"
                        return InsightCard(
                            id=f"cluster-{cid}",
                            type="UNLABELED_CLUSTER",
                            title="Etiketsiz bir küme tespit edildi",
                            body=f'Birden fazla not aynı şeyi söylüyor ama bunun adı yok. Örnek: "{example}"',
                            meta={"cluster_size": len(cluster)},
                        )
    except Exception as e:
        logger.error(f"Unlabeled cluster insight failed: {e}")

    return None
