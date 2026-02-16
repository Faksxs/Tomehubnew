# Phase-2 Freshness / Consistency Implementation Report
**Tarih:** 2026-02-11  
**Dil:** Turkce (ASCII)  
**Kapsam:** Graph freshness gorunurlugu + event-driven enrichment tetikleme

## 1. Ozet

Bu fazda iki kritik iyilestirme uygulandi:

1. `index_freshness_state` API seviyesinde gorunur hale getirildi.
2. Ingest/sync sonrasinda graph enrichment non-blocking olarak tetiklenir hale getirildi.

Temel hedef: kullanicinin "hemen aramada bulamama" riskini olculebilir ve yonetilebilir yapmak.

## 2. Uygulanan Degisiklikler

1. Yeni servis:
   - `apps/backend/services/index_freshness_service.py`
   - Saglananlar:
     - `get_index_freshness_state(book_id, firebase_uid)`
     - `enrich_graph_for_book(firebase_uid, book_id, max_items, timeout_sec)`
     - `maybe_trigger_graph_enrichment_async(firebase_uid, book_id, reason)`

2. Konfigurasyon:
   - `apps/backend/config.py`
     - `GRAPH_ENRICH_ON_INGEST` (default: `true`)
     - `GRAPH_ENRICH_MAX_ITEMS` (default: `8`)
     - `GRAPH_ENRICH_TIMEOUT_SEC` (default: `25`)
   - `apps/backend/.env.example` guncellendi.

3. Endpoint davranislari:
   - `GET /api/books/{book_id}/ingestion-status`
     - Yeni alanlar:
       - `index_freshness_state`
       - `index_freshness` (detayli sayac/coverage)
   - `POST /api/add-item`
   - `POST /api/books/{book_id}/sync-highlights`
   - `POST /api/notes/{book_id}/sync-personal-note`
     - Basari donuslerine freshness metadata eklendi.
     - Basari sonrasinda graph enrichment async trigger eklendi.
   - PDF ingest background success noktasinda graph enrichment async trigger eklendi.

4. Olcum araci:
   - `apps/backend/scripts/phase2_freshness_probe.py`
   - Polling ile status/freshness transition suresini raporlar.

5. Calistirma kilavuzu:
   - `documentation/guides/PHASE2_FRESHNESS_RUNBOOK.md`

## 3. Freshness State Mantigi

State uretimi:

1. `not_ready`: vector ve graph hic hazir degil
2. `vector_ready`: vector var, graph yok
3. `graph_ready`: graph var, vector yok (teorik)
4. `fully_ready`: vector + graph hazir

Kullanilan temel sayaclar:

1. `total_chunks`
2. `embedded_chunks`
3. `graph_linked_chunks`
4. `vector_coverage_ratio`
5. `graph_coverage_ratio`

## 4. Risk / Trade-off

1. Graph enrichment LLM cagrisi yaptigi icin maliyet artirabilir.
2. Bu nedenle guardrail eklendi:
   - max item limiti
   - timeout limiti
   - async ve best-effort calisma
3. Acil rollback: `GRAPH_ENRICH_ON_INGEST=false`

## 5. Dogrulama Plani

1. API smoke:
   - `ingestion-status` response'unda freshness alanlari var mi
2. Freshness progression:
   - `PROCESSING -> COMPLETED`
   - `not_ready/vector_ready -> fully_ready`
3. Probe script:
   - `phase2_freshness_probe.py` ile first-seen metrikleri

## 6. Sonuc

Bu faz ile consistency problemi "gizli sistem davranisi" olmaktan cikti; API seviyesinde izlenebilir hale geldi.
Graph enrichment halen eventual olmakla birlikte event-driven tetikleme ile stale pencere kisaltilmaya baslandi.
