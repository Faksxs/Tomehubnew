# Phase 5 Query Profiling Baseline (2026-02-22)

- Generated: `2026-02-22 03:35:19 UTC`
- Scope: non-destructive profiling + index candidate audit
- Sample uid: `vpq1p0UzcCSLAh1d18WgZZWPBE63`
- Sample book_id: `1770687774840`
- SEARCH_LOGS time column: `TIMESTAMP`

## Table Counts

- `TOMEHUB_CONTENT`: `4534`
- `TOMEHUB_LIBRARY_ITEMS`: `267`
- `TOMEHUB_ITEM_INDEX_STATE`: `267`
- `TOMEHUB_INGESTED_FILES`: `15`
- `TOMEHUB_SEARCH_LOGS`: `1264`

## Table Stats Freshness

- `TOMEHUB_CONTENT` last_analyzed: `2026-02-22 02:23:40`
- `TOMEHUB_INGESTED_FILES` last_analyzed: `2026-02-22 00:17:14`
- `TOMEHUB_LIBRARY_ITEMS` last_analyzed: `2026-02-22 02:23:39`
- `TOMEHUB_SEARCH_LOGS` last_analyzed: `2026-02-18 01:25:44`

## Candidate Index Coverage

- `TOMEHUB_CONTENT(FIREBASE_UID, BOOK_ID, SOURCE_TYPE)` covered: `YES` | indexes: `IDX_CONT_UID_BOOK_SRC`
- `TOMEHUB_CONTENT(FIREBASE_UID, BOOK_ID, CREATED_AT)` covered: `YES` | indexes: `IDX_CONT_UID_BOOK_CRT`
- `TOMEHUB_CONTENT(FIREBASE_UID, BOOK_ID, CONTENT_TYPE)` covered: `YES` | indexes: `IDX_CONT_UID_BOOK_CTYPE`
- `TOMEHUB_INGESTED_FILES(FIREBASE_UID, BOOK_ID)` covered: `YES` | indexes: `IDX_INGEST_UID_BOOK`
- `TOMEHUB_SEARCH_LOGS(TIMESTAMP)` covered: `YES` | indexes: `IDX_SEARCH_LOGS_TIME`

## Representative Query Timings

- `content_by_uid_book_source_type`: rows=1, runs=5, p50=27.12ms, p95=47.74ms, max=47.74ms
- `content_by_uid_book_created_at`: rows=2, runs=5, p50=39.56ms, p95=57.54ms, max=57.54ms
- `library_item_by_uid`: rows=200, runs=5, p50=47.1ms, p95=47.32ms, max=47.32ms
- `ingestion_status_view_by_uid`: rows=15, runs=5, p50=22.1ms, p95=30.15ms, max=30.15ms
- `search_logs_recent_window`: rows=200, runs=5, p50=50.62ms, p95=57.57ms, max=57.57ms

## SEARCH_LOGS Recent Daily Volume

- `2026-02-22`: `21`
- `2026-02-21`: `1`
- `2026-02-20`: `6`
- `2026-02-19`: `1`
- `2026-02-18`: `96`
- `2026-02-17`: `17`
- `2026-02-16`: `3`
- `2026-02-15`: `2`
- `2026-02-14`: `22`
- `2026-02-13`: `184`
- `2026-02-12`: `155`
- `2026-02-11`: `480`
- `2026-02-10`: `1`
- `2026-02-09`: `5`

## Phase 5 Next Actions

1. Apply missing high-ROI indexes only where coverage=NO and timings justify.
2. Verify `SEARCH_LOGS(TIMESTAMP)` access path before partition migration.
3. Prepare partition migration runbook (attach/backfill/retention) after baseline sign-off.
