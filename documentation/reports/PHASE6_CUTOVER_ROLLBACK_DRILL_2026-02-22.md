# Phase 6 Cutover + Rollback Drill Report (Dry-Run) (2026-02-22)

- Generated: `2026-02-22 23:07:15 UTC`
- Verdict: `PASS`
- Mode: `DRY-RUN / REHEARSAL` (no destructive DB changes)

## Checklist Results

- `db_table:TOMEHUB_LIBRARY_ITEMS`: `pass` - required for cutover
- `db_table:TOMEHUB_CONTENT`: `pass` - required for cutover
- `db_table:TOMEHUB_ITEM_INDEX_STATE`: `pass` - required for cutover
- `db_table:TOMEHUB_SEARCH_LOGS`: `pass` - required for cutover
- `db_view:VW_TOMEHUB_LIBRARY_ITEMS_ENRICHED`: `pass` - compatibility rollout surface
- `db_view:VW_TOMEHUB_BOOKS_COMPAT`: `pass` - compatibility rollout surface
- `db_view:VW_TOMEHUB_INGESTION_STATUS_BY_ITEM`: `pass` - compatibility rollout surface
- `integrity:content_orphans_vs_library_items`: `pass` - count=0
- `integrity:library_items_duplicate_uid_item`: `pass` - count=0
- `ops:outbox_table_present`: `pass` - rows=4
- `artifact:PHASE3_ENTITY_PARITY_CHECK_2026-02-22.md`: `pass` - exists=True path=C:\Users\aksoy\Desktop\yeni tomehub\documentation\reports\PHASE3_ENTITY_PARITY_CHECK_2026-02-22.md
- `artifact:PHASE3_HIGHLIGHT_PARITY_SWEEP_2026-02-22.md`: `pass` - exists=True path=C:\Users\aksoy\Desktop\yeni tomehub\documentation\reports\PHASE3_HIGHLIGHT_PARITY_SWEEP_2026-02-22.md
- `artifact:PHASE5_QUERY_PROFILING_POST_STATS_2026-02-22.md`: `pass` - exists=True path=C:\Users\aksoy\Desktop\yeni tomehub\documentation\reports\PHASE5_QUERY_PROFILING_POST_STATS_2026-02-22.md
- `artifact:PHASE5_QUERY_PLAN_SNAPSHOT_2026-02-22.md`: `pass` - exists=True path=C:\Users\aksoy\Desktop\yeni tomehub\documentation\reports\PHASE5_QUERY_PLAN_SNAPSHOT_2026-02-22.md
- `artifact:PHASE5_SEARCH_LOGS_PARTITION_RUNBOOK_2026-02-22.md`: `pass` - exists=True path=C:\Users\aksoy\Desktop\yeni tomehub\documentation\reports\PHASE5_SEARCH_LOGS_PARTITION_RUNBOOK_2026-02-22.md
- `manual_rehearsed:read_cutover_toggle_enable (compat views -> canonical reads)`: `warn` - Runbook/checklist prepared; execution deferred
- `manual_rehearsed:write_path_finalize (Oracle-first authoritative writes)`: `warn` - Runbook/checklist prepared; execution deferred
- `manual_rehearsed:firebase_write_disable`: `warn` - Runbook/checklist prepared; execution deferred
- `manual_rehearsed:rollback_rename_or_featureflag_revert`: `warn` - Runbook/checklist prepared; execution deferred

## Cutover Sequence (Rehearsed)

1. Confirm latest release gate report is at least CONDITIONAL_PASS.
2. Enable read cutover to canonical/view-first path in approved order.
3. Run live smoke against /api/search, /api/smart-search, /api/realtime/poll, ingestion-status.
4. Finalize Oracle-first write path and monitor outbox + ingestion health.
5. Disable Firebase writes only after monitoring window is green.
6. If regression detected, execute rollback checklist (toggle/rename reversion) immediately.

## Rollback Sequence (Rehearsed)

1. Pause/disable new write path toggle.
2. Restore previous read path toggle.
3. Verify core endpoints and search parity smoke.
4. Keep Oracle data; do not destructive-reset during rollback.
5. Document incident and diff before reattempt.

