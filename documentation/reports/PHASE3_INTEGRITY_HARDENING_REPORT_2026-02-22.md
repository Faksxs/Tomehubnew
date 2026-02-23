# Phase 3 Integrity Hardening Report

- **Generated (UTC):** 2026-02-22 23:08:00Z
- **Mode:** DRY-RUN
- **Cleanup orphans:** False

## Summary

- OK: `18`
- WARN: `0`
- FAIL: `0`

## Checks

| Check | Status | Value |
|---|---|---|
| `table_exists:TOMEHUB_LIBRARY_ITEMS` | `OK` | `True` |
| `table_exists:TOMEHUB_CONTENT` | `OK` | `True` |
| `table_exists:TOMEHUB_INGESTED_FILES` | `OK` | `True` |
| `table_exists:TOMEHUB_FILE_REPORTS` | `OK` | `True` |
| `table_exists:TOMEHUB_ITEM_INDEX_STATE` | `OK` | `True` |
| `content_orphans_vs_library_items` | `OK` | `0` |
| `ingested_files_orphans_vs_library_items` | `OK` | `0` |
| `file_reports_orphans_vs_library_items` | `OK` | `0` |
| `item_index_state_orphans_vs_library_items` | `OK` | `0` |
| `library_items_duplicate_uid_item` | `OK` | `0` |
| `library_items_item_id_cross_uid_collision` | `OK` | `0` |
| `library_items_personal_note_visibility` | `OK` | `0` |
| `content_personal_note_visibility` | `OK` | `0` |
| `legacy_books_missing_in_library_items` | `OK` | `0` |
| `fk_prep:FK_CNT_UID_BID_LI` | `OK` | `DISABLED/NOT VALIDATED` |
| `fk_prep:FK_IF_UID_BID_LI` | `OK` | `DISABLED/NOT VALIDATED` |
| `fk_prep:FK_FR_UID_BID_LI` | `OK` | `ENABLED/NOT VALIDATED` |
| `fk_prep:FK_IS_UID_IID_LI` | `OK` | `ENABLED/NOT VALIDATED` |

## Notes

- FK constraints are intentionally report-only in this phase runner unless write paths are fully migrated.
- Composite unique key `UQ_LIBITEM_UID_ITEM` is added as safe preparation for future composite FKs.
