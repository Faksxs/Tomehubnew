# Phase 3 Integrity Hardening Report

- **Generated (UTC):** 2026-02-24 03:04:23Z
- **Mode:** DRY-RUN
- **Cleanup orphans:** False

## Summary

- OK: `4`
- WARN: `0`
- FAIL: `1`

## Checks

| Check | Status | Value |
|---|---|---|
| `table_exists:TOMEHUB_LIBRARY_ITEMS` | `OK` | `True` |
| `table_exists:TOMEHUB_CONTENT` | `FAIL` | `False` |
| `table_exists:TOMEHUB_INGESTED_FILES` | `OK` | `True` |
| `table_exists:TOMEHUB_FILE_REPORTS` | `OK` | `True` |
| `table_exists:TOMEHUB_ITEM_INDEX_STATE` | `OK` | `True` |

## Notes

- FK constraints are intentionally report-only in this phase runner unless write paths are fully migrated.
- Composite unique key `UQ_LIBITEM_UID_ITEM` is added as safe preparation for future composite FKs.
