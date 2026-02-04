# Data Maintenance Notes

## TOMEHUB_CONTENT Text Field Backfill

Purpose:
- Fix placeholder text in `NORMALIZED_CONTENT` / `TEXT_DEACCENTED`.
- Populate `LEMMA_TOKENS` for search quality.

Script:
- `apps/backend/scripts/backfill_content_text_fields.py`

Requirements:
- `zeyrek` must be installed.
- NLTK Turkish tokenizer data is required:
  - Run `python -c "import nltk; nltk.download('punkt_tab')"` once per environment.

Behavior:
- Reads from `content_chunk`.
- Writes `normalized_content`, `text_deaccented`, `lemma_tokens`.
- Uses batch commits to avoid long locks.

Verification:
- `normalized_content` should not contain `highlight from` placeholders.
- `lemma_tokens` should not be `[]`.

## TOMEHUB_CONTENT Tags/Categories Normalization

Purpose:
- Normalize `CATEGORIES` (VARCHAR2) and `TAGS` (CLOB) into lookup tables for fast filtering.

Script:
- `apps/backend/scripts/backfill_content_tags_categories.py`

Behavior:
- Reads `categories` and `tags` from `TOMEHUB_CONTENT`.
- Writes rows to:
  - `TOMEHUB_CONTENT_CATEGORIES`
  - `TOMEHUB_CONTENT_TAGS`
- De-duplicates by normalized value.

## File Reports JSON Search

Purpose:
- Use JSON search index on `TOMEHUB_FILE_REPORTS.KEY_TOPICS` for fast topic lookups.

API:
- `GET /api/reports/search?topic=<Topic>&limit=<N>&firebase_uid=<UID>`

Notes:
- Uses `JSON_EXISTS` with case-insensitive regex match.
- Falls back to `LIKE` if JSON query fails.
