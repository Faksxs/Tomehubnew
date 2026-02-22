# Oracle Migration v2 Implementation (2026-02-21)

This document records the implemented parts of the Oracle migration v2 plan.

## Implemented

1. Schema Validation + Normalization Gateway
- Added strict normalization/validation models for Firestore payloads before Oracle writes.
- File: `apps/backend/models/firestore_sync_models.py`
- Covers:
  - `author` string/list normalization
  - timestamp normalization
  - tag/highlight dedupe and shape normalization
  - canonical item type mapping
  - entity hash generation for idempotency keying

2. Firestore -> Oracle Backfill Safety Layer
- Added async sync service with:
  - dry-run support (default safe mode)
  - idempotency key (`uid + book_id + entity_hash`)
  - quarantine log (`logs/firestore_sync_quarantine.jsonl`)
  - embedding RPM limiter
  - embedding cost estimate
  - in-process status tracking
- File: `apps/backend/services/firestore_sync_service.py`

3. Sync Script Hardening
- Replaced legacy script behavior to default dry-run.
- Explicit execute mode required (`--execute`).
- Added configurable `--max-items`, `--embedding-rpm-cap`, `--embedding-unit-cost-usd`.
- File: `apps/backend/scripts/sync_missing_items_to_oracle.py`

4. Monitoring Metrics for Embedding Backfill
- Added:
  - `tomehub_embedding_backfill_total_calls`
  - `tomehub_embedding_backfill_queue_depth`
  - `tomehub_embedding_backfill_cost_estimate_usd`
- File: `apps/backend/services/monitoring.py`

5. Admin API for Backfill Start/Status
- Added endpoints:
  - `POST /api/admin/firestore-sync/start`
  - `GET /api/admin/firestore-sync/status`
- File: `apps/backend/app.py`

6. Realtime UX Protection (Polling Path)
- Added coarse realtime polling endpoint:
  - `GET /api/realtime/poll`
  - event types: `book.updated`, `highlight.synced`, `note.synced`
- Added frontend client helper:
  - `pollRealtimeEvents(...)`
- Files:
  - `apps/backend/app.py`
  - `apps/frontend/src/services/backendApiService.ts`

7. Memory Layer Hardening (Health Visibility)
- Added Oracle memory-layer health endpoint:
  - `GET /api/health/memory-layer`
  - returns session/message totals + stale sessions over retention window
- File: `apps/backend/app.py`

## Not Implemented Yet

1. SSE/WebSocket push channel for realtime updates (polling exists now).
2. Full projection-cutover automation and KPI-based auto-disable.
3. Dedicated quarantine replay workflow.
4. Read-only cutover runbook automation.

## Validation Run

1. Python compile check:
- `python -m py_compile` passed for changed backend modules.

2. Frontend build:
- `npm --prefix apps/frontend run build` passed.

## Operational Notes

1. Production safety:
- Keep `dry_run=true` for first API runs.
- Promote to execute only after parity checks.

2. Quarantine review:
- Inspect `logs/firestore_sync_quarantine.jsonl` after each run.

3. Realtime client:
- Polling endpoint is ready; UI wiring can be added incrementally.
