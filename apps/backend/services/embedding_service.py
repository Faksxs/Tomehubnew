# -*- coding: utf-8 -*-
"""
TomeHub Embedding Service
=========================
Handles text embedding generation via unified llm_client adapter.

Generates 768-dimensional vectors compatible with Oracle VECTOR(768, FLOAT32).
"""

import array
import logging
from typing import List, Optional

from config import settings
from services.circuit_breaker_service import (
    CircuitBreakerOpenException,
    RetryConfig,
    get_embedding_circuit_breaker,
    retry_with_backoff,
)
from services.llm_client import MODEL_TIER_EMBEDDING, embed_contents, get_model_for_tier

logger = logging.getLogger(__name__)

# Circuit breaker for embedding API
CIRCUIT_BREAKER = get_embedding_circuit_breaker()

# Retry configuration
RETRY_CONFIG = RetryConfig(
    max_retries=3,
    initial_delay=1.0,
    max_delay=10.0,
    backoff_factor=2.0,
    jitter=True,
)


def _call_embedding_api(text_or_list: str | List[str], task_type: str = "retrieval_document"):
    if not text_or_list:
        raise ValueError("Input must be a non-empty string or list")
    model_name = get_model_for_tier(MODEL_TIER_EMBEDDING)
    vectors = embed_contents(
        model=model_name,
        contents=text_or_list,
        task_type=task_type,
        output_dimensionality=768,
        timeout_s=30.0 if isinstance(text_or_list, list) else 20.0,
        task="embedding",
    )
    if not vectors:
        raise ValueError("Embedding API returned no vectors")

    if isinstance(text_or_list, list):
        return vectors
    return vectors[0]


def get_embedding(text: str) -> Optional[array.array]:
    """
    Generate an embedding for document retrieval.
    """
    if not text or not isinstance(text, str):
        logger.error("Invalid input: text must be a non-empty string")
        return None

    try:
        vector = CIRCUIT_BREAKER.call(
            retry_with_backoff,
            _call_embedding_api,
            RETRY_CONFIG,
            text,
            task_type="retrieval_document",
        )
        if vector:
            return array.array("f", vector)
        return None
    except CircuitBreakerOpenException as exc:
        logger.error("Embedding API circuit breaker OPEN: %s", exc)
        return None
    except Exception as exc:
        logger.error("Embedding generation failed: %s: %s", type(exc).__name__, exc)
        return None


def get_query_embedding(text: str) -> Optional[array.array]:
    """
    Generate an embedding optimized for search queries.
    """
    if not text or not isinstance(text, str):
        logger.error("Invalid input: text must be a non-empty string")
        return None

    try:
        vector = CIRCUIT_BREAKER.call(
            retry_with_backoff,
            _call_embedding_api,
            RETRY_CONFIG,
            text,
            task_type="retrieval_query",
        )
        if vector:
            return array.array("f", vector)
        return None
    except CircuitBreakerOpenException as exc:
        logger.error("Query embedding circuit breaker OPEN: %s", exc)
        return None
    except Exception as exc:
        logger.error("Query embedding generation failed: %s: %s", type(exc).__name__, exc)
        return None


def batch_get_embeddings(texts: List[str], task_type: str = "retrieval_document") -> List[Optional[array.array]]:
    """
    Generate embeddings for multiple texts with circuit breaker + retry.
    """
    if not texts:
        return []

    if not settings.GEMINI_API_KEY:
        logger.error("GEMINI_API_KEY not configured")
        return [None] * len(texts)

    try:
        logger.info("Generating batch embeddings for %s texts (type=%s)...", len(texts), task_type)
        vectors = CIRCUIT_BREAKER.call(
            retry_with_backoff,
            _call_embedding_api,
            RETRY_CONFIG,
            texts,
            task_type=task_type,
        )
        if not vectors:
            logger.error("Batch embedding returned no vectors")
            return [None] * len(texts)
        embeddings = [array.array("f", v) for v in vectors]
        logger.info("Batch embedding generated %s embeddings", len(embeddings))
        return embeddings
    except CircuitBreakerOpenException as exc:
        logger.error("Batch embedding circuit breaker OPEN: %s", exc)
        return [None] * len(texts)
    except Exception as exc:
        logger.error("Batch embedding failed: %s: %s", type(exc).__name__, exc)
        logger.info("Falling back to sequential embedding generation")
        return [get_embedding(t) for t in texts]


def get_circuit_breaker_status() -> dict:
    """Get current circuit breaker status for monitoring."""
    return CIRCUIT_BREAKER.get_status()
