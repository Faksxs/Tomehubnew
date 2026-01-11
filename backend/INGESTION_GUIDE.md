# Book Ingestion Pipeline - Usage Guide

## Overview

The `ingest_book.py` script automates the complete data ingestion flow for PDF books into your TomeHub library.

**Pipeline Flow:**
```
PDF File → Text Extraction → Embedding Generation → Oracle Database
```

## Features

✅ Complete automation of ingestion process  
✅ Batch processing with single database connection  
✅ Error handling (skips failed chunks, continues processing)  
✅ Progress logging for each chunk  
✅ Interactive and command-line modes  
✅ Automatic embedding generation  
✅ Proper vector format for Oracle  

## Usage

### Interactive Mode

Run the script and follow the prompts:

```bash
python backend/ingest_book.py
```

You'll be asked for:
1. PDF file path
2. Book title
3. Author name
4. Firebase UID (optional, defaults to test_user_001)

### Command Line Mode

Provide arguments directly:

```bash
python backend/ingest_book.py "path/to/book.pdf" "Being and Time" "Martin Heidegger"
```

With custom user ID:

```bash
python backend/ingest_book.py "book.pdf" "Meditations" "Marcus Aurelius" "user_123"
```

## Example Session

```
======================================================================
TomeHub Book Ingestion - Interactive Mode
======================================================================

Enter PDF file path: C:\Books\being_and_time.pdf
Enter book title: Being and Time
Enter author name: Martin Heidegger
Enter Firebase UID (press Enter for test_user_001): 

======================================================================
Confirm Ingestion
======================================================================
PDF:    C:\Books\being_and_time.pdf
Title:  Being and Time
Author: Martin Heidegger
User:   test_user_001

Proceed with ingestion? (yes/no): yes

======================================================================
Step 1: Extracting PDF Content
======================================================================
[19:20:15] Starting PDF extraction...
[INFO] File: C:\Books\being_and_time.pdf
...
[SUCCESS] Extracted 342 chunks from PDF

======================================================================
Step 2: Connecting to Oracle Database
======================================================================
[19:20:45] [OK] Connected to database

======================================================================
Step 3: Processing Chunks and Generating Embeddings
======================================================================
[19:20:46] [Processing] Page 1, Chunk 1/342... [SAVED]
[19:20:48] [Processing] Page 1, Chunk 2/342... [SAVED]
[19:20:50] [Processing] Page 1, Chunk 3/342... [SAVED]
...

======================================================================
Step 4: Committing to Database
======================================================================
[19:35:12] [OK] Transaction committed

======================================================================
Ingestion Summary
======================================================================
Total chunks extracted:     342
Successfully inserted:      340
Failed (embedding):         1
Failed (database):          1
Success rate:               99.4%

======================================================================
[SUCCESS] Book ingestion complete!
======================================================================

'Being and Time' by Martin Heidegger is now searchable in your TomeHub library!
```

## Error Handling

The script handles errors gracefully:

### Failed Embeddings
If an embedding fails for a chunk, it logs the error and continues:
```
[19:21:05] [Processing] Page 5, Chunk 42/342... [FAILED - Embedding]
```

### Failed Database Inserts
If a database insert fails, it logs and continues:
```
[19:21:10] [Processing] Page 6, Chunk 55/342... [FAILED - DB Error: ORA-...]
```

### Empty Chunks
Chunks with less than 10 characters are automatically skipped:
```
[19:21:15] [SKIP] Page 10, Chunk 89/342 - Too short
```

## What Gets Stored

Each chunk is stored with:
- `firebase_uid`: User identifier
- `source_type`: "PDF"
- `title`: "{Book Title} - {Author}"
- `content_chunk`: Extracted text
- `chunk_type`: "paragraph", "heading", etc.
- `page_number`: Source page
- `chunk_index`: Sequential position
- `vec_embedding`: 768-dimensional vector

## Integration Example

Use in your own scripts:

```python
from ingest_book import ingest_book

# Ingest a book
success = ingest_book(
    pdf_path="philosophy_book.pdf",
    title="Critique of Pure Reason",
    author="Immanuel Kant",
    firebase_uid="user_456"
)

if success:
    print("Book successfully ingested!")
```

## Batch Processing Multiple Books

```python
from ingest_book import ingest_book

books = [
    ("book1.pdf", "Being and Time", "Heidegger"),
    ("book2.pdf", "Meditations", "Marcus Aurelius"),
    ("book3.pdf", "Republic", "Plato")
]

for pdf_path, title, author in books:
    print(f"\nIngesting: {title}...")
    success = ingest_book(pdf_path, title, author)
    if success:
        print(f"✓ {title} ingested successfully")
    else:
        print(f"✗ {title} failed")
```

## Performance Notes

- **Processing time**: ~2-3 seconds per chunk (embedding generation)
- **Database**: Single connection, batch commit at end
- **Memory**: Processes chunks sequentially (memory efficient)
- **Typical book**: 200-500 chunks, 10-25 minutes total

## Troubleshooting

### "Failed to extract content from PDF"
- Check PDF file path is correct
- Ensure OCI credentials are configured
- Verify PDF is not corrupted or password-protected

### "Failed to connect to database"
- Check Oracle credentials in backend/.env
- Verify wallet files are in place
- Test connection with: `python backend/main.py`

### "Failed - Embedding"
- Check GEMINI_API_KEY in backend/.env
- Verify internet connectivity
- Test embedding service: `python backend/embedding_service.py`

## Next Steps

After ingestion, you can:
1. Query your library with semantic search
2. Build RAG endpoints for Q&A
3. Create Flask API for frontend integration
4. Add more books to your library
