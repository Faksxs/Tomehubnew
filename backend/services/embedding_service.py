# -*- coding: utf-8 -*-
"""
TomeHub Embedding Service
=========================
Handles text embedding generation using Google's Generative AI API.
Generates 768-dimensional vectors compatible with Oracle VECTOR(768, FLOAT32).

Author: TomeHub Team
Date: 2026-01-07
"""

import os
import array
from typing import Optional, List
from dotenv import load_dotenv
import google.generativeai as genai

# Load environment variables from .env file - go up one level from services/ to backend/
env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '.env')
load_dotenv(dotenv_path=env_path)

# Configure Gemini API
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)


def get_embedding(text: str) -> Optional[array.array]:
    """
    Generate a 768-dimensional embedding vector for the given text.
    
    This function uses Google's text-embedding-004 model to convert text
    into a semantic vector representation suitable for storage in Oracle's
    VECTOR(768, FLOAT32) column type.
    
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
        print("[ERROR] Invalid input: text must be a non-empty string")
        return None
    
    # Check API key configuration
    if not GEMINI_API_KEY:
        print("[ERROR] GEMINI_API_KEY not found in .env file")
        return None
    
    try:
        # Call Gemini embedding API
        # task_type="retrieval_document" optimizes for document storage/retrieval
        result = genai.embed_content(
            model="models/text-embedding-004",
            content=text,
            task_type="retrieval_document"
        )
        
        # Extract embedding from result
        embedding_list = result['embedding']
        
        # Validate embedding dimensions
        if len(embedding_list) != 768:
            print(f"[WARNING] Expected 768 dimensions, got {len(embedding_list)}")
        
        # Convert to array.array("f", ...) for Oracle compatibility
        # "f" = float (32-bit), matching FLOAT32 in Oracle VECTOR type
        embedding_array = array.array("f", embedding_list)
        
        return embedding_array
        
    except Exception as e:
        print(f"[ERROR] Failed to generate embedding: {e}")
        import traceback
        traceback.print_exc()
        return None


def get_query_embedding(text: str) -> Optional[array.array]:
    """
    Generate an embedding optimized for search queries.
    
    This is a specialized version of get_embedding() that uses
    task_type="retrieval_query" for better query-to-document matching.
    
    Args:
        text (str): The search query text.
    
    Returns:
        array.array or None: A 768-dimensional float array, or None on failure.
    """
    if not text or not isinstance(text, str):
        print("[ERROR] Invalid input: text must be a non-empty string")
        return None
    
    if not GEMINI_API_KEY:
        print("[ERROR] GEMINI_API_KEY not found in .env file")
        return None
    
    try:
        # Use retrieval_query task type for search queries
        result = genai.embed_content(
            model="models/text-embedding-004",
            content=text,
            task_type="retrieval_query"
        )
        
        embedding_list = result['embedding']
        
        if len(embedding_list) != 768:
            print(f"[WARNING] Expected 768 dimensions, got {len(embedding_list)}")
        
        embedding_array = array.array("f", embedding_list)
        
        return embedding_array
        
    except Exception as e:
        print(f"[ERROR] Failed to generate query embedding: {e}")
        import traceback
        traceback.print_exc()
        return None


def batch_get_embeddings(texts: List[str]) -> List[Optional[array.array]]:
    """
    Generate embeddings for multiple texts in batch.
    
    Note: This processes texts sequentially. For production use,
    consider implementing proper batch API calls if available.
    
    Args:
        texts (List[str]): List of texts to embed.
    
    Returns:
        List[Optional[array.array]]: List of embeddings, with None for failures.
    """
    embeddings = []
    
    for i, text in enumerate(texts):
        print(f"[INFO] Processing text {i+1}/{len(texts)}...")
        embedding = get_embedding(text)
        embeddings.append(embedding)
    
    return embeddings


# ============================================================================
# TEST BLOCK
# ============================================================================

if __name__ == "__main__":
    print("=" * 70)
    print("TomeHub Embedding Service - Test")
    print("=" * 70)
    
    # Test with a philosophical sentence
    test_text = "Dasein is a being that is concerned with its own being and existence in the world."
    
    print(f"\n[TEST] Generating embedding for:")
    print(f'"{test_text}"')
    print()
    
    # Generate embedding
    embedding = get_embedding(test_text)
    
    if embedding is not None:
        print(f"[SUCCESS] Embedding generated successfully!")
        print(f"  Dimensions: {len(embedding)}")
        print(f"  Type: {type(embedding)}")
        print(f"  First 5 values: {list(embedding[:5])}")
        print(f"  Data type: {embedding.typecode} (should be 'f' for float32)")
        
        # Verify it's compatible with Oracle
        print(f"\n[INFO] This embedding is ready for Oracle VECTOR(768, FLOAT32)")
        
    else:
        print("[FAILED] Could not generate embedding")
        print("[INFO] Please check:")
        print("  1. GEMINI_API_KEY is set in backend/.env")
        print("  2. You have internet connectivity")
        print("  3. The API key is valid")
    
    print("\n" + "=" * 70)
    
    # Test query embedding
    print("\n[TEST] Testing query embedding...")
    query = "What is Heidegger's view on existence?"
    query_embedding = get_query_embedding(query)
    
    if query_embedding is not None:
        print(f"[SUCCESS] Query embedding generated!")
        print(f"  Dimensions: {len(query_embedding)}")
    else:
        print("[FAILED] Could not generate query embedding")
    
    print("\n" + "=" * 70)
