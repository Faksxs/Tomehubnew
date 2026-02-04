# Layer-3 Analytics (Lemma-Based Word Count)

## Overview
Layer-3 now supports deterministic analytic questions such as:
- `kitap kaç kez geçiyor`
- `"özgürlük" kelimesi kaç defa geçiyor`

These queries bypass the LLM and return a direct count.

## Matching Rules
- **Lemma-based**: counts morphological variants (e.g., `kitap`, `kitabın`, `kitapta`, `kitaplar`).
- **Scope**: only book chunks (`PDF`, `EPUB`, `PDF_CHUNK`).

## Data Source
Counts are computed from `TOMEHUB_CONTENT.TOKEN_FREQ`, a JSON map of lemma -> count.

Example:
```
{"kitap": 12, "okumak": 3, "insan": 8}
```

## Setup
1. Run migration:
```
python apps/backend/scripts/run_token_freq_migration.py
```

2. Backfill existing content:
```
python apps/backend/scripts/backfill_token_freq.py
```

## Response Metadata
Analytic responses include:
```
metadata.analytics = {
  "type": "word_count",
  "term": "kitap",
  "count": 12,
  "match": "lemma",
  "scope": "book_chunks"
}
```
