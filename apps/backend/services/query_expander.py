# -*- coding: utf-8 -*-
import os
import json
import logging
import google.generativeai as genai
from typing import List, Optional
from tenacity import retry, stop_after_attempt, wait_exponential

from services.cache_service import MultiLayerCache, generate_cache_key, get_cache
from config import settings

logger = logging.getLogger(__name__)

class QueryExpander:
    """
    Generates semantic variations of search queries to improve recall.
    Uses LLM to find synonyms, related concepts, and alternative phrasings.
    """
    
    def __init__(self, cache: Optional[MultiLayerCache] = None):
        # API Key should be configured globally, but we double check
        if not os.getenv("GEMINI_API_KEY"):
            logger.warning("GEMINI_API_KEY not found. Query expansion will be disabled.")
        
        self.cache = cache or get_cache()
            
    def expand_query(self, query: str, max_variations: int = 3) -> List[str]:
        """
        Generate alternative search queries with caching.
        
        Args:
            query: Original user query
            max_variations: Limit 3 to prevent noise/latency
            
        Returns:
            List of unique query strings (variations only, not including original)
        """
        if not query or len(query.split()) < 2:
            return []
        
        # Check cache first
        if self.cache:
            cache_key = generate_cache_key(
                service="expansion",
                query=query,
                firebase_uid="",  # Expansions are query-only, not user-specific
                book_id=None,
                limit=max_variations,
                version=settings.LLM_MODEL_VERSION
            )
            cached_variations = self.cache.get(cache_key)
            if cached_variations:
                logger.info(f"Cache hit for query expansion: {query[:30]}...")
                return cached_variations
        
        # Generate variations
        variations = self._expand_query_impl(query, max_variations)
        
        # Store in cache (TTL: 7 days = 604800 seconds)
        if self.cache and variations:
            cache_key = generate_cache_key(
                service="expansion",
                query=query,
                firebase_uid="",
                book_id=None,
                limit=max_variations,
                version=settings.LLM_MODEL_VERSION
            )
            self.cache.set(cache_key, variations, ttl=604800)
            logger.info(f"Cached query expansion for key: {cache_key[:50]}...")
        
        return variations
    
    @retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=1, max=5))
    def _expand_query_impl(self, query: str, max_variations: int = 3) -> List[str]:
        """
        Internal implementation of query expansion (called by expand_query).
        """
        try:
            model = genai.GenerativeModel('gemini-2.0-flash')
            
            prompt = f"""
            Act as a search optimization engine.
            Generate {max_variations} alternative search queries for the following user input.
            Focus on:
            1. Synonyms (e.g., "cost" -> "price", "expense")
            2. Conceptual paraphrasing (e.g., "how to code" -> "programming guide")
            3. Removing potential ambiguity
            
            User Input: "{query}"
            
            Return ONLY a JSON list of strings. Example: ["variation1", "variation2"]
            """
            
            response = model.generate_content(prompt, request_options={'timeout': 5})
            text = response.text.strip()
            
            # Simple cleanup
            import re
            json_match = re.search(r'\[.*\]', text, re.DOTALL)
            if json_match:
                variations = json.loads(json_match.group(0))
                # Validate
                cleaned = [v.strip() for v in variations if isinstance(v, str) and v.strip()]
                return cleaned[:max_variations]
            
            return []
            
        except Exception as e:
            logger.warning(f"Query expansion failed: {e}")
            return []

if __name__ == "__main__":
    # Test
    expander = QueryExpander()
    print(expander.expand_query("vicdanın doğası"))
