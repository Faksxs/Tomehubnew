# Cleanup Stale Ingestion State: Bilginin Toplumsal Tarihi (PDF Only)

The ingestion for the book "Bilginin Toplumsal Tarihi" is stuck in `PROCESSING`. We will reset this state while ensuring that user-created content (highlights, notes) remains untouched.

## Proposed Changes

### Database Cleanup

A targeted cleanup script will be executed, strictly scoped ONLY to "Bilginin Toplumsal Tarihi" (ID: 1771795251587):

#### [TOMEHUB_INGESTED_FILES]
- Delete the record for `BOOK_ID = '1771795251587'` and `FIREBASE_UID = 'vpq1p0UzcCSLAh1d18WgZZWPBE63'`. This resets the "Processing" status in the UI.

#### [TOMEHUB_CONTENT_V2]
- **Targeted Delete**: Remove ONLY rows where:
    - `ITEM_ID = '1771795251587'`
    - `FIREBASE_UID = 'vpq1p0UzcCSLAh1d18WgZZWPBE63'`
    - `CONTENT_TYPE` is in `('PDF', 'EPUB', 'PDF_CHUNK')`
- **Preservation**: This query explicitly ignores `HIGHLIGHT`, `INSIGHT`, and `PERSONAL_NOTE` types, keeping them safe in the database.

---

## Verification Plan

### Automated Verification
Confirm following counts are 0:
1. `SELECT COUNT(*) FROM TOMEHUB_INGESTED_FILES WHERE BOOK_ID = '1771795251587'`
2. `SELECT COUNT(*) FROM TOMEHUB_CONTENT_V2 WHERE ITEM_ID = '1771795251587' AND CONTENT_TYPE IN ('PDF', 'EPUB', 'PDF_CHUNK')`

### Manual Verification
1. User checks that "Processing..." has disappeared in the UI.
2. User verifies that "Upload PDF" button is enabled.
3. User re-uploads the PDF.
