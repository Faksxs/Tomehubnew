# Phase 6 Release Gate Readiness Report (2026-02-22)

- Generated: `2026-02-22 23:08:26 UTC`
- Verdict: `CONDITIONAL_PASS`
- Scope: Phase 1-5 validation reruns + targeted tests + artifact checks

## Step Results

### `C:\Users\aksoy\AppData\Local\Python\pythoncore-3.14-64\python.exe apps/backend/scripts/run_phase1_checklist.py`
- status: `pass`
- command: `C:\Users\aksoy\AppData\Local\Python\pythoncore-3.14-64\python.exe apps/backend/scripts/run_phase1_checklist.py`
- exit_code: `0`
- stdout_tail:
```text
[OK] Column exists `TOMEHUB_CONTENT.DELETED_AT`
[OK] Column exists `TOMEHUB_CONTENT.DELETION_SOURCE`
[OK] Column exists `TOMEHUB_CONTENT.ROW_VERSION`
[OK] Index exists `IDX_LIBITEM_UID_TYPE`
[OK] Index exists `IDX_LIBITEM_UID_UPD`
[OK] Index exists `IDX_LIBITEM_UID_VIS`
[OK] Index exists `IDX_CHGEVT_STATUS_TS`
[OK] Index exists `IDX_CHGEVT_UID_TS`
[OK] Index exists `IDX_CHGEVT_ITEM_TS`
[OK] Index exists `IDX_INGRUN_STATUS_TS`
[OK] Index exists `IDX_INGEVT_RUN_TS`
[OK] Index exists `IDX_INGEVT_ITEM_TS`
[OK] Index exists `IDX_IDXSTATE_UID_UPD`
[OK] Index exists `IDX_CONT_UID_BOOK_SRC`
[OK] Index exists `IDX_CONT_UID_BOOK_CRT`
[OK] View exists `VW_TOMEHUB_LIBRARY_ITEMS_ENRICHED`
[OK] View exists `VW_TOMEHUB_INGESTION_STATUS_BY_ITEM`
[OK] View exists `VW_TOMEHUB_BOOKS_COMPAT`
[OK] `VW_TOMEHUB_LIBRARY_ITEMS_ENRICHED` count: 268
[OK] `VW_TOMEHUB_INGESTION_STATUS_BY_ITEM` count: 15
[OK] `VW_TOMEHUB_BOOKS_COMPAT` count: 268
[OK] Phase 1C audit report exists: C:/Users/aksoy/Desktop/yeni tomehub/documentation/reports/PHASE1C_TOMEHUB_BOOKS_DML_AUDIT_2026-02-22.md
[OK] Phase 1C audit total parsed: 9
[OK] Phase 1C audit runtime count parsed: 1
[OK] Phase 1C helper `_mirror_book_registry_rows` exists
[OK] Phase 1C runtime additive mirror logic present
[OK] Phase 1D bind-safe exact LIKE present
[OK] Phase 1D legacy exact interpolation removed

[OK] Phase 1 checklist passed.
```

### `C:\Users\aksoy\AppData\Local\Python\pythoncore-3.14-64\python.exe apps/backend/scripts/run_phase2_validation.py`
- status: `pass`
- command: `C:\Users\aksoy\AppData\Local\Python\pythoncore-3.14-64\python.exe apps/backend/scripts/run_phase2_validation.py`
- exit_code: `0`
- stdout_tail:
```text
[OK] LIBRARY_ITEMS rows in scope: 268
[OK] ITEM_INDEX_STATE rows in scope: 268
[OK] TOMEHUB_CONTENT.CONTENT_TYPE null count: 0
[OK] TOMEHUB_CONTENT.INGESTION_TYPE null count: 0
[OK] TOMEHUB_CONTENT.SEARCH_VISIBILITY null count: 0
[OK] TOMEHUB_CONTENT.CONTENT_HASH null count: 0
[OK] TOMEHUB_CONTENT.CONTENT_TYPE allowed values
[OK] TOMEHUB_CONTENT.INGESTION_TYPE allowed values
[OK] TOMEHUB_CONTENT.SEARCH_VISIBILITY allowed values
[OK] TOMEHUB_LIBRARY_ITEMS.SEARCH_VISIBILITY allowed values
[OK] Mapping PDF/PDF_CHUNK -> PDF/BOOK_CHUNK
[OK] Mapping EPUB -> EPUB/BOOK_CHUNK
[OK] Mapping ARTICLE -> WEB/ARTICLE_BODY
[OK] Mapping WEBSITE -> WEB/WEBSITE_BODY
[OK] Mapping HIGHLIGHT -> MANUAL/HIGHLIGHT
[OK] Mapping INSIGHT -> MANUAL/INSIGHT
[OK] Mapping PERSONAL_NOTE -> MANUAL/NOTE
[OK] CONTENT_HASH format check
[OK] CONTENT_HASH sampled recompute: 25 rows
[OK] Content key parity -> missing library items: 0
[OK] Library key parity -> missing content roots: 0
[OK] ITEM_INDEX_STATE missing rows for library items: 0
[OK] ITEM_INDEX_STATE orphan rows: 0
[OK] LIBRARY_ITEMS duplicate (uid,item_id): 0
[OK] VW_TOMEHUB_LIBRARY_ITEMS_ENRICHED count parity: 268
[OK] VW_TOMEHUB_BOOKS_COMPAT count parity: 268
[OK] VW_TOMEHUB_LIBRARY_ITEMS_ENRICHED duplicate keys: 0
[OK] PERSONAL_NOTE content rows visibility policy: 0

[OK] Phase 2 validation passed.
```

### `C:\Users\aksoy\AppData\Local\Python\pythoncore-3.14-64\python.exe apps/backend/scripts/run_phase3_integrity_hardening.py`
- status: `pass`
- command: `C:\Users\aksoy\AppData\Local\Python\pythoncore-3.14-64\python.exe apps/backend/scripts/run_phase3_integrity_hardening.py`
- exit_code: `0`
- stdout_tail:
```text
=== Phase 3 Integrity Hardening (DRY-RUN) ===
[OK] table_exists:TOMEHUB_LIBRARY_ITEMS: True
[OK] table_exists:TOMEHUB_CONTENT: True
[OK] table_exists:TOMEHUB_INGESTED_FILES: True
[OK] table_exists:TOMEHUB_FILE_REPORTS: True
[OK] table_exists:TOMEHUB_ITEM_INDEX_STATE: True
[OK] content_orphans_vs_library_items: 0
[OK] ingested_files_orphans_vs_library_items: 0
[OK] file_reports_orphans_vs_library_items: 0
[OK] item_index_state_orphans_vs_library_items: 0
[OK] library_items_duplicate_uid_item: 0
[OK] library_items_item_id_cross_uid_collision: 0
[OK] library_items_personal_note_visibility: 0
[OK] content_personal_note_visibility: 0
[OK] legacy_books_missing_in_library_items: 0
[OK] fk_prep:FK_CNT_UID_BID_LI: DISABLED/NOT VALIDATED
[OK] fk_prep:FK_IF_UID_BID_LI: DISABLED/NOT VALIDATED
[OK] fk_prep:FK_FR_UID_BID_LI: ENABLED/NOT VALIDATED
[OK] fk_prep:FK_IS_UID_IID_LI: ENABLED/NOT VALIDATED
[INFO] Report written: C:/Users/aksoy/Desktop/yeni tomehub/documentation/reports/PHASE3_INTEGRITY_HARDENING_REPORT_2026-02-22.md

[OK] Phase 3 integrity hardening completed.
```

### `C:\Users\aksoy\AppData\Local\Python\pythoncore-3.14-64\python.exe apps/backend/scripts/run_phase3_highlight_parity_sweep.py`
- status: `pass`
- command: `C:\Users\aksoy\AppData\Local\Python\pythoncore-3.14-64\python.exe apps/backend/scripts/run_phase3_highlight_parity_sweep.py`
- exit_code: `0`
- stdout_tail:
```text
=== Phase 3 Highlight Parity Sweep ===
[INFO] users=1 include_test_users=False execute_fix=False

[RUN] dry-run parity uid=vpq1p0UzcCSLAh1d18WgZZWPBE63
[INFO] uid=vpq1p0UzcCSLAh1d18WgZZWPBE63 mismatches=0 failed=0 fs_total=872 ora_total=872

[INFO] Report written: C:/Users/aksoy/Desktop/yeni tomehub/documentation/reports/PHASE3_HIGHLIGHT_PARITY_SWEEP_2026-02-22.md
[OK] Phase 3 highlight parity sweep completed.
```

### `C:\Users\aksoy\AppData\Local\Python\pythoncore-3.14-64\python.exe apps/backend/scripts/run_phase3_entity_parity_check.py`
- status: `pass`
- command: `C:\Users\aksoy\AppData\Local\Python\pythoncore-3.14-64\python.exe apps/backend/scripts/run_phase3_entity_parity_check.py`
- exit_code: `0`
- stdout_tail:
```text
=== Phase 3 Entity Parity Check ===
[INFO] users=1 include_test_users=False
[RUN] uid=vpq1p0UzcCSLAh1d18WgZZWPBE63
[INFO] status=WARN fs_total=226 ora_total=226 missing=0 extra=45 failed_items=0
[INFO] Report written: C:/Users/aksoy/Desktop/yeni tomehub/documentation/reports/PHASE3_ENTITY_PARITY_CHECK_2026-02-22.md
[OK] Phase 3 entity parity check completed.
```

### `C:\Users\aksoy\AppData\Local\Python\pythoncore-3.14-64\python.exe apps/backend/scripts/run_phase3_quarantine_retry_audit.py`
- status: `pass`
- command: `C:\Users\aksoy\AppData\Local\Python\pythoncore-3.14-64\python.exe apps/backend/scripts/run_phase3_quarantine_retry_audit.py`
- exit_code: `0`
- stdout_tail:
```text
=== Phase 3 Quarantine/Retry Audit ===
[OK] Report written: C:/Users/aksoy/Desktop/yeni tomehub/documentation/reports/PHASE3_QUARANTINE_RETRY_AUDIT_2026-02-22.md
```

### `C:\Users\aksoy\AppData\Local\Python\pythoncore-3.14-64\python.exe -m unittest`
- status: `pass`
- command: `C:\Users\aksoy\AppData\Local\Python\pythoncore-3.14-64\python.exe -m unittest apps/backend/tests/test_search_exact_boundary.py apps/backend/tests/test_search_scope_filters.py apps/backend/tests/test_search_sql_safety.py apps/backend/tests/test_phase4_smoke_endpoints.py`
- exit_code: `0`
- stderr_tail:
```text
{"asctime": "2026-02-23 00:08:25,557", "levelname": "INFO", "name": "tomehub_api", "message": "Importing flow_routes..."}
{"asctime": "2026-02-23 00:08:25,557", "levelname": "INFO", "name": "tomehub_api", "message": "Importing flow_routes..."}
{"asctime": "2026-02-23 00:08:25,578", "levelname": "INFO", "name": "tomehub_api", "message": "Router registered", "route_count": 6}
{"asctime": "2026-02-23 00:08:25,578", "levelname": "INFO", "name": "tomehub_api", "message": "Router registered", "route_count": 6}
...............{"asctime": "2026-02-23 00:08:25,605", "levelname": "WARNING", "name": "middleware.auth_middleware", "message": "DEV_UNSAFE_AUTH_BYPASS enabled: Using firebase_uid from query params"}
.{"asctime": "2026-02-23 00:08:25,609", "levelname": "WARNING", "name": "middleware.auth_middleware", "message": "DEV_UNSAFE_AUTH_BYPASS enabled: Using firebase_uid from query params"}
.{"asctime": "2026-02-23 00:08:25,612", "levelname": "WARNING", "name": "middleware.auth_middleware", "message": "DEV_UNSAFE_AUTH_BYPASS enabled: Using firebase_uid from JSON body"}
{"asctime": "2026-02-23 00:08:25,613", "levelname": "INFO", "name": "tomehub_api", "message": "Using JWT-verified UID: u1"}
{"asctime": "2026-02-23 00:08:25,613", "levelname": "INFO", "name": "tomehub_api", "message": "Using JWT-verified UID: u1"}
{"asctime": "2026-02-23 00:08:25,613", "levelname": "INFO", "name": "tomehub_api", "message": "Search started", "uid": "u1", "question": "test soru"}
{"asctime": "2026-02-23 00:08:25,613", "levelname": "INFO", "name": "tomehub_api", "message": "Search started", "uid": "u1", "question": "test soru"}
{"asctime": "2026-02-23 00:08:25,989", "levelname": "INFO", "name": "tomehub_api", "message": "Search finished successfully", "answer_length": 2, "source_count": 1, "first_source_title": "s1", "first_source_score": 0.9, "metadata": {"status": "ok"}}
{"asctime": "2026-02-23 00:08:25,989", "levelname": "INFO", "name": "tomehub_api", "message": "Search finished successfully", "answer_length": 2, "source_count": 1, "first_source_title": "s1", "first_source_score": 0.9, "metadata": {"status": "ok"}}
.{"asctime": "2026-02-23 00:08:25,993", "levelname": "WARNING", "name": "middleware.auth_middleware", "message": "DEV_UNSAFE_AUTH_BYPASS enabled: Using firebase_uid from JSON body"}
.
----------------------------------------------------------------------
Ran 19 tests in 0.432s

OK
```

### `artifact:PHASE5_QUERY_PROFILING_PRE_INDEX_2026-02-22.md`
- status: `pass`
- notes: exists=True path=C:\Users\aksoy\Desktop\yeni tomehub\documentation\reports\PHASE5_QUERY_PROFILING_PRE_INDEX_2026-02-22.md

### `artifact:PHASE5_QUERY_PROFILING_POST_INDEX_2026-02-22.md`
- status: `pass`
- notes: exists=True path=C:\Users\aksoy\Desktop\yeni tomehub\documentation\reports\PHASE5_QUERY_PROFILING_POST_INDEX_2026-02-22.md

### `artifact:PHASE5_QUERY_PROFILING_POST_STATS_2026-02-22.md`
- status: `pass`
- notes: exists=True path=C:\Users\aksoy\Desktop\yeni tomehub\documentation\reports\PHASE5_QUERY_PROFILING_POST_STATS_2026-02-22.md

### `artifact:PHASE5_DBMS_STATS_REFRESH_2026-02-22.md`
- status: `pass`
- notes: exists=True path=C:\Users\aksoy\Desktop\yeni tomehub\documentation\reports\PHASE5_DBMS_STATS_REFRESH_2026-02-22.md

### `artifact:PHASE5_QUERY_PLAN_SNAPSHOT_2026-02-22.md`
- status: `pass`
- notes: exists=True path=C:\Users\aksoy\Desktop\yeni tomehub\documentation\reports\PHASE5_QUERY_PLAN_SNAPSHOT_2026-02-22.md

### `artifact:PHASE5_SEARCH_LOGS_PARTITION_RUNBOOK_2026-02-22.md`
- status: `pass`
- notes: exists=True path=C:\Users\aksoy\Desktop\yeni tomehub\documentation\reports\PHASE5_SEARCH_LOGS_PARTITION_RUNBOOK_2026-02-22.md

### `artifact:PHASE6_CUTOVER_ROLLBACK_DRILL_2026-02-22.md`
- status: `pass`
- notes: exists=True path=C:\Users\aksoy\Desktop\yeni tomehub\documentation\reports\PHASE6_CUTOVER_ROLLBACK_DRILL_2026-02-22.md

### `artifact:PHASE6_LIVE_SMOKE_REAL_API_2026-02-22.md`
- status: `pass`
- notes: exists=True path=C:\Users\aksoy\Desktop\yeni tomehub\documentation\reports\PHASE6_LIVE_SMOKE_REAL_API_2026-02-22.md

### `artifact:PHASE6_READ_WRITE_CUTOVER_PLAN_2026-02-22.md`
- status: `pass`
- notes: exists=True path=C:\Users\aksoy\Desktop\yeni tomehub\documentation\reports\PHASE6_READ_WRITE_CUTOVER_PLAN_2026-02-22.md

### `artifact:PHASE6_FIREBASE_WRITE_DISABLE_CHECKLIST_2026-02-22.md`
- status: `pass`
- notes: exists=True path=C:\Users\aksoy\Desktop\yeni tomehub\documentation\reports\PHASE6_FIREBASE_WRITE_DISABLE_CHECKLIST_2026-02-22.md

### `manual:rollback_drill_execution`
- status: `warn`
- notes: Rollback runbooks exist, but full cutover rollback drill execution not performed in this runner.

### `manual:phased_read_cutover_finalize`
- status: `warn`
- notes: Read cutover finalization is operational step; not executed by validation runner.

### `manual:write_path_finalize_oracle_first`
- status: `warn`
- notes: Write path finalization/Firebase write disable are not executed automatically.

## Summary

- pass: `17`
- warn: `3`
- fail: `0`

## Cutover Guidance

- Technical validation checks passed, but operational/manual cutover steps remain.
- Complete rollback drill + live API smoke + final cutover approvals before Firebase write disable.
