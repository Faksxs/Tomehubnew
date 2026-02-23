# Phase 1C TOMEHUB_BOOKS DML Callsite Audit (2026-02-22)

## Summary

- Total DML callsites: `9`
- Runtime callsites: `1`
- Maintenance callsites: `6`
- Script callsites: `1`
- Test callsites: `0`
- Other callsites: `1`

### By DML Type

- `MERGE`: `3`
- `INSERT`: `3`
- `UPDATE`: `3`
- `DELETE`: `0`

## Migration Guidance (Phase 1C Output)

- Runtime write-paths must be moved off direct `TOMEHUB_BOOKS` DML before any view-based canonical cutover.
- `INSTEAD OF` trigger remains fallback only; default path is backend write-path migration.
- Maintenance/scripts should be reviewed and patched only if they are still used operationally.

## Findings

| Category | DML | File | Line | Recommended Action |
|---|---|---|---:|---|
| `maintenance` | `INSERT` | `apps/backend/fix_firestore_to_oracle_sync.py` | 44 | Review for one-off usage; patch only if still operationally used in migration/cutover |
| `maintenance` | `INSERT` | `apps/backend/fix_ghost_klasik.py` | 36 | Review for one-off usage; patch only if still operationally used in migration/cutover |
| `maintenance` | `UPDATE` | `apps/backend/fix_uid_migration.py` | 24 | Review for one-off usage; patch only if still operationally used in migration/cutover |
| `maintenance` | `UPDATE` | `apps/backend/revert_uid_migration.py` | 23 | Review for one-off usage; patch only if still operationally used in migration/cutover |
| `maintenance` | `UPDATE` | `apps/backend/revert_uid_migration.py` | 26 | Review for one-off usage; patch only if still operationally used in migration/cutover |
| `maintenance` | `INSERT` | `apps/backend/sync_klasik_to_oracle.py` | 32 | Review for one-off usage; patch only if still operationally used in migration/cutover |
| `other` | `MERGE` | `apps/backend/infrastructure/migrations/repair_schema_safe.sql` | 23 | Manual review |
| `runtime` | `MERGE` | `apps/backend/services/ingestion_service.py` | 192 | Migrate to TOMEHUB_LIBRARY_ITEMS write path (or central abstraction) before view-based cutover |
| `script` | `MERGE` | `apps/backend/scripts/run_safe_migration_v2.py` | 37 | Review for one-off usage; patch only if still operationally used in migration/cutover |

## Notes

- This audit is regex-based and intended for migration routing prep.
- Dynamic SQL builders should still be reviewed manually during Phase 1C implementation.
