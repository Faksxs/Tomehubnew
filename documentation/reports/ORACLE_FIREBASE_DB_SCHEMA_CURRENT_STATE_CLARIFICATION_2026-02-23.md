# TomeHub Oracle ve Firebase Veri Modeli (Guncel Durum + Duzeltme Notlari)

**Tarih:** 2026-02-23  
**Amac:** Oracle DB sema yapisindaki kategori/katmanlari guncel durumla anlatmak, onceki raporlarda olusabilecek yanlis anlamalari duzeltmek ve Firebase (Firestore) mevcut veri yapisini ayni sekilde netlestirmek.

---

## 1. Kisa Sonuc (En kritik duzeltme)

TomeHub Oracle tarafinda su an **iki katman birlikte** dusunulmeli:

1. **Canli/legacy-operasyonel tablo katmani** (ornegin `TOMEHUB_CONTENT`, `TOMEHUB_BOOKS`, `TOMEHUB_SEARCH_LOGS`, `TOMEHUB_CONCEPTS`, `TOMEHUB_CHAT_*`)
2. **Yeni canonical migration/cutover katmani** (ornegin `TOMEHUB_LIBRARY_ITEMS`, `TOMEHUB_ITEM_INDEX_STATE`, `TOMEHUB_CHANGE_EVENTS`, compatibility view'lar)

Bu nedenle sadece `.astro/warehouse.md` dosyasina bakarak "guncel Oracle semasi" anlatimi yapmak artik eksik kalir.

---

## 2. Neden Yanlis Anlasilma Oldu? (Kok neden)

### 2.1 `.astro/warehouse.md` degerli ama "live snapshot"

- `.astro/warehouse.md` 2026-02-22 tarihli bir **schema reference/snapshot** dosyasi.
- Canli tablolari ve row count'lari guzel ozetliyor.
- Ancak repo icindeki daha yeni **canonical migration/cutover** tablolarini ve view'lari tam kapsamiyor.

### 2.2 Repo artik canonical item modeli ekledi

Asagidaki kanitlar canonical modelin repo-ve-rapor gercegi oldugunu gosteriyor:

- `apps/backend/scripts/apply_phase1a_oracle_foundation.py`:
  - `TOMEHUB_LIBRARY_ITEMS`
  - `TOMEHUB_CHANGE_EVENTS`
  - `TOMEHUB_INGESTION_RUNS`
  - `TOMEHUB_INGESTION_EVENTS`
  - `TOMEHUB_ITEM_INDEX_STATE`
- `apps/backend/scripts/apply_phase1b_compat_views.py`:
  - `VW_TOMEHUB_LIBRARY_ITEMS_ENRICHED`
  - `VW_TOMEHUB_INGESTION_STATUS_BY_ITEM`
  - `VW_TOMEHUB_BOOKS_COMPAT`
- `documentation/reports/ORACLE_MIGRATION_FINALIZATION_EXECUTION_REPORT_2026-02-22.md`:
  - Phase 1A / 1B tamamlandigi ve canli snapshot'ta `TOMEHUB_LIBRARY_ITEMS` gibi tablolarin goruldugu belirtiliyor.
- `documentation/reports/PHASE6_RELEASE_GATE_READINESS_2026-02-22.md`:
  - compatibility view'larin varligi ve count parity gecildigi raporlaniyor.

---

## 3. Oracle DB Semasi: Guncel Kategori Yapisi (Pratik / Duzeltilmis Anlatim)

Asagidaki kategorizasyon "tek tablo listesi" yerine "sistemin gercek domain akislarini" anlatir.

### 3.1 Canonical Item / Senkronizasyon Katmani (Yeni ana model)

**Amaç:** Firebase item dunyasini Oracle tarafinda canonical/master model olarak tutmak ve cutover'i guvenli yapmak.

**Ana tablolar:**

- `TOMEHUB_LIBRARY_ITEMS` (yeni canonical master)
  - Ana anahtar: `ITEM_ID`
  - Tenant ayrimi: `FIREBASE_UID`
  - Tip: `ITEM_TYPE`
  - Metadata: `TITLE`, `AUTHOR`, `PUBLISHER`, `ISBN`, `SOURCE_URL`, `PAGE_COUNT`, `COVER_URL`
  - Kullanici/urun alanlari: `INVENTORY_STATUS`, `READING_STATUS`, `PERSONAL_NOTE_CATEGORY`, `IS_FAVORITE`
  - Sync/provenance alanlari: `ORIGIN_*`, `SYNC_RUN_ID`, `ROW_VERSION`, `IS_DELETED`, `DELETED_AT`

- `TOMEHUB_ITEM_INDEX_STATE` (item bazli index readiness ozet tablosu)
  - `(FIREBASE_UID, ITEM_ID)` composite PK
  - `VECTOR_READY`, `GRAPH_READY`, `FULLY_READY`
  - `TOTAL_CHUNKS`, `EMBEDDED_CHUNKS`, `GRAPH_LINKED_CHUNKS`
  - coverage ratio alanlari

- `TOMEHUB_CHANGE_EVENTS` (outbox / degisim olaylari)
  - Senkronizasyon/cutover yayin akisi icin event tablosu
  - `ENTITY_TYPE`, `EVENT_TYPE`, `STATUS`, `PAYLOAD_JSON`, retry/error alanlari

- `TOMEHUB_INGESTION_RUNS`, `TOMEHUB_INGESTION_EVENTS`
  - Run-level ve item-level ingestion izlenebilirligi

**Compatibility view'lar:**

- `VW_TOMEHUB_LIBRARY_ITEMS_ENRICHED`
- `VW_TOMEHUB_INGESTION_STATUS_BY_ITEM`
- `VW_TOMEHUB_BOOKS_COMPAT`

Bu view'lar legacy/cutover gecisinde uygulama tarafi paritesini korumak icin kullaniliyor.

### 3.2 Icerik / Retrieval / RAG Katmani

**Amaç:** Chunk bazli arama, embedding, semantic filtreleme.

**Ana tablo:**

- `TOMEHUB_CONTENT`
  - Her satir bir chunk/icerik parcasi
  - Tenant ayrimi: `FIREBASE_UID`
  - Metin: `CONTENT_CHUNK`
  - Embedding: `VEC_EMBEDDING` (vector)
  - Kaynak tipi: `SOURCE_TYPE`
  - Baglanti: `BOOK_ID` (pratikte item kimligiyle iliskileniyor; legacy ad korunmus)
  - Arama yardimcilari: `NORMALIZED_CONTENT`, `TEXT_DEACCENTED`, `LEMMA_TOKENS`
  - Semantic alanlar: `PASSAGE_TYPE`, `QUOTABILITY`, `CLASSIFIER_CONFIDENCE`
  - Sonradan eklenen canonical/sync alanlari: `CONTENT_TYPE`, `INGESTION_TYPE`, `CONTENT_HASH`, `SEARCH_VISIBILITY`, `ORIGIN_*`, `ROW_VERSION`, `IS_DELETED`

**Yardimci tablolar:**

- `TOMEHUB_CONTENT_TAGS`
- `TOMEHUB_CONTENT_CATEGORIES`
- `TOMEHUB_INGESTED_FILES` (item bazli ingestion durum/istatistik)

### 3.3 Arama Analitik / Gozlemlenebilirlik Katmani

**Amaç:** Search davranisi, latency, kalite ve feedback takibi.

**Tablolar:**

- `TOMEHUB_SEARCH_LOGS`
  - Sorgu metni, intent, strategy/score, latency, session baglantisi
  - Tarihsel olarak kolon adlari degisti/genislendi (`TIMESTAMP`, `MODEL_NAME`, vb.)

- `TOMEHUB_FEEDBACK`
  - Search sonucuna kullanici geri bildirimi (`RATING`, `SEARCH_LOG_ID`, metin alanlari)

### 3.4 Bilgi Grafigi (Knowledge Graph) Katmani

**Amaç:** Kavramlar ve iliskiler uzerinden graph destekli retrieval/discovery.

**Tablolar:**

- `TOMEHUB_CONCEPTS`
- `TOMEHUB_RELATIONS`
- `TOMEHUB_CONCEPT_CHUNKS`
- `TOMEHUB_CONCEPT_ALIASES`

**Dikkat (isim drift'i):**

- Bazi dokumanlarda normalize isimler geciyor (`CONCEPT_ID`, `RELATION_ID`, `VECTOR`)
- Kod/migration tarafinda siklikla gercek kolonlar `ID`, `SRC_ID`, `DST_ID`, `EMBEDDING`, `DESCRIPTION_EMBEDDING` olarak kullaniliyor.

### 3.5 Dis Kaynak Zenginlestirme (External KB) Katmani

**Amaç:** Wikidata/OpenAlex gibi dis kaynaklardan metadata ve graph edge saklamak.

**Tablolar:**

- `TOMEHUB_EXTERNAL_BOOK_META`
- `TOMEHUB_EXTERNAL_ENTITIES`
- `TOMEHUB_EXTERNAL_EDGES`

### 3.6 Chat / Memory / Flow Katmani

**Amaç:** Sohbet oturumlari, mesajlar, flow hafizasi ve raporlama.

**Tablolar:**

- `TOMEHUB_CHAT_SESSIONS`
  - `FIREBASE_UID`, `TITLE`, `RUNNING_SUMMARY`
  - `CONVERSATION_STATE_JSON` (JSON check)
  - `TITLE_LOCKED`, `TAGS` (JSON search index)

- `TOMEHUB_CHAT_MESSAGES`
  - `SESSION_ID` -> `TOMEHUB_CHAT_SESSIONS(ID)`
  - `ROLE`, `CONTENT`, `CITATIONS`

- `TOMEHUB_FLOW_SEEN`
  - Kullanici + session + chunk bazli "goruldu" hafizasi
  - `FIREBASE_UID`, `SESSION_ID`, `CHUNK_ID`, `SEEN_AT`
  - `TOMEHUB_CONTENT(ID)` ile FK hazirligi/uygulamasi mevcut

- `TOMEHUB_FILE_REPORTS`
  - Item/book bazli ozet, key topics, entities (JSON)

### 3.7 Kalite / Dagilim / Epistemik Katman

**Amaç:** Item/book bazli epistemik kalite dagilim olcumu.

- `TOMEHUB_BOOK_EPISTEMIC_METRICS`
  - `BOOK_ID`, `FIREBASE_UID`
  - `LEVEL_A/B/C`, `TOTAL_CHUNKS`, `UPDATED_AT`

### 3.8 Legacy / Gecis Uyumluluk Katmani

**Hala onemli tablolar (tamamen yok sayilmamali):**

- `TOMEHUB_BOOKS` (legacy book registry / mirror rolunde)
- `TOMEHUB_CONTENT` (hala retrieval'in cekirdegi)
- `TOMEHUB_INGESTED_FILES`, `TOMEHUB_FILE_REPORTS` gibi tablolar canonical modele baglanan ama tarihsel adlarini koruyan tablolar

---

## 4. Oracle Tarafinda Duzeltilmesi Gereken Anlatimlar (Yanlis Anlama Noktalari)

### 4.1 "Oracle semasi = sadece 18 tablo" anlatimi eksik

`.astro/warehouse.md` 18 tabloyu ozetliyor ama canonical migration tablolari/view'lari dahil edilmiyor. Guncel anlatimda en az iki grup ayri verilmelidir:

- **Live retrieval/legacy tables**
- **Canonical migration/cutover tables + compatibility views**

### 4.2 Kolon adlari dokumanlarda normalize edilmis olabilir

Ornekler:

- `TOMEHUB_CONCEPTS`: dokumanda `CONCEPT_ID`, kodda `ID`
- `TOMEHUB_RELATIONS`: dokumanda `SOURCE_CONCEPT_ID`, `DEST_CONCEPT_ID`; kodda `SRC_ID`, `DST_ID`
- `TOMEHUB_CHAT_SESSIONS`: dokumanda `SESSION_ID`; kodda/DDL'de PK genelde `ID`

Bu fark "schema hatasi" degil; **dokuman dilinin normalize edilmesi** ile **gercek DB kolon adi** arasindaki fark olabilir. Ama teknik raporlarda karisiklik yaratir.

### 4.3 `TOMEHUB_CONTENT.BOOK_ID` artik sadece "legacy book" anlami tasimiyor

Phase 3/6 raporlarinda `TOMEHUB_CONTENT(FIREBASE_UID, BOOK_ID)` -> `TOMEHUB_LIBRARY_ITEMS(FIREBASE_UID, ITEM_ID)` iliski hazirligi var. Bu nedenle bugunku anlatimda:

- `BOOK_ID` = "legacy isimli ama pratikte item-level foreign key alani" gibi ele alinmali.

### 4.4 `SOURCE_TYPE` alaninda legacy + canonical degerler birlikte yasiyor

`phaseX_content_source_type_constraint.sql` icinde hem eski hem yeni/kanoniklesmis degerler kabul ediliyor:

- `PDF`, `EPUB`, `PDF_CHUNK`, `ARTICLE`, `WEBSITE`
- `PERSONAL_NOTE`, `HIGHLIGHT`, `INSIGHT`, `BOOK`
- legacy/compat: `NOTES`, `NOTE`, `personal`

Yani "tek bir temiz enum var" anlatimi eksik olur.

### 4.5 Snapshot dosyalari authoritative degil

Asagidaki dosyalar faydali ama **tek otorite** degil:

- `.astro/warehouse.md` (snapshot)
- `apps/backend/schema.json` (eski/limitli snapshot)

Asil otorite:

- DDL/migration script'leri
- canli validation/release-gate raporlari
- runtime SQL callsite'lari

---

## 5. Firebase (Firestore) Mevcut DB Yapisi

Bu bolum "Firebase tarafinda uygulamanin aktif kullandigi veri modeli"ni anlatir.

## 5.1 Temel Mimari

- Kimlik: **Firebase Auth UID**
- Veri store: **Cloud Firestore**
- Oracle tarafinda tenant anahtari olarak `FIREBASE_UID` kullaniliyor

Yani Firebase UID, hem Firestore path anahtari hem Oracle multi-tenant filtreleme anahtaridir.

## 5.2 Canonical Firestore Koleksiyon Yapisi (Uygulama kaniti)

Frontend `apps/frontend/src/services/firestoreService.ts` ve backend sync servisleri uzerinden gorulen ana yapi:

- `users/{uid}` (user document)
  - Alt koleksiyon: `items`
  - Alt koleksiyon: `personalNoteFolders`

### 5.2.1 `users/{uid}/items/{itemId}`

Bu koleksiyon kullanicinin kutuphane ogelerini tutar (kitap, makale, website, personal note vb.).

**Frontend tip tanimi (`LibraryItem`) ana alanlar:**

- Kimlik / tip:
  - `id`
  - `type` (`BOOK | ARTICLE | WEBSITE | PERSONAL_NOTE`)

- Temel metadata:
  - `title`, `author`, `translator`, `publisher`, `publicationYear`, `isbn`, `url`
  - `pageCount`, `coverUrl`

- Kutuphane / durum alanlari:
  - `status` (physical status)
  - `readingStatus`
  - `isFavorite`
  - `tags`

- Icerik/not alanlari:
  - `generalNotes`
  - `highlights[]`

- Dil/policy alanlari:
  - `contentLanguageMode`
  - `contentLanguageResolved`
  - `sourceLanguageHint`
  - `languageDecisionReason`
  - `languageDecisionConfidence`

- Personal note klasorleme:
  - `personalNoteCategory`
  - `personalFolderId`
  - `folderPath`

- Zaman ve ingestion durum alanlari:
  - `addedAt`
  - `isIngested`

### 5.2.2 `highlights[]` (item icinde embedded array)

Her item icinde embedded dizi olarak tutulur.

**Temel alanlar:**

- `id`
- `text`
- `type` (`highlight | insight`, legacy `note` gelebilir)
- `pageNumber`, `paragraphNumber`, `chapterTitle`
- `comment`
- `createdAt`
- `tags`
- `isFavorite`

**Normalize notu:**

- Frontend ve backend legacy `note` tipini canonical olarak `insight`/`HIGHLIGHT`-`INSIGHT` eksenine normalize ediyor.

### 5.2.3 `users/{uid}/personalNoteFolders/{folderId}`

Personal note klasorlerini tutar.

**Alanlar:**

- `id`
- `category` (`PRIVATE | DAILY | IDEAS`)
- `name`
- `order`
- `createdAt`
- `updatedAt`

## 5.3 Backend'de Firestore -> Oracle Map (Mevcut davranis)

Backend `firestore_sync_service.py` + `firestore_sync_models.py` akisi:

- Firestore kaynagi: `users/{uid}/items`
- Her dokuman `StrictFirestoreItem` olarak normalize/validate edilir
- `item_id` Oracle tarafinda `book_id`/`item_id` baglaminda kullanilir
- `PERSONAL_NOTE` item'lar ile diger item tipleri farkli ingestion yollarina gider
- highlight'lar Oracle `TOMEHUB_CONTENT` tarafina ayri senkronize edilir

Bu nedenle Firebase yapisi sadece "frontend cache" degil; hala migration/cutover surecinde aktif veri kaynagi/partneridir.

## 5.4 Firebase Yapisi Hakkinda Duzeltme Notu

- "Firebase DB tek tablo/tek collection" degil; ana uygulama modeli **user-scoped subcollection** desenini kullaniyor.
- Canonical uygulama path'i: `users/{uid}/items`
- Personal note folder yapisi ayri subcollection: `users/{uid}/personalNoteFolders`
- Repo icinde `infra/firebase/firebase.json` mevcut olsa da Firestore data modelinin asil kaniti runtime servis kodlaridir.

---

## 6. Oracle <-> Firebase Iliskiyi Dogru Anlatmanin Onerilen Sekli

Asagidaki anlatim su an icin en dogru/az hata ureten versiyon:

1. **Kimlik ve tenant ekseni Firebase UID'dir** (`users/{uid}` ve Oracle `FIREBASE_UID`)
2. **Firebase `items` koleksiyonu user-level source modeldir**
3. **Oracle `TOMEHUB_LIBRARY_ITEMS` canonical/master modele dogru gecis katmanidir**
4. **Oracle `TOMEHUB_CONTENT` retrieval/RAG chunk katmanidir**
5. **`BOOK_ID` bircok yerde tarihsel isimdir; yeni canonical baglamda item kimligi gibi davranir**
6. **Compatibility view'lar cutover ve geriye uyum icin vardir; "kalici domain tablo" gibi anlatilmamali**

---

## 7. Dokumantasyon Icin Net Duzeltme Onerileri

### 7.1 Oracle dokumani ikiye bol

- **A. Live Operational Snapshot (warehouse.md tipi)**
- **B. Canonical Schema & Cutover Model (phase raporlari + DDL)**

### 7.2 Kolon adi standardi belirle

Teknik dokumanlarda tercihen:

- once gercek kolon adi (`ID`, `SRC_ID`)
- parantez icinde is anlami (`concept_id`, `source_concept_id`)

### 7.3 Mapping tablosu ekle (cok kritik)

Ornek dokuman tablosu:

- Firestore `users/{uid}/items/{itemId}` -> Oracle `TOMEHUB_LIBRARY_ITEMS(ITEM_ID, FIREBASE_UID)`
- Oracle `TOMEHUB_CONTENT(BOOK_ID, FIREBASE_UID)` -> canonical item anahtarina bagli retrieval chunk'lari
- `TOMEHUB_ITEM_INDEX_STATE` -> item bazli hazirlik/coverage ozeti

### 7.4 Snapshot dosyalarina "authoritative degil" etiketi ekle

Ozellikle:

- `.astro/warehouse.md`
- `apps/backend/schema.json`

---

## 8. Bu Raporun Kaynaklari (Repo-truth)

- `.astro/warehouse.md`
- `apps/backend/scripts/apply_phase1a_oracle_foundation.py`
- `apps/backend/scripts/apply_phase1b_compat_views.py`
- `apps/backend/create_analytics_schema.sql`
- `apps/backend/create_graph_schema.sql`
- `apps/backend/create_memory_schema.sql`
- `apps/backend/migrations/phaseX_*.sql` (ozellikle content/chat/graph/external/epistemic alanlari)
- `documentation/reports/ORACLE_MIGRATION_FINALIZATION_EXECUTION_REPORT_2026-02-22.md`
- `documentation/reports/PHASE6_RELEASE_GATE_READINESS_2026-02-22.md`
- `documentation/reports/PHASE3_INTEGRITY_HARDENING_REPORT_2026-02-22.md`
- `apps/frontend/src/services/firestoreService.ts`
- `apps/frontend/src/types.ts`
- `apps/backend/services/firestore_sync_service.py`
- `apps/backend/models/firestore_sync_models.py`

---

## 9. Ek Not (Guven Seviyesi)

Bu rapor **repo ve rapor kanitlarina dayali** "guncel durumu dogru anlatma" raporudur. Canli Oracle instance'ta son dakikada yeni migration calistirildiysa, tek farklar row count ve yeni kolon/tablo ekleri olabilir; ancak burada anlatilan ana kategori yapisi ve Firebase modeli repo-truth ile uyumludur.

