# Phase 3 Quarantine/Retry Audit

- **Generated (UTC):** 2026-02-22 23:08:23Z

## Ingestion Run Status Counts

| Status | Count |
|---|---:|
| `COMPLETED` | 2 |
| `FAILED` | 1 |

## Open or Incomplete Runs (Top 50)

| RUN_ID | RUN_TYPE | STATUS | UID | STARTED_AT | FINISHED_AT | TOTAL | PROCESSED | SUCCESS | FAILED | QUARANTINE |
|---|---|---|---|---|---|---:|---:|---:|---:|---:|
| `phase2_backfill_20260222T022243Z_d4a02d75` | `PHASE2_BACKFILL` | `FAILED` | `None` | `2026-02-22 03:22:46.784936` | `2026-02-22 03:23:03.002294` | 0 | 0 | 0 | 1 | 0 |

## Runs With Failures/Quarantine (Top 100)

| RUN_ID | RUN_TYPE | STATUS | UID | QUARANTINE | FAILED | STARTED_AT | FINISHED_AT |
|---|---|---|---|---:|---:|---|---|
| `phase2_backfill_20260222T022243Z_d4a02d75` | `PHASE2_BACKFILL` | `FAILED` | `None` | 0 | 1 | `2026-02-22 03:22:46.784936` | `2026-02-22 03:23:03.002294` |

## Ingestion Event Status Counts

| Status | Count |
|---|---:|

## Retry Candidate Buckets

| EVENT_TYPE | ERROR_CODE | Count |
|---|---|---:|

## Recent Failed/Quarantined Events (Top 100)

| RUN_ID | UID | ITEM_ID | ENTITY_TYPE | EVENT_TYPE | STATUS | ERROR_CODE | CREATED_AT |
|---|---|---|---|---|---|---|---|

## Standardization Notes

- Treat `FAILED`, `ERROR`, `QUARANTINED` event statuses as retry candidates unless `ERROR_CODE` is classified terminal.
- Future retry worker should be idempotent and keyed by `(RUN_ID, ITEM_ID, EVENT_TYPE)` or explicit event idempotency key.
- Quarantine decisions should persist `ERROR_CODE` + normalized reason in `DETAILS_JSON` for deterministic retry routing.
