# TomeHub Embedding Service - Usage Guide

## Overview

The `embedding_service.py` module provides text embedding generation using Google's Gemini text-embedding-004 model, producing 768-dimensional vectors compatible with Oracle's `VECTOR(768, FLOAT32)` type.

## Setup

### 1. Install Dependencies

```bash
pip install google-generativeai
```

### 2. Configure API Key

Add your Gemini API key to `backend/.env`:

```env
GEMINI_API_KEY=your_actual_api_key_here
```

Get your API key from: https://makersuite.google.com/app/apikey

## Functions

### `get_embedding(text: str) -> Optional[array.array]`

Generates a 768-dimensional embedding for document storage.

**Parameters:**
- `text` (str): The text to embed (paragraph, sentence, or document chunk)

**Returns:**
- `array.array` (768 floats) or `None` on failure

**Example:**
```python
from embedding_service import get_embedding

text = "Heidegger's concept of Dasein explores being-in-the-world."
embedding = get_embedding(text)

if embedding:
    print(f"Generated {len(embedding)}-dimensional vector")
    # Use with Oracle
    cursor.execute(insert_sql, {"p_vec": embedding, ...})
```

### `get_query_embedding(text: str) -> Optional[array.array]`

Generates an embedding optimized for search queries.

**Parameters:**
- `text` (str): The search query

**Returns:**
- `array.array` (768 floats) or `None` on failure

**Example:**
```python
from embedding_service import get_query_embedding

query = "What is phenomenology?"
query_vec = get_query_embedding(query)

# Use for semantic search
cursor.execute("""
    SELECT title, content_chunk
    FROM TOMEHUB_CONTENT
    WHERE VECTOR_DISTANCE(vec_embedding, :p_vec, COSINE) < 0.5
    ORDER BY VECTOR_DISTANCE(vec_embedding, :p_vec, COSINE)
    FETCH FIRST 5 ROWS ONLY
""", {"p_vec": query_vec})
```

### `batch_get_embeddings(texts: List[str]) -> List[Optional[array.array]]`

Generates embeddings for multiple texts.

**Example:**
```python
from embedding_service import batch_get_embeddings

texts = [
    "First paragraph...",
    "Second paragraph...",
    "Third paragraph..."
]

embeddings = batch_get_embeddings(texts)
```

## Complete Integration Example

```python
import oracledb
from embedding_service import get_embedding

# Connect to Oracle
connection = oracledb.connect(...)
cursor = connection.cursor()

# Your content
content = "Marcus Aurelius teaches us to focus on what we can control."

# Generate embedding
embedding = get_embedding(content)

if embedding:
    # Insert into database
    cursor.execute("""
        INSERT INTO TOMEHUB_CONTENT 
        (firebase_uid, source_type, title, content_chunk, vec_embedding)
        VALUES (:p_uid, :p_type, :p_title, :p_content, :p_vec)
    """, {
        "p_uid": "user_123",
        "p_type": "NOTES",
        "p_title": "Stoicism Notes",
        "p_content": content,
        "p_vec": embedding
    })
    
    connection.commit()
    print("Content stored with embedding!")
```

## Testing

Run the test block:

```bash
python backend/embedding_service.py
```

Expected output:
```
======================================================================
TomeHub Embedding Service - Test
======================================================================

[TEST] Generating embedding for:
"Dasein is a being that is concerned with its own being..."

[SUCCESS] Embedding generated successfully!
  Dimensions: 768
  Type: <class 'array.array'>
  First 5 values: [0.0123, -0.0456, 0.0789, ...]
  Data type: f (should be 'f' for float32)

[INFO] This embedding is ready for Oracle VECTOR(768, FLOAT32)
======================================================================
```

## Error Handling

The module includes robust error handling:

```python
embedding = get_embedding("some text")

if embedding is None:
    # Handle failure
    print("Failed to generate embedding")
    # Check:
    # 1. GEMINI_API_KEY is set
    # 2. Internet connectivity
    # 3. API key is valid
```

## Performance Notes

- Each API call takes ~200-500ms
- For batch processing, use `batch_get_embeddings()`
- Consider caching embeddings to avoid redundant API calls
- The text-embedding-004 model supports up to 2048 tokens per request

## Next Steps

1. Add your GEMINI_API_KEY to `backend/.env`
2. Test the module: `python backend/embedding_service.py`
3. Integrate with your PDF ingestion pipeline
4. Use for RAG queries
