# PDF Service Usage Guide

## Overview

The `pdf_service.py` module extracts structured content from PDF files using OCI Document Understanding service. It returns organized chunks with page numbers, content types, and metadata - ready for embedding generation.

## Setup

### Prerequisites

1. OCI credentials configured in `backend/.env`
2. OCI SDK installed: `pip install oci`
3. Valid PDF file to process

## Main Function

### `extract_pdf_content(pdf_path: str) -> List[Dict]`

Extracts structured content from a PDF file.

**Parameters:**
- `pdf_path` (str): Path to the PDF file

**Returns:**
List of dictionaries, each containing:
```python
{
    'text': str,           # Extracted text content
    'page_num': int,       # Page number (1-indexed)
    'type': str,           # Content type ('paragraph', 'heading', etc.)
    'confidence': float,   # OCR confidence (0-1)
    'line_index': int,     # Line position on page
    'bbox': dict          # Bounding box (optional)
}
```

**Example:**
```python
from pdf_service import extract_pdf_content

chunks = extract_pdf_content("being_and_time.pdf")

for chunk in chunks:
    print(f"Page {chunk['page_num']}: {chunk['text'][:50]}...")
```

## Integration with Embedding Service

Combine PDF extraction with embedding generation:

```python
from pdf_service import extract_pdf_content
from embedding_service import get_embedding
import oracledb

# 1. Extract PDF content
chunks = extract_pdf_content("philosophy_book.pdf")

# 2. Connect to database
connection = oracledb.connect(...)
cursor = connection.cursor()

# 3. Process each chunk
for i, chunk in enumerate(chunks):
    # Generate embedding
    embedding = get_embedding(chunk['text'])
    
    if embedding:
        # Store in database
        cursor.execute("""
            INSERT INTO TOMEHUB_CONTENT 
            (firebase_uid, source_type, title, content_chunk, 
             chunk_type, page_number, chunk_index, vec_embedding)
            VALUES (:p_uid, :p_type, :p_title, :p_content, 
                    :p_chunk_type, :p_page, :p_chunk_idx, :p_vec)
        """, {
            "p_uid": "user_123",
            "p_type": "PDF",
            "p_title": "Being and Time",
            "p_content": chunk['text'],
            "p_chunk_type": chunk['type'],
            "p_page": chunk['page_num'],
            "p_chunk_idx": i,
            "p_vec": embedding
        })

connection.commit()
print(f"Ingested {len(chunks)} chunks!")
```

## Complete Ingestion Pipeline

```python
def ingest_pdf_to_database(pdf_path, firebase_uid, title):
    """Complete pipeline: PDF → Chunks → Embeddings → Database"""
    
    from pdf_service import extract_pdf_content
    from embedding_service import get_embedding
    import oracledb
    
    # Extract PDF content
    print(f"Extracting content from {pdf_path}...")
    chunks = extract_pdf_content(pdf_path)
    
    if not chunks:
        print("Failed to extract PDF content")
        return False
    
    # Connect to database
    connection = oracledb.connect(...)
    cursor = connection.cursor()
    
    # Process chunks
    successful = 0
    for i, chunk in enumerate(chunks):
        # Generate embedding
        embedding = get_embedding(chunk['text'])
        
        if embedding:
            cursor.execute("""
                INSERT INTO TOMEHUB_CONTENT 
                (firebase_uid, source_type, title, content_chunk, 
                 chunk_type, page_number, chunk_index, vec_embedding)
                VALUES (:p_uid, :p_type, :p_title, :p_content, 
                        :p_chunk_type, :p_page, :p_chunk_idx, :p_vec)
            """, {
                "p_uid": firebase_uid,
                "p_type": "PDF",
                "p_title": title,
                "p_content": chunk['text'],
                "p_chunk_type": chunk['type'],
                "p_page": chunk['page_num'],
                "p_chunk_idx": i,
                "p_vec": embedding
            })
            successful += 1
    
    connection.commit()
    cursor.close()
    connection.close()
    
    print(f"Successfully ingested {successful}/{len(chunks)} chunks")
    return True

# Usage
ingest_pdf_to_database(
    "heidegger_being_and_time.pdf",
    "user_123",
    "Being and Time - Heidegger"
)
```

## Testing

Run the test block:

```bash
python backend/pdf_service.py
```

You'll be prompted for a PDF file path. The script will:
1. Extract all content
2. Show first 3 chunks with metadata
3. Display statistics (pages, chunks, types)
4. Save results to `pdf_extraction_output.json`

## Error Handling

The module includes comprehensive error handling:

```python
chunks = extract_pdf_content("book.pdf")

if chunks is None:
    # Handle extraction failure
    print("Failed to extract PDF")
    # Possible causes:
    # - File not found
    # - Invalid PDF format
    # - OCI API error
    # - Network timeout
```

## Performance Notes

- Processing time: ~2-5 seconds per page
- File size limit: Check OCI Document Understanding limits
- Supported formats: PDF only
- OCR: Automatically applied to scanned PDFs

## Output Structure

Example chunk:
```json
{
  "text": "Dasein is a being that is concerned with its own being.",
  "page_num": 42,
  "type": "paragraph",
  "confidence": 0.99,
  "line_index": 5,
  "bbox": {
    "points": [[0.1, 0.2], [0.9, 0.2], [0.9, 0.3], [0.1, 0.3]]
  }
}
```

## Next Steps

1. Test with your PDF files
2. Integrate with `embedding_service.py`
3. Build complete ingestion pipeline
4. Add to your Flask API
