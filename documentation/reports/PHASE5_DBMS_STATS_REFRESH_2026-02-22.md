# Phase 5 DBMS_STATS Refresh Report (2026-02-22)

- Generated: `2026-02-22 22:58:46 UTC`
- Mode: `EXECUTE`
- Degree: `2`

## Target Tables

- `TOMEHUB_CONTENT` row_count=`4540`
- `TOMEHUB_INGESTED_FILES` row_count=`15`
- `TOMEHUB_LIBRARY_ITEMS` row_count=`267`
- `TOMEHUB_ITEM_INDEX_STATE` row_count=`267`
- `TOMEHUB_SEARCH_LOGS` row_count=`1265`

## Actions

- Applied: `TOMEHUB_CONTENT`
- Applied: `TOMEHUB_INGESTED_FILES`
- Applied: `TOMEHUB_LIBRARY_ITEMS`
- Applied: `TOMEHUB_ITEM_INDEX_STATE`
- Applied: `TOMEHUB_SEARCH_LOGS`

## Stats Snapshot (Before -> After)

### `TOMEHUB_CONTENT`
- `last_analyzed`: `2026-02-22 05:09:24` -> `2026-02-22 22:58:44`
- `num_rows`: `4534` -> `4540`
- `sample_size`: `4534` -> `4540`
- `stale_stats`: `NO` -> `NO`

### `TOMEHUB_INGESTED_FILES`
- `last_analyzed`: `2026-02-22 08:09:27` -> `2026-02-22 22:58:45`
- `num_rows`: `15` -> `15`
- `sample_size`: `15` -> `15`
- `stale_stats`: `NO` -> `NO`

### `TOMEHUB_LIBRARY_ITEMS`
- `last_analyzed`: `2026-02-22 02:23:39` -> `2026-02-22 22:58:45`
- `num_rows`: `267` -> `267`
- `sample_size`: `267` -> `267`
- `stale_stats`: `NO` -> `NO`

### `TOMEHUB_ITEM_INDEX_STATE`
- `last_analyzed`: `2026-02-22 02:38:43` -> `2026-02-22 22:58:46`
- `num_rows`: `267` -> `267`
- `sample_size`: `267` -> `267`
- `stale_stats`: `NO` -> `NO`

### `TOMEHUB_SEARCH_LOGS`
- `last_analyzed`: `2026-02-18 01:25:44` -> `2026-02-22 22:58:46`
- `num_rows`: `1170` -> `1265`
- `sample_size`: `1170` -> `1265`
- `stale_stats`: `NO` -> `NO`

## Notes

- `cascade=>TRUE` also refreshes dependent index stats.
- Use this before plan comparisons to reduce optimizer jitter from stale stats.
