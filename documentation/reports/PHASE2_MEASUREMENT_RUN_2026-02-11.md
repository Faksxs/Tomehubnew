# Phase-2 Freshness Measurement Run (2026-02-11)

## 1) Run Context

- UID: `vpq1p0UzcCSLAh1d18WgZZWPBE63`
- Probe script: `apps/backend/scripts/phase2_freshness_probe.py`
- Endpoint: `GET /api/books/{book_id}/ingestion-status`

## 2) Initial Probe Results (Before Graph Fixes)

1. `1764982122036`
   - report: `documentation/reports/phase2_freshness_probe_20260211_022832.json`
   - status: `COMPLETED`
   - freshness: `vector_ready`
   - total/embedded/graph_linked: `192 / 192 / 0`
   - timed_out: `true`
2. `bb722b93-d132-4850-8b97-971548cc1cde`
   - report: `documentation/reports/phase2_freshness_probe_20260211_022917.json`
   - status: `COMPLETED`
   - freshness: `vector_ready`
   - total/embedded/graph_linked: `7 / 7 / 0`
   - timed_out: `true`
3. `62558300-7ec4-4fbb-b176-bc38dc1ba168`
   - report: `documentation/reports/phase2_freshness_probe_20260211_023004.json`
   - status: `COMPLETED`
   - freshness: `vector_ready`
   - total/embedded/graph_linked: `13 / 13 / 0`
   - timed_out: `true`

## 3) Root-Cause Findings During Run

1. Prompt formatting bug in Graph extraction:
   - `apps/backend/prompts/graph_prompts.py`
   - unescaped `{}` caused `'"name"'` runtime errors.
2. Console encoding bug in Graph extraction debug output:
   - `apps/backend/services/graph_service.py`
   - debug print could fail on Windows encoding.
3. DB bind mismatch and type issues in `save_to_graph`:
   - `apps/backend/services/graph_service.py`
   - bind placeholder mismatch and CLOB compatibility issue in MERGE.

## 4) Applied Fixes

1. Escaped JSON braces in `GRAPH_EXTRACTION_PROMPT`.
2. Replaced risky debug print with safe logger preview.
3. Fixed MERGE bind placeholder usage and CLOB casting (`TO_CLOB`).
4. Made `save_to_graph` return success/fail boolean.
5. Updated enrichment metrics to count only successful graph saves:
   - `apps/backend/services/index_freshness_service.py`

## 5) Verification After Fixes

1. Manual enrichment run:
   - command path: `apps/backend/services/index_freshness_service.py` via CLI import
   - book: `1764982122036`
   - result: `linked_chunks=1`
   - post state: `fully_ready`
2. Probe after fix:
   - report: `documentation/reports/phase2_freshness_probe_20260211_023429.json`
   - result: immediate `fully_ready`
3. API check:
   - `GET /api/books/1764982122036/ingestion-status?...`
   - `index_freshness_state=fully_ready`

## 6) Decision

- Faz 2 ölçüm turu için ana hedef (freshness state görünürlüğü + graph eventual readiness doğrulaması) **karşılandı**.
- Ancak kalite/stabilite için ek tur gerekli:
  1. En az 5 kitapta aynı ölçüm
  2. `graph_coverage_ratio` alt sınırı belirleme
  3. 429 oranı için rate/backoff planı
