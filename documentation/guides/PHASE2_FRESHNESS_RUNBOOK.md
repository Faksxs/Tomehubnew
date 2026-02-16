# Phase-2 Freshness / Consistency Runbook

## 1. Goal

Validate and operationalize:

1. `index_freshness_state` visibility (`not_ready|vector_ready|graph_ready|fully_ready`)
2. Ingest/sync sonrası graph enrichment tetikleme davranisi
3. Kullaniciya "hemen aradiginda bulamama" riskinin olculebilir hale gelmesi

## 2. Implemented Scope

1. New service: `apps/backend/services/index_freshness_service.py`
2. Config flags:
   1. `GRAPH_ENRICH_ON_INGEST`
   2. `GRAPH_ENRICH_MAX_ITEMS`
   3. `GRAPH_ENRICH_TIMEOUT_SEC`
3. API response enrichment:
   1. `GET /api/books/{book_id}/ingestion-status` now returns `index_freshness_state` + `index_freshness`
   2. `POST /api/add-item`, `POST /api/books/{book_id}/sync-highlights`, `POST /api/notes/{book_id}/sync-personal-note` now return freshness metadata
4. Automatic graph enrichment trigger:
   1. PDF ingest completion
   2. Add item
   3. Highlight sync
   4. Personal note sync

## 3. Test Prerequisites

1. Backend up and reachable (default: `http://127.0.0.1:5001`)
2. Test user `firebase_uid`
3. Test `book_id`
4. Valid `GEMINI_API_KEY` (graph extraction for enrichment path)

## 4. Quick Manual Checks

1. PDF ingest baslat:
```bash
curl -X POST http://127.0.0.1:5001/api/ingest ...
```
2. Durumu izle:
```bash
curl "http://127.0.0.1:5001/api/books/<book_id>/ingestion-status?firebase_uid=<uid>"
```
3. Beklenen progression:
   1. `status=PROCESSING`
   2. `status=COMPLETED` + `index_freshness_state=vector_ready` (veya direkt `fully_ready`)
   3. Bir sure sonra `index_freshness_state=fully_ready`

## 5. Automated Probe

Run:
```bash
cd apps/backend
python scripts/phase2_freshness_probe.py --uid <uid> --book-id <book_id> --base-url http://127.0.0.1:5001
```

Outputs:

1. `documentation/reports/phase2_freshness_probe_<timestamp>.json`
2. `documentation/reports/phase2_freshness_probe_<timestamp>.md`

Key metrics:

1. `first_seen_sec.vector_ready_sec`
2. `first_seen_sec.graph_ready_sec`
3. `first_seen_sec.fully_ready_sec`
4. `timed_out`

## 6. Suggested Initial Thresholds

1. Vector readiness target: `<= 10s` after sync completion, `<= 120s` after PDF ingest completion
2. Full readiness target: `<= 300s` (depends on `GRAPH_ENRICH_MAX_ITEMS` and model latency)
3. Timeout alarm: probe timeout without `fully_ready`

## 7. Go / No-Go Gates

1. Gate A (Freshness visibility):
   1. `index_freshness_state` appears in all target endpoints
2. Gate B (Consistency):
   1. Vector readiness is consistently observed
3. Gate C (Graph eventual consistency):
   1. Graph-linked chunk count increases over time when pending chunks exist
4. Gate D (Stability):
   1. No ingestion regressions / no API errors introduced

## 8. Rollback Lever

If graph enrichment causes cost/latency pressure:

1. Set `GRAPH_ENRICH_ON_INGEST=false`
2. Keep freshness telemetry active
3. Continue graph build via controlled batch jobs
