# Phase 5 SEARCH_LOGS Partition Runbook (Draft, Pre-Implementation)

**Date:** 2026-02-22  
**Scope:** `TOMEHUB_SEARCH_LOGS` monthly partition migration and retention/archival preparation  
**Status:** Draft runbook (implementation not applied)

---

## 1. Goal

Move `TOMEHUB_SEARCH_LOGS` to monthly range/interval partitioning on the canonical time column (`TIMESTAMP`) with:

- safer retention operations (partition maintenance instead of row-by-row delete)
- predictable performance as volume grows
- archive path for >90 day data

This runbook is prepared after Phase 5 baseline profiling and index audit.

---

## 2. Preconditions

Must be true before execution:

1. Phase 4 search logging writes are stable (no schema churn on `TOMEHUB_SEARCH_LOGS`)
2. Phase 5 baseline profiling is captured
3. `TIMESTAMP` confirmed as canonical time column
4. Rollback plan and maintenance window approved
5. Application behavior verified against current `IDX_SEARCH_LOGS_TIME`

Recommended:

- Refresh stats before migration (`DBMS_STATS` on `TOMEHUB_SEARCH_LOGS`)
- Capture row count and day distribution snapshot
- Confirm no hardcoded `ROWID` assumptions in cleanup jobs

---

## 3. Target Design (Approved Direction)

### 3.1 Partitioning Strategy

- `PARTITION BY RANGE ("TIMESTAMP")`
- `INTERVAL (NUMTOYMINTERVAL(1,'MONTH'))`
- Initial seed partition covering historical minimum date

### 3.2 Retention / Archive Policy

- Hot retention in primary table: last `90` days
- Older partitions:
  - move to archive table (`TOMEHUB_SEARCH_LOGS_ARCHIVE`) or
  - export/cold storage depending ops decision

### 3.3 Index Strategy

- Keep time-based access path (`TIMESTAMP`) as local index strategy on partitioned table
- Re-evaluate additional indexes after real workload patterns (do not over-index logs)

---

## 4. Migration Approaches (Choose One)

## A. CTAS + Rename Cutover (Preferred for simplicity)

1. Create partitioned target table with same columns
2. Create required local indexes
3. Backfill data (`INSERT /*+ APPEND */ ... SELECT ...`)
4. Validate row counts and spot-checks
5. Brief write freeze / app maintenance window
6. Swap names (rename old -> backup, new -> canonical)
7. Recreate grants/synonyms/triggers if any
8. Post-cutover smoke + stats gather

Pros:

- clean structure
- predictable rollback (rename back)

Cons:

- requires controlled cutover window
- duplicate storage during migration

## B. Online Redefinition (`DBMS_REDEFINITION`)

Use only if strict uptime requirement justifies complexity.

Pros:

- lower downtime

Cons:

- more operational complexity
- harder rollback/debug

Current recommendation: **Approach A (CTAS + Rename)** for this project phase.

---

## 5. Execution Checklist (Detailed)

## 5.1 Preflight

1. Capture counts
   - total rows
   - min/max `TIMESTAMP`
   - per-day distribution (last 30/90 days)
2. Capture DDL
   - table DDL
   - indexes
   - grants
   - constraints
3. Confirm application writes/reads still use expected columns
4. Disable/stop retention jobs touching `TOMEHUB_SEARCH_LOGS`

## 5.2 Build Partitioned Target

1. Create `TOMEHUB_SEARCH_LOGS_PNEW` (same columns)
2. Define interval monthly partitioning on `TIMESTAMP`
3. Create required indexes (local where applicable)
4. Apply grants

## 5.3 Backfill

1. Bulk insert historical rows into `TOMEHUB_SEARCH_LOGS_PNEW`
2. Commit in controlled batches if needed
3. Gather stats on new table
4. Validate:
   - total count
   - min/max timestamp
   - sample row equality by ID / query text / timestamp

## 5.4 Cutover

1. Pause app writes (maintenance mode or short freeze)
2. Backfill delta rows (if any)
3. Rename current table -> backup (e.g. `TOMEHUB_SEARCH_LOGS_BAK_20260222`)
4. Rename partitioned table -> `TOMEHUB_SEARCH_LOGS`
5. Recreate/verify indexes, grants, synonyms
6. Resume app writes

## 5.5 Post-Cutover Validation

1. Smoke insert from app/search path
2. Query recent logs by time window
3. Run Phase 5 profiling subset (`search_logs_recent_window`)
4. Confirm partition pruning via `EXPLAIN PLAN`
5. Gather final stats

---

## 6. Retention and Archive Operations

### 6.1 Monthly Retention Job (Partition-Aware)

Instead of:

- `DELETE FROM TOMEHUB_SEARCH_LOGS WHERE TIMESTAMP < ...`

Use:

- identify partitions older than retention window
- archive partition data (if required)
- `ALTER TABLE ... DROP PARTITION ...` or `TRUNCATE PARTITION ...`

### 6.2 Archive Validation

For each archived partition:

1. Row count before move
2. Row count after move in archive
3. Checksum/sample validation
4. Audit log entry

---

## 7. Rollback Plan

If cutover fails after rename:

1. Pause writes
2. Rename current `TOMEHUB_SEARCH_LOGS` (partitioned) to failed name
3. Rename backup table back to `TOMEHUB_SEARCH_LOGS`
4. Re-verify grants/indexes
5. Resume writes

If failure occurs before cutover:

- drop `TOMEHUB_SEARCH_LOGS_PNEW`
- keep current table unchanged

---

## 8. Risks and Mitigations

1. **Lock contention during cutover**
- Mitigation: short maintenance window + prebuilt target table

2. **Missed grants/synonyms**
- Mitigation: pre-capture DDL and explicit post-cutover checklist

3. **Stats not gathered after swap**
- Mitigation: mandatory post-cutover `DBMS_STATS`

4. **Retention job still doing row deletes**
- Mitigation: update job before enabling partition lifecycle ops

---

## 9. Not Yet Executed (Explicit)

This runbook does **not** apply partitioning yet.

Pending before implementation:

1. Final DDL draft for partitioned `TOMEHUB_SEARCH_LOGS`
2. Cutover window decision
3. Post-cutover smoke checklist approval

