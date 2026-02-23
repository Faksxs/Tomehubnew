# TomeHub Oracle Sema Konsolidasyonu ve Arama Optimizasyonu Final Implementasyon Raporu (v4)

**Tarih:** 2026-02-22  
**Durum:** Final Plan (Implementation Blueprint)  
**Kapsam:** Oracle canonical migration, search optimization, parity-safe cutover

---

## 1. Kisa Ozet

Bu final plan, onceki onerileri + son ornek mimariden alinabilecek faydali parcalari + canli sistem gerceklerini birlestirir.

Ana kararlar:
- `Oracle = tam veri deposu` (personal notes dahil)
- `Master data` ile `search corpus` ayrilir
- `Compatibility-first` gecis yapilir (sistemi kirmadan)
- `0 veri kaybi` parity ve audit ile kanitlanmadan cutover yapilmaz

---

## 2. Son Ornek Yapidan Alinan Ilham (Objektif Degerlendirme)

### 2.1 Planimiza Eklenenler

1. **Tier yaklasimi (katmanli dusunme)**
- Kabul
- Kullanilacak:
  - Tier 1: Canonical Item + Content
  - Tier 2: Search/Analytics/Observability
  - Tier 3: Graph/Relationships

2. **Ayrı kalite/eval tablosu fikri (`TOMEHUB_JUDGE_EVALUATIONS`)**
- Kismi kabul
- Zorunlu degil, ancak offline search/RAG kalite olcumu icin faydali

3. **Author enrichment tracking**
- Kabul
- Sadece `AUTHOR` doldurma degil, enrichment workflow durumu izlenecek

4. **TOTAL_CHUNKS otomasyonu**
- Kabul (uyarlanmis)
- Trigger yerine once summary-state / scheduled update job yaklasimi
- Trigger opsiyonu daha sonra

5. **Ingestion log tablosu**
- Kabul (uyarlanmis)
- Generic log yerine `run/event` modeli

### 2.2 Zaten Mevcut veya Yanlis Teshis Olanlar

1. **Books-Content STRING MATCH riski**
- Legacy raporlarda geciyor
- Canli sistemde `BOOK_ID` kullanimi mevcut
- Gercek is:
  - FK cleanup + validation
  - orphan/mismatch temizligi
  - title fallback sadece yardimci mekanizma

2. **Read/Write pool separation**
- Zaten mevcut
- Yeni is degil; tuning + monitoring isi

3. **Vector index + semantic filtering**
- Vector index zaten mevcut
- Gercek optimizasyon hedefi:
  - lexical query paterni
  - source/visibility filtering
  - telemetry + query plan olcumu

4. **Cache staleness -> model version hashing invalidation**
- Kismen mevcut (cache key icinde model/router/mix bayraklari var)
- Gerekli ek iyilestirme:
  - item-level invalidation
  - ingestion/sync event-driven invalidation

### 2.3 Simdilik Eklenmeyenler

1. **Bitmap index onerisi**
- `TOMEHUB_CONTENT` DML yogun oldugu icin riskli
- Oracle bitmap index write contention yaratabilir
- Content tablosu icin reddedildi (simdilik)

2. **`TOMEHUB_FLOW_ANCHORS`**
- Fayda potansiyeli var
- Cekirdek migration icin zorunlu degil
- `phase-later backlog`

---

## 3. Final Hedef Mimari (Tier Bazli)

## Tier 1: Core Canonical + Content

### 3.1 `TOMEHUB_LIBRARY_ITEMS` (Yeni Canonical Master)

**Grain:** `1 item = 1 row`

**Amac:**
- UID, title, author, metadata
- summary/general notes
- status / inventory / reading state
- category/tag policy
- audit / provenance / visibility

### 3.2 `TOMEHUB_CONTENT` (Search Corpus)

**Grain:** `1 retrievable text unit = 1 row`

**Amac:**
- PDF/EPUB chunk'lari
- highlights / insights
- personal note text'leri
- article / website body
- embeddings + lexical search alanlari

### 3.3 `TOMEHUB_INGESTED_FILES` (Ingestion Status)

**Grain:** `1 item/file ingestion state`

**Amac:**
- indexed status
- chunk_count / embedding_count
- file metadata
- failure reason / status reason

## Tier 2: Search, Analytics, Observability

### 3.4 `TOMEHUB_SEARCH_LOGS` (Partition-ready)
- query analytics
- latency
- routing diagnostics
- cache hit bilgisi

### 3.5 `TOMEHUB_CHANGE_EVENTS` (Yeni Outbox)
- polling / SSE / WebSocket icin guvenilir degisim kaynagi

### 3.6 `TOMEHUB_INGESTION_RUNS` / `TOMEHUB_INGESTION_EVENTS` (Yeni)
- ingestion izlenebilirlik
- retry / failure analizi
- parity/debug izi

### 3.7 `TOMEHUB_JUDGE_EVALUATIONS` (Opsiyonel ama onerilen)
- offline arama/RAG kalite degerlendirmesi
- `TOP_RESULT_SCORE` null probleminden bagimsiz kalite normalize etme

### 3.8 `TOMEHUB_ITEM_INDEX_STATE` (Yeni Summary)
- vector/graph readiness summary
- UI/API hizlandirma

## Tier 3: Graph & Relationships

### 3.9 Mevcut (Korunur)
- `TOMEHUB_CONCEPTS`
- `TOMEHUB_RELATIONS`
- `TOMEHUB_CONCEPT_CHUNKS`

### 3.10 Opsiyonel Gelecek
- Flow anchors benzeri yapi (urun ihtiyaci netlesince)

---

## 4. Canli Sistem Gercegi ve Duzeltilen Varsayimlar

Bu plan canli sistem/kod kullanimina dayanir:

- `TOMEHUB_CONTENT` arama/RAG'nin ana calisma tablosudur.
- `SOURCE_TYPE` backend'de yaygin hardcoded kullaniliyor (`search`, `flow`, `analytics`, `ingestion`).
- `Exact/Lemma` arama SQL seviyesinde `LIKE`, boundary dogrulama application tarafinda yapiliyor.
- `TOMEHUB_SEARCH_LOGS` zaman kolonu `TIMESTAMP` (bazi raporlarda `CREATED_AT` varsayimi geciyor).
- `TOMEHUB_INGESTED_FILES` ingestion-status icin authoritative olmali.
- `BOOK_ID` baglantisi canli sistemde vardir; sadece integrity hardening gerekir.

**Not:** Legacy raporlardaki `TITLE string-match` anlatimlari final implementasyon kararlarinda authoritative kabul edilmeyecektir.

---

## 5. Sema Kararlari (Final, Kilitli)

### 5.1 `SOURCE_TYPE` Ayrimi (Additive)

`TOMEHUB_CONTENT` icine yeni kolonlar:
- `INGESTION_TYPE` (`PDF`, `EPUB`, `WEB`, `MANUAL`, `SYNC`)
- `CONTENT_TYPE` (`BOOK_CHUNK`, `HIGHLIGHT`, `INSIGHT`, `NOTE`, `ARTICLE_BODY`, `WEBSITE_BODY`, `ITEM_SUMMARY`)

Kurallar:
- `SOURCE_TYPE` compatibility icin kalir
- backend kademeli migration ile gecer
- mapping matrix ile populate edilir

### 5.2 Privacy / Visibility Policy

Yeni alan (master/content):
- `SEARCH_VISIBILITY` (`DEFAULT`, `EXCLUDED_BY_DEFAULT`, `NEVER_RETRIEVE`)

Default:
- `PRIVATE`, `DAILY` notlar Oracle'da tutulur
- varsayilan Layer-2/RAG aramalarinda gelmez
- explicit filter ile erisilir

### 5.3 Provenance / Audit (0 veri kaybi icin kritik)

Yeni alanlar (master/content):
- `ORIGIN_SYSTEM`
- `ORIGIN_COLLECTION`
- `ORIGIN_DOC_ID`
- `ORIGIN_SUBDOC_ID`
- `ORIGIN_UPDATED_AT`
- `SYNC_RUN_ID`

Amaç:
- Firestore -> Oracle kaydinin kaynak izini saklamak
- parity/debug/idempotency kolaylastirmak

### 5.4 Tombstone / Soft Delete

Yeni alanlar:
- `IS_DELETED`
- `DELETED_AT`
- `DELETION_SOURCE`
- `ROW_VERSION`

Amaç:
- silinen kayitlarin geri gelmesini onlemek
- sync conflict/coherency guclendirmek

### 5.5 Dedupe Foundation

Yeni alan:
- `CONTENT_HASH`

Kural:
- ilk faz `soft dedupe`
- hard unique constraint sonra (entity-grain netlestikten sonra)
- hash algoritmasi standardize edilir: **SHA-256**
- hash girisi canonicalized text uzerinden uretilir (normalization kurali dokumante edilmeden backfill baslatilmaz)

### 5.6 FK ve Integrity

- `TOMEHUB_CONTENT.BOOK_ID` -> canonical item relation enforce/validate hale getirilecek
- once:
  - orphan cleanup
  - parity validation
- sonra FK validation/enforcement

### 5.7 `TOMEHUB_BOOKS` -> `TOMEHUB_LIBRARY_ITEMS` DML Gecis Kurali

Kritik kural:
- `Compatibility View First` rollout'ta write-path icin view uzerine `INSERT/MERGE` varsayilmayacak.
- `TOMEHUB_BOOKS` DML callsite'lari (runtime servisler + kritik jobs/scripts) audit edilip yeni hedefe alinacak.

Neden:
- Oracle view uzerine DML cogu durumda `INSTEAD OF` trigger gerektirir
- plansiz view swap write-path kirilmasi yaratir

Uygulama secenegi (oncelik sirasi):
1. Backend write callsite'larini dogrudan `TOMEHUB_LIBRARY_ITEMS`'a tasimak
2. Service/procedure katmani ile merkezi write abstraction
3. Gecici olarak `INSTEAD OF` trigger (yalniz compatibility gecisi icin)

Not:
- Runtime tarafta mevcut `TOMEHUB_BOOKS` write path'leri icin sistematik DML inventory zorunludur; sayi sabit varsayilmamalidir.

---

## 6. Veri Yerlesim Karari (Final)

### 6.1 `TOMEHUB_LIBRARY_ITEMS` (Canonical)

Tutulacaklar:
- UID
- title / author / publisher / translator / isbn / url / page_count / cover
- summary / general notes
- tags (item tags mapping)
- category (item taxonomy mapping)
- status / reading_status / inventory
- personal_note_category (item-level ise)
- favorite
- audit / provenance / visibility

### 6.2 `TOMEHUB_INGESTED_FILES`

Tutulacaklar:
- PDF indexed status
- chunk_count / embedding_count
- file info
- failure reason / status reason

### 6.3 `TOMEHUB_CONTENT`

Tutulacaklar:
- highlight / insight / note / article / website / pdf chunk textleri
- embeddings
- lexical fields (`normalized_content`, `text_deaccented`, `lemma_tokens`)
- search-serving projection alanlari (gerektigi kadar)

---

## 7. Public API / Interface Degisiklikleri (Additive)

### 7.1 Search API (`/api/search`, `/api/smart-search`)

Yeni opsiyonel parametreler:
- `include_private_notes` (default `false`)
- `visibility_scope` (`default`, `all`)
- `content_type` (rollout sonrasi)
- `ingestion_type` (rollout sonrasi)

### 7.2 Ingestion Status API

Yeni response alanlari:
- `match_source` (`exact_book_id`, `title_fallback`)
- `match_confidence`
- `item_index_state` (`TOMEHUB_ITEM_INDEX_STATE` kaynakli)

### 7.3 Realtime Polling / Event API

Yeni response modeli:
- `last_event_id`
- `changes[]`
- `server_time`

### 7.4 Admin/Internal Parity API veya Job Output

Standart alanlar:
- `entity_counts`
- `hash_mismatches`
- `quarantine_count`
- `remaining_mismatch_items`

---

## 8. Optimizasyon Plani (Gercekten Faydali Olanlar)

## 8A. Kisa Vadede En Cok Etki (High ROI)

### 1. Composite Indexler (olcum bazli)

Oncelikli adaylar:
- `TOMEHUB_CONTENT(FIREBASE_UID, BOOK_ID, SOURCE_TYPE)`
- `TOMEHUB_CONTENT(FIREBASE_UID, BOOK_ID, CREATED_AT)`
- `TOMEHUB_CONTENT(FIREBASE_UID, BOOK_ID, CONTENT_TYPE)` (rollout sonrasi)
- `TOMEHUB_INGESTED_FILES(FIREBASE_UID, BOOK_ID[, FILE_TYPE])`
- `TOMEHUB_SEARCH_LOGS(TIMESTAMP)` (partition oncesi/sonrasi local strategy)

### 2. Search Telemetry Breakdown

`TOMEHUB_SEARCH_LOGS.STRATEGY_DETAILS` JSON icine eklenecek:
- `VECTOR_TIME_MS`
- `GRAPH_TIME_MS`
- `RERANK_TIME_MS`
- `LLM_TIME_MS`
- `CACHE_HIT`
- `CACHE_LAYER`

### 2.1 Security Hardening: ExactMatchStrategy SQL Injection Riski

Tespit:
- `ExactMatchStrategy` icinde `LIKE '%{safe_term}%'` string interpolation kullanimi vardir.

Karar:
- Faz 4 kapsaminda **zorunlu** duzeltme
- Security niteliginde oldugu icin uygun olursa Faz 4 oncesi hotfix olarak one alinabilir

Hedef:
- string interpolation kaldirilir
- bind-safe Oracle pattern arama tasarimi uygulanir
- mevcut exact match davranisi korunur (regression test ile)

### 3. Index Freshness Summary Table

`TOMEHUB_ITEM_INDEX_STATE` ile:
- `get_index_freshness_state` aggregate sorgu yuku azalir
- UI/API yanitlari hizlanir

### 4. Outbox Events

Ortak temel:
- realtime UX
- cache invalidation
- sync audit

### 5. Author Enrichment Tracking

Sadece `AUTHOR` alanini doldurmak degil:
- enrichment durumu
- son deneme zamani
- kaynak/provider
- hata nedeni

## 8B. Orta Vadede Etkili

### 1. `SEARCH_LOGS` Monthly Partition + Archive
- `TIMESTAMP` bazli
- retention cleanup `DELETE` yerine partition maintenance

### 2. Daily Analytics Pre-Aggregation
- dashboard/rapor sorgularini hafifletir
- ornek: `SEARCH_LOGS_DAILY_METRICS`

### 3. Title Canonicalization
- fallback match guvenligi
- duplicate detection

## 8C. Simdilik Ertelenenler (Olcum Gerektirir)

1. `TOMEHUB_CONTENT` partition  
2. Bitmap indexler (ozellikle content tablosu)  
3. Flow-specific yeni graph anchor tablolari

---

## 9. Final Implementasyon Yol Haritasi (6 Faz)

## Faz 1: Preparation (DDL Additive + Compat Foundation) [Hafta 1]

Yapilacaklar:
- `TOMEHUB_LIBRARY_ITEMS` olustur
- `TOMEHUB_CHANGE_EVENTS` olustur
- `TOMEHUB_ITEM_INDEX_STATE` olustur
- `TOMEHUB_INGESTION_RUNS` / `TOMEHUB_INGESTION_EVENTS` olustur
- `TOMEHUB_CONTENT` additive kolonlarini ekle:
  - `INGESTION_TYPE`
  - `CONTENT_TYPE`
  - `CONTENT_HASH`
  - `SEARCH_VISIBILITY`
  - `ORIGIN_*`
  - tombstone/version alanlari
- compatibility view'lar olustur
- non-breaking index baslangic seti ekle (olcum planiyla)

**Cikti:**
- Canli sistem bozulmadan yeni iskelet hazir

## Faz 2: Migration / Backfill / Enrichment [Hafta 2]

Yapilacaklar:
- `TOMEHUB_LIBRARY_ITEMS` backfill (Oracle + Firestore canonical merge)
- `CONTENT_TYPE / INGESTION_TYPE` backfill
- `SEARCH_VISIBILITY` populate (`PRIVATE/DAILY => EXCLUDED_BY_DEFAULT`)
- `CONTENT_HASH` backfill
- `AUTHOR enrichment` pipeline + tracking
- `TOMEHUB_ITEM_INDEX_STATE` initial populate

**Backfill sirasi (zorunlu belge):**
1. Nullable/additive kolonlar + defaults + compatibility view hazirlik kontrolu
2. `TOMEHUB_LIBRARY_ITEMS` base backfill (id/uid/type/title + minimum audit/provenance)
3. Item metadata backfill (author/publisher/status/inventory/summary vb.)
4. `SEARCH_VISIBILITY` population (policy once yerlessin)
5. `TOMEHUB_CONTENT` icin `INGESTION_TYPE/CONTENT_TYPE` mapping backfill
6. `CONTENT_HASH` backfill (SHA-256, canonicalized text, batch + idempotent)
7. `TOMEHUB_ITEM_INDEX_STATE` initial populate
8. `AUTHOR enrichment` jobs + tracking + retry queue
9. Parity pre-check (count) ve parity deep-check (hash)

Siralama gerekcesi:
- once canonical item kimligi/policy yerlesir
- sonra content-derived alanlar doldurulur
- hash/parity hesaplari en son stabil veri uzerinde calisir

**Cikti:**
- canonical master dolu
- search corpus yeni kolonlari populated

## Faz 3: Parity & Integrity Hardening [Hafta 2-3]

Yapilacaklar:
- entity bazli parity:
  - `BOOK`
  - `ARTICLE`
  - `WEBSITE`
  - `HIGHLIGHT`
  - `INSIGHT`
  - `PERSONAL_NOTE`
- hash parity (ozellikle highlight/insight)
- orphan cleanup
- `BOOK_ID` relation validation
- quarantine/retry flow standardizasyonu

**Cikti:**
- `0 veri kaybi` cutover on kosulu saglanir

## Faz 4: Search / Realtime / Cache Code Alignment [Hafta 3-4]

Yapilacaklar:
- search endpoints visibility policy
- telemetry breakdown logging
- `ExactMatchStrategy` SQL injection riskinin giderilmesi (string interpolation kaldirma)
- ingestion status confidence metadata
- outbox-based polling
- cache invalidation eventleri (ingestion/sync sonrasi)
- compatibility views ustunden read path standardizasyonu

**Cikti:**
- UX korunur
- backend yeni semayi kullanmaya baslar

## Faz 5: Performance & Analytics Optimization [Hafta 4]

Yapilacaklar:
- query profiling
- index fine-tuning
- `SEARCH_LOGS` partition implementation
- archive strategy
- optional daily aggregate tables

**Cikti:**
- p95/p99 iyilestirme
- log buyumesi kontrolu

## Faz 6: Validation, Rollout, Cleanup [Hafta 5]

Yapilacaklar:
- regression tests
- parity rerun
- rollback drill
- phased read cutover finalize
- write path finalize (Oracle-first)
- Firebase write disable (yalniz parity + rollback + monitoring green ise)

**Cikti:**
- Guvenli cutover

---

## 10. Test Senaryolari (Zorunlu)

## 10.1 Veri Dogrulugu
- personal notes (`PRIVATE/DAILY` dahil) Oracle'da count parity
- highlight/insight count + hash parity
- duplicate sync rerun idempotent (count artmaz)

## 10.2 Arama Kalitesi
- `bilhassa` gibi parity keyword testlerinde exact count eslesir
- private/daily default exclude, explicit include calisir
- lexical/semantic mix policy regress olmaz

## 10.3 Ingestion / PDF Status
- exact `book_id` match oncelikli
- title fallback false positive uretmez
- `TOMEHUB_INGESTED_FILES` authoritative status kalir

## 10.4 Realtime
- polling degisiklikleri 2-5 sn icinde gorur
- outbox retry duplicate publish uretmez

## 10.5 Performans
- p50/p95 search olcumleri baseline'dan kotulesmez (veya kabul edilen sinirda kalir)
- `index_freshness` summary table sonrasi latency duser

## 10.6 Rollback
- compatibility view rollback
- additive schema rollback (non-destructive adimlar)
- partition/retention rollback runbook

---

## 11. KPI / Kabul Kriterleri (Final)

1. **0 veri kaybi**
- tum entity'lerde parity gecer
- quarantine cozulmeden cutover yok

2. **Search dogruluk**
- parity orneklerinde exact hit count esit
- privacy visibility policy dogru uygulanir

3. **Search performans**
- p95 hedefi korunur/iyilesir
- `SEARCH_LOGS` latency breakdown gozlenebilir

4. **Realtime UX**
- polling p95 <= 5 sn
- push (eklenirse) p95 <= 1.5 sn

5. **Operasyonel guvenlik**
- provenance + outbox + tombstone aktif
- rollback testi gecer

---

## 12. Varsayimlar / Defaultlar (Son Hali)

- Oracle 7/24 erisilebilir
- Firebase Auth devam eder
- Tum personal notes Oracle'a tasinir
- `PRIVATE/DAILY` default retrieval disinda tutulur (explicit include ile erisilir)
- `SOURCE_TYPE` additive geciste kalir
- `TOMEHUB_LIBRARY_ITEMS` yeni canonical master'dir
- rollout `Compatibility View First`
- `SEARCH_LOGS` partition implementation orta fazda yapilir
- `CONTENT_HASH` soft dedupe ile baslar
- `TOMEHUB_CONTENT` partition simdilik ertelenir (olcum sonrasi)

---

## 13. Uretilecek / Korunacak Dokumantasyon Seti

Bu final rapor, asagidaki calismalarla birlikte kullanilacaktir:
- canli schema truth snapshot
- DDL blueprint (additive)
- backfill/parity runbooks
- rollback runbooks
- query profiling notlari
- KPI baseline ve post-change karsilastirmalari

---

## 14. Son Not (Uygulama Disiplini)

Bu planin en kritik prensibi:
- **Once parity + audit + rollback**, sonra cutover

Sistem calisirken sema duzenlemesi yapilacagi icin:
- additive migration
- compatibility views
- olcum bazli index kararlari
- policy-driven retrieval visibility

yaklasimi zorunludur.
