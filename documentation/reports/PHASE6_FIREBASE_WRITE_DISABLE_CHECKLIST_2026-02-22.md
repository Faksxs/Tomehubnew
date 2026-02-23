# Phase 6 Firebase Write-Disable Checklist (2026-02-22)

**Status:** Final operational checklist (manual execution)  
**Purpose:** Safely disable Firebase writes after Oracle-first cutover is stable

---

## 1. Go/No-Go Criteria

All must be true:

- [ ] Phase 6 release gate report is at least `CONDITIONAL_PASS`
- [ ] Phase 6 live smoke (real API + DB) passed
- [ ] Read cutover is active and stable
- [ ] Oracle-first write path is active and stable
- [ ] No unresolved parity mismatches (`missing_in_oracle = 0`)
- [ ] Rollback owner and on-call available
- [ ] Monitoring dashboard open and staffed

---

## 2. Pre-Disable Snapshot (Record)

Record before change:

- [ ] current deploy SHA
- [ ] config/flag values (read path, write path, Firebase writes)
- [ ] timestamp (UTC)
- [ ] error rate baseline
- [ ] `/api/search` p95 baseline
- [ ] `/api/smart-search` p95 baseline

---

## 3. Disable Procedure

1. [ ] Enable/confirm Oracle-first write path
2. [ ] Disable Firebase writes (feature flag/config)
3. [ ] Record exact cutover timestamp
4. [ ] Announce change in ops channel

---

## 4. Immediate Validation (0-10 min)

- [ ] `/api/search` smoke request passes
- [ ] `/api/smart-search` smoke request passes
- [ ] `/api/realtime/poll` returns outbox payload
- [ ] ingestion-status endpoint returns expected metadata
- [ ] New write action persists to Oracle
- [ ] `TOMEHUB_CHANGE_EVENTS` receives event

---

## 5. Short Observation Window (10-60 min)

- [ ] error rate stable
- [ ] p95 latency within acceptable range
- [ ] no auth/permission regression reports
- [ ] no ingestion consistency regression
- [ ] no new orphan rows in integrity spot check

---

## 6. Rollback Trigger Conditions

Rollback if any occurs:

- [ ] sustained 5xx increase
- [ ] data write loss / inconsistency
- [ ] ingestion status regressions
- [ ] search parity regression on known checks
- [ ] critical user-facing failures

---

## 7. Rollback Steps (If Triggered)

1. [ ] Re-enable Firebase writes
2. [ ] Revert write-path toggle
3. [ ] Revert read-path toggle if needed
4. [ ] Run live smoke + key parity checks
5. [ ] Document incident and timestamps

---

## 8. Final Sign-Off

- [ ] Firebase writes remain disabled after observation window
- [ ] Ops sign-off recorded
- [ ] Engineering sign-off recorded
- [ ] Post-cutover report attached

