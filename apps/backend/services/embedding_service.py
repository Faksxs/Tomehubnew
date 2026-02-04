# -*- coding: utf-8 -*-
"""
TomeHub Embedding Service
=========================
Handles text embedding generation using Google's Generative AI API.
Generates 768-dimensional vectors compatible with Oracle VECTOR(768, FLOAT32).

Features:
- Circuit breaker for API resilience
- Retry logic with exponential backoff
- Comprehensive error logging
- Metrics for monitoring

Author: TomeHub Team
Date: 2026-01-07 (updated 2026-02-02 for Phase 2)
"""

import os
import array
import time
import logging
from typing import Optional, List
from dotenv import load_dotenv
import google.generativeai as genai

from services.circuit_breaker_service import (
    get_embedding_circuit_breaker,
    RetryConfig,
    retry_with_backoff,
    CircuitBreakerOpenException
)

logger = logging.getLogger(__name__)

# Load environment variables from .env file - go up one level from services/ to backend/
env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '.env')
load_dotenv(dotenv_path=env_path)

# Configure Gemini API
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

# Circuit breaker for embedding API
CIRCUIT_BREAKER = get_embedding_circuit_breaker()

# Retry configuration
RETRY_CONFIG = RetryConfig(
    max_retries=3,
    initial_delay=1.0,
    max_delay=10.0,
    backoff_factor=2.0,
    jitter=True
)


from services.monitoring import AI_SERVICE_LATENCY

def _call_gemini_api(text_or_list: Any, task_type: str = "retrieval_document") -> Any:
    """
    Internal function to call Gemini embedding API.
    Supports both single text (str) and multiple texts (List[str]).
    """
    if not text_or_list:
        raise ValueError("Input must be non-empty string or list")
    
    is_batch = isinstance(text_or_list, list)
    
    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY not configured")
    
    start_time = time.time()
    
    try:
        # Call Gemini embedding API
        with AI_SERVICE_LATENCY.labels(service="google_embedding", operation="embed").time():
            result = genai.embed_content(
                model="models/gemini-embedding-001",
                content=text_or_list,
                task_type=task_type,
                output_dimensionality=768,
                request_options={'timeout': 30 if is_batch else 20}
            )
        
        latency_ms = (time.time() - start_time) * 1000
        
        if is_batch:
            # For batch calls, result typically has 'embeddings' key
            # In the Python SDK, it might be an object with an 'embeddings' attribute
            if hasattr(result, 'embeddings'):
                embeddings = result.embeddings
            elif isinstance(result, dict):
                embeddings = result.get('embeddings', [])
            else:
                embeddings = []
                
            if not embeddings:
                logger.error(f"Batch API returned no embedding data. Result: {result}")
                raise ValueError("Missing batch embedding data")
            
            logger.debug(f"✓ Batch Embedding API call successful: {len(embeddings)} items ({latency_ms:.0f}ms)")
            return embeddings
        else:
            # Single call logic
            embedding_list = None
            if hasattr(result, 'embedding'):
                embedding_list = result.embedding
            elif isinstance(result, dict):
                embedding_list = result.get('embedding')
            
            if not embedding_list:
                logger.error(f"API returned response but 'embedding' data missing. Result: {result}")
                raise ValueError("Missing embedding data in response")
            
            logger.debug(f"✓ Embedding API call successful ({latency_ms:.0f}ms)")
            return embedding_list

        
    except TimeoutError as e:
        logger.error(f"Embedding API timeout (20s exceeded): {e}")
        raise
    except Exception as e:
        logger.error(f"Embedding API error ({type(e).__name__}): {e}")
        raise


def get_embedding(text: str) -> Optional[array.array]:
    """
    Generate a 768-dimensional embedding vector for the given text.
    
    Protected by circuit breaker and retry logic. If the API fails:
    - Individual failures: Retry with exponential backoff
    - Repeated failures: Circuit breaker opens, fail fast
    - Circuit open: Returns None immediately
    
    This function is used for document/content embedding with task_type="retrieval_document".
    
    Args:
        text (str): The text to embed. Should be a meaningful chunk of content
                   (paragraph, sentence, or document excerpt).
    
    Returns:
        array.array or None: A 768-dimensional float array compatible with
                            oracledb, or None if the API call fails.
    
    Example:
        >>> embedding = get_embedding("Heidegger's concept of Dasein")
        >>> print(len(embedding))  # Should print 768
        768
    """
    # Validate input
    if not text or not isinstance(text, str):
        logger.error("Invalid input: text must be a non-empty string")
        return None
    
    try:
        # Call with circuit breaker protection and retry logic
        embedding_list = CIRCUIT_BREAKER.call(
            retry_with_backoff,
            _call_gemini_api,
            RETRY_CONFIG,
            text,
            task_type="retrieval_document"
        )
        
        if embedding_list:
            # Convert to array.array("f", ...) for Oracle compatibility
            # "f" = float (32-bit), matching FLOAT32 in Oracle VECTOR type
            embedding_array = array.array("f", embedding_list)
            return embedding_array
        
        return None
        
    except CircuitBreakerOpenException as e:
        # Circuit breaker is open - fail fast
        logger.error(f"⚠️ Embedding API circuit breaker OPEN: {e}")
        logger.info("Semantic search disabled. Searches will use keyword matching only.")
        return None
    except Exception as e:
        # Other exceptions (validation errors, etc.)
        logger.error(f"Embedding generation failed: {type(e).__name__}: {e}")
        return None


def get_query_embedding(text: str) -> Optional[array.array]:
    """
    Generate an embedding optimized for search queries.
    
    This is a specialized version of get_embedding() that uses
    task_type="retrieval_query" for better query-to-document matching.
    
    Protected by the same circuit breaker and retry logic.
    
    Args:
        text (str): The search query text.
    
    Returns:
        array.array or None: A 768-dimensional float array, or None on failure.
    """
    if not text or not isinstance(text, str):
        logger.error("Invalid input: text must be a non-empty string")
        return None
    
    try:
        # Call with circuit breaker and retry logic
        embedding_list = CIRCUIT_BREAKER.call(
            retry_with_backoff,
            _call_gemini_api,
            RETRY_CONFIG,
            text,
            task_type="retrieval_query"
        )
        
        if embedding_list:
            embedding_array = array.array("f", embedding_list)
            return embedding_array
        
        return None
        
    except CircuitBreakerOpenException as e:
        logger.error(f"⚠️ Query embedding circuit breaker OPEN: {e}")
        return None
    except Exception as e:
        logger.error(f"Query embedding generation failed: {type(e).__name__}: {e}")
        return None


def batch_get_embeddings(texts: List[str], task_type: str = "retrieval_document") -> List[Optional[array.array]]:
    """
    Generate embeddings for multiple texts in batch using Gemini's native batch support.
    
    Args:
        texts (List[str]): List of texts to embed.
        task_type (str): "retrieval_document" or "retrieval_query"
    """
    if not texts:
        return []
    
    if not GEMINI_API_KEY:
        logger.error("GEMINI_API_KEY not configured")
        return [None] * len(texts)
    
    try:
        logger.info(f"Generating batch embeddings for {len(texts)} texts (type={task_type})...")
        
        # Call with circuit breaker and retry protection
        embeddings_list = CIRCUIT_BREAKER.call(
            retry_with_backoff,
            _call_gemini_api,
            RETRY_CONFIG,
            texts,  # Pass list directly
            task_type=task_type
        )
        
        if not embeddings_list:
            logger.error("Batch API returned no embeddings")
            return [None] * len(texts)
        
        # Convert each embedding to array.array("f", ...)
        embeddings = []
        for emb in embeddings_list:
            embeddings.append(array.array("f", emb))
        
        logger.info(f"✓ Batch embedding generated {len(embeddings)} embeddings")
        return embeddings
        
    except CircuitBreakerOpenException as e:
        logger.error(f"⚠️ Batch embedding circuit breaker OPEN: {e}")
        logger.info("Falling back to keyword-only search")
        return [None] * len(texts)
    except Exception as e:
        logger.error(f"Batch embedding failed: {type(e).__name__}: {e}")
        logger.info("Falling back to sequential embedding generation")
        # Fallback to sequential if batch fails
        return [get_embedding(t) for t in texts]


def get_circuit_breaker_status() -> dict:
    """Get current circuit breaker status for monitoring"""
    return CIRCUIT_BREAKER.get_status()
