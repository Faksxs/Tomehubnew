# PDF Chunk Reingest Runbook

Use this only for selected problematic books.

1. Identify the target `firebase_uid` and `book_id`.
2. Run a quality audit before changes:

```powershell
python apps/backend/scripts/chunk_quality_audit.py --firebase-uid <uid> --book-id <book_id> --title "<title>" --author "<author>"
```

3. Purge the book content with the existing admin/internal flow.
4. Re-upload the original PDF through the normal ingestion UI or `/api/ingest`.
5. Run the same audit again and compare:
   - `broken_start_count`
   - `broken_end_count`
   - `bibliography_like_count`
   - `short_fragment_count`
   - `ocr_noise_count`
6. Check Flow manually for the same book and confirm that bibliography-like or mid-sentence cards are reduced.
