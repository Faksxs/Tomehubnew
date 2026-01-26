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
            task_type="retrieval_document",
            request_options={'timeout': 20}
        )
        
        # Extract embedding from result
        embedding_list = None
        if isinstance(result, dict):
            embedding_list = result.get('embedding')
        elif hasattr(result, 'embedding'):
            embedding_list = result.embedding
        
        # If still None, try subscription in case it's a different mapping type
        if embedding_list is None:
            try:
                embedding_list = result['embedding']
            except (KeyError, TypeError):
                pass
                
        if not embedding_list:
            print(f"[ERROR] API returned response but 'embedding' data is missing. Result: {result}")
            return None
        
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
            task_type="retrieval_query",
            request_options={'timeout': 20}
        )
        
        embedding_list = None
        if isinstance(result, dict):
            embedding_list = result.get('embedding')
        elif hasattr(result, 'embedding'):
            embedding_list = result.embedding
            
        if embedding_list is None:
            try:
                embedding_list = result['embedding']
            except (KeyError, TypeError):
                pass
        
        if not embedding_list:
            print(f"[ERROR] API returned response but 'embedding' data is missing for query. Result: {result}")
            return None
        
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
    Generate embeddings for multiple texts in batch using Gemini's native batch support.
    
    This is significantly faster than sequential calls.
    
    Args:
        texts (List[str]): List of texts to embed.
    
    Returns:
        List[Optional[array.array]]: List of embeddings, with None for failures.
    """
    if not texts:
        return []
        
    if not GEMINI_API_KEY:
        print("[ERROR] GEMINI_API_KEY not found in .env file")
        return [None] * len(texts)
    
    try:
        print(f"[INFO] Generating embeddings for batch of {len(texts)} texts...")
        
        # Google Gemini supports batch embedding by passing a list to content
        result = genai.embed_content(
            model="models/text-embedding-004",
            content=texts,
            task_type="retrieval_document",
            request_options={'timeout': 30}
        )
        
        embeddings_list = None
        if isinstance(result, dict):
            embeddings_list = result.get('embedding')
        elif hasattr(result, 'embedding'):
            embeddings_list = result.embedding
            
        if embeddings_list is None:
            try:
                embeddings_list = result['embedding']
            except (KeyError, TypeError):
                pass
                
        if not embeddings_list:
            print(f"[ERROR] Batch API returned response but 'embedding' data is missing. Result: {result}")
            # Fallback to sequential to try and salvage individual items? 
            # Or just fail. The original code fell back on ANY exception.
            # We will raise an exception to trigger the fallback in the except block below.
            raise ValueError("Missing 'embedding' key in batch response")
        
        # Convert each embedding to array.array("f", ...)
        embeddings = []
        for emb in embeddings_list:
            embeddings.append(array.array("f", emb))
            
        return embeddings
        
    except Exception as e:
        print(f"[ERROR] Batch embedding failed: {e}")
        # Fallback to sequential if batch fails for some reason (e.g. too large)
        print("[INFO] Falling back to sequential generation...")
        return [get_embedding(t) for t in texts]


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
