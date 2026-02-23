# Phase 6 Read/Write Cutover Plan (2026-02-22)

**Status:** Operational plan (not executed by code)  
**Scope:** Final transition to Oracle-first canonical reads/writes with rollback safety

---

## 1. Objective

Complete the final rollout steps after Phases 1-5 technical implementation:

- canonical read path finalization
- Oracle-first write path finalization
- controlled Firebase write disable
- fast rollback path if regression appears

---

## 2. Preconditions (Must Be Green)

1. `PHASE6_RELEASE_GATE_READINESS_2026-02-22.md` = `CONDITIONAL_PASS` or `PASS`
2. Phase 3 parity checks:
   - `missing_in_oracle = 0`
   - highlight/insight parity mismatch = 0
3. Phase 5 profiling + plan snapshot available
4. Phase 6 live smoke (real API+DB) report available
5. On-call / rollback owner assigned

---

## 3. Read Cutover Sequence

## 3.1 Scope

Target read surfaces:

- `/api/smart-search`
- `/api/search`
- `/api/books/{id}/ingestion-status`
- realtime poll (`outbox-first` already enabled, verify in monitoring)

## 3.2 Steps

1. Confirm current deploy SHA and DB schema version
2. Enable canonical/view-first read path according to existing feature toggles/config
3. Run smoke checks immediately:
   - `/api/search`
   - `/api/smart-search`
   - `/api/realtime/poll`
   - ingestion-status
4. Monitor 15-30 min:
   - error rate
   - p95 latency
   - search result parity spot checks (`bilhassa` etc.)
5. If stable, proceed to write cutover

## 3.3 Rollback Trigger (Read Path)

Rollback immediately if any of these occur:

- sustained 5xx increase
- ingestion-status false positives/negatives
- search direct-match parity regression
- outbox poll payload regressions

---

## 4. Write Cutover Sequence (Oracle-First)

## 4.1 Scope

Finalize Oracle-first writes for:

- item metadata updates
- ingestion status updates
- highlight/note sync writes
- outbox event emission confirmation

## 4.2 Steps

1. Enable Oracle-first authoritative write flag/path
2. Verify write-path telemetry:
   - `TOMEHUB_CHANGE_EVENTS` growth
   - ingestion rows updates
   - no new orphan rows
3. Spot-check a test write in app:
   - item update reflected in Oracle
   - related endpoint reads consistent
4. Keep Firebase writes enabled during observation window (shadow mode if applicable)

---

## 5. Firebase Write Disable (Final Step)

Disable only after:

1. Read cutover stable
2. Oracle-first writes stable
3. Rollback owner confirms readiness
4. Monitoring dashboards green

Then:

1. Disable Firebase write path (feature flag / config)
2. Announce cutover timestamp
3. Monitor for at least one business cycle

---

## 6. Rollback Plan (Operational)

If regression after write cutover or Firebase write disable:

1. Re-enable previous write path / Firebase writes
2. Revert read path toggle
3. Run Phase 6 live smoke + parity spot checks
4. Preserve Oracle data (no destructive rollback)
5. Document drift introduced during rollback window

---

## 7. Monitoring Checklist During Cutover

- `/api/search` 5xx, p95
- `/api/smart-search` lexical_total sanity for known terms
- `/api/realtime/poll` source=`outbox` ratio
- ingestion-status error rate / false-positive complaints
- `TOMEHUB_CHANGE_EVENTS` insert rate
- orphan checks (`content vs library_items`)

