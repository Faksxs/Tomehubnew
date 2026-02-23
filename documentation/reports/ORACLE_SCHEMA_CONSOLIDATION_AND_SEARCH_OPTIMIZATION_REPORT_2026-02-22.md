# Oracle Schema Consolidation and Search Optimization Report (2026-02-22)

## Amaç

Bu raporun amacı iki hedefi birlikte sağlamak için Oracle şema düzenleme önerisi sunmaktır:

1. `Düzenli ve dağınık olmayan kayıt modeli`
   - Bir kitap/item için ana kayıtların tek yerde tutulması
   - UI alanları ile AI/search index verisinin ayrılması

2. `Arama (Layer 2) için hızlı ve doğru sonuç`
   - Arama için optimize edilmiş yapı korunmalı
   - Veri doğruluğu (parity) bozulmadan performans iyileştirilmeli

## Kısa Sonuç (Karar Özeti)

`TOMEHUB_CONTENT` ana kitap kaydı tablosu olmamalı.

Öneri:
- `TOMEHUB_CONTENT` = arama/index corpus tablosu (chunk/highlight/note gibi retrievable text birimleri)
- `TOMEHUB_BOOKS` (veya daha doğru isimle yeni bir `TOMEHUB_LIBRARY_ITEMS`) = ana item/master tablo
- `TOMEHUB_INGESTED_FILES` = PDF/ingestion durum tablosu (ayrı kalmalı)

Yani:
- `status`, `inventory`, `readingStatus`, `metadata` -> master tabloda
- `pdf status/chunk_count` -> `TOMEHUB_INGESTED_FILES`
- `summary/tags/category` -> canonical olarak master tabloda (ama search için kontrollü şekilde `TOMEHUB_CONTENT`e yansıtılabilir)

## Canlı Şema Gözlemi (Önemli)

Canlı Oracle şeması, `.astro/warehouse.md` dokümanındaki bazı tanımlardan farklıdır. Bu yüzden gerçek referans canlı DB olmalıdır.

Öne çıkan gerçek durum:

- `TOMEHUB_BOOKS.ID` = `VARCHAR2` (master item id gibi kullanılıyor)
- `TOMEHUB_CONTENT.BOOK_ID` = `VARCHAR2` (item id referansı)
- `TOMEHUB_CONTENT` içinde hem arama alanları hem de bazı UI/meta alanları birlikte bulunuyor:
  - `TAGS`, `SUMMARY`, `NORMALIZED_STATUS`, `CATEGORIES`, `COMMENT`

Bu tasarım çalışır, ama uzun vadede `grain` (satır seviyesi anlamı) karışıyor.

## Mevcut Sorun (Şema Perspektifi)

### 1. Aynı kavram farklı tablolarda temsil ediliyor

- `TOMEHUB_BOOKS` bir master tablo gibi duruyor
- `TOMEHUB_CONTENT.BOOK_ID` de item kimliği gibi davranıyor

Bu, ekip içinde şu karışıklıkları üretir:
- "Kitap sayısı" hangi tablodan sayılacak?
- "Bir kitabın metadata'sı" nerede authoritative?
- "Arama sonucu başlık/yazar" hangi kaynaktan gelsin?

### 2. `TOMEHUB_CONTENT` çok fazla rol üstleniyor

Şu anda aynı tabloda:
- PDF chunk
- Highlight/Insight
- Personal note
- Article/Website
- Bazı item-level text/metadata yansımaları

Bu, arama için güçlü ama bakım için zor bir yapı.

### 3. UI alanları ile search/index alanları ayrışmamış

Örnek:
- `status`, `inventory`, `readingStatus` gibi UI alanları sık güncellenir
- `TOMEHUB_CONTENT` ise daha çok arama corpus/index mantığına uygun olmalı

Mutable UI alanlarının search corpus tablosunda canonical tutulması:
- veri tekrarını artırır
- sync karmaşasını artırır
- parity/race-condition riskini yükseltir

## Tasarım Prensibi (Önerilen)

### A. "Canonical Data" ile "Search Index Data" ayrılmalı

- `Canonical` = kullanıcıya görünen gerçek kayıt (master truth)
- `Index/Search` = arama performansı için optimize edilmiş türetilmiş veri

### B. Her tablonun grain'i net olmalı

- Master tablo satırı = `1 item`
- Content tablo satırı = `1 retrievable text unit` (chunk/highlight/note vb.)

### C. Denormalization kontrollü yapılmalı

Search hızını korumak için bazı alanlar `TOMEHUB_CONTENT` içinde kopya tutulabilir; ama canonical yerleri ayrı olmalı.

## Alan Bazlı Karar Tablosu (Senin Soruna Net Cevap)

### 1. Kitap bilgileri / UID / yazar / metadata

Örnek alanlar:
- `firebase_uid`
- `title`
- `author`
- `publisher`
- `publicationYear`
- `translator`
- `isbn`
- `url`
- `pageCount`
- `coverUrl`
- `addedAt`, `updatedAt`

Karar:
- `Master tabloda tutulmalı` (`TOMEHUB_BOOKS` genişletilerek veya yeni `TOMEHUB_LIBRARY_ITEMS`)
- `TOMEHUB_CONTENT` içinde canonical tutulmamalı

Gerekçe:
- Bunlar item-level alanlar
- Aramada gösterim için join ile alınabilir
- Sık güncellenen UI metadata'sı chunk tablosunu kirletmemeli

### 2. `summary` (genel özet / generalNotes)

Bu alanda iki kullanım var:
- UI'da gösterilen item özeti/notu
- Search/RAG için aranabilir metin

Karar:
- `Canonical`: master tabloda (`summary_text` / `general_notes`)
- `Search için opsiyonel kopya`: `TOMEHUB_CONTENT` içinde tek bir item-summary satırı

Öneri:
- `TOMEHUB_CONTENT`e summary koyulacaksa bu açıkça bir index satırı olsun
  - örn. `source_type='BOOK'`, `chunk_type='item_summary'`

Neden?
- UI alanı tek yerde kalır
- Search hızlı kalır
- Veri tekrarının anlamı netleşir

### 3. `tags`

Burada iki farklı seviye var:

1. `Item tags` (kitabın etiketleri)
2. `Highlight tags` (tek tek highlight etiketleri)

Karar:
- `Item tags`: master tarafında ayrı ilişki tablosu (`TOMEHUB_ITEM_TAGS`) önerilir
- `Highlight tags`: `TOMEHUB_CONTENT_TAGS` içinde kalmalı (çünkü content-level)

Geçişte pratik çözüm:
- Kısa vadede `TOMEHUB_CONTENT.TAGS` compatibility için kalabilir
- Ama canonical item tags artık master kaynaklı olmalı

### 4. `status` / `readingStatus` / `inventory`

Örnek:
- `On Shelf`, `Lent Out`, `Lost`
- `To Read`, `Reading`, `Finished`

Karar:
- `Sadece master tabloda tutulmalı`
- `TOMEHUB_CONTENT` içinde canonical tutulmamalı

Gerekçe:
- Bunlar arama corpus verisi değil
- UI/analytics verisi
- Sık güncellenebilir alanlar

### 5. `pdf` durumu (indexed mi, chunk sayısı, file info)

Karar:
- `TOMEHUB_INGESTED_FILES` içinde tutulmalı (ayrı kalmalı)

Öneri:
- `BOOK_ID + FIREBASE_UID` unique tasarım doğru (zaten var)
- PDF durumunu `TOMEHUB_CONTENT`ten türetmek yerine `TOMEHUB_INGESTED_FILES` authoritative olsun
- `TOMEHUB_CONTENT` sadece chunkların kendisini tutsun

Not:
- UI'daki "PDF indexed" durumunda fuzzy title fallback yanlış pozitif üretebiliyor; item-id bazlı doğrulama daha güvenli

### 6. `category`

`Category` tek anlamlı değil. Ayrıştırmak gerekir:

1. `Personal note category` (`PRIVATE/DAILY/IDEAS`)
2. `Book thematic category` (etiket/kategori sınıfları)
3. `Content NLP categories` (chunk-level sınıflandırma)

Karar:
- `Personal note category`: master tabloda item-level alan
- `Book thematic categories`: master item category mapping tablosu (veya item tags içinde)
- `Content NLP categories`: `TOMEHUB_CONTENT_CATEGORIES` içinde kalmalı

## Hedef Şema Önerisi (Pragmatik)

## Seçenek A (Önerilen - düşük risk)

`TOMEHUB_BOOKS` tablosunu "kitap" yerine "library item master" rolüne yaklaştırmak (veya yeni isimle paralel tablo açmak)

### A1. Master tablo (canonical)

Öneri isim:
- Kısa vadede: `TOMEHUB_BOOKS` (genişletilmiş)
- Daha temiz: `TOMEHUB_LIBRARY_ITEMS`

Satır seviyesi:
- `1 user item = 1 row`

Önerilen alan grupları:
- Kimlik: `id`, `firebase_uid`, `type`
- Kimlik/meta: `title`, `author`, `publisher`, `publication_year`, `translator`, `isbn`, `url`
- UI durumu: `inventory_status`, `reading_status`, `is_favorite`
- Note/meta: `personal_note_category`, `folder_id`, `folder_path`
- Özet: `general_notes` (veya `summary_text`)
- Görsel/fiziksel: `cover_url`, `page_count`, `shelf_code`
- Audit: `created_at`, `updated_at`

### A2. Search corpus tablosu (mevcut `TOMEHUB_CONTENT`)

Rol:
- Arama ve RAG için retrievable text unit store

Satır seviyesi:
- `1 chunk/highlight/insight/personal_note_text = 1 row`

Kalacak alanlar:
- `firebase_uid`, `source_type`, `content_chunk`, `vec_embedding`
- `book_id` (aslında item_id referansı)
- `page_number`, `chunk_index`, `chunk_type`
- `text_deaccented`, `lemma_tokens`, `normalized_content`, `token_freq`
- `comment`, `summary` (yalnızca content-row bağlamında)

Not:
- `BOOK_ID` adı teknik olarak artık `ITEM_ID` olmalı (uzun vadede rename)

### A3. Ingestion durumu (mevcut `TOMEHUB_INGESTED_FILES`)

Rol:
- Dosya ingestion orchestration / index freshness durumu

Kalmalı:
- `status`, `chunk_count`, `embedding_count`, `source_file_name`, timestamps

## Arama Performansı ve Doğruluk İçin Etki Analizi

### Bu ayrım aramayı yavaşlatır mı?

Doğru tasarlanırsa hayır.

Çünkü Layer 2'nin ağır işi zaten `TOMEHUB_CONTENT` üzerinde:
- exact/lemma match
- vector search
- highlight/insight retrieval

Master tablo genelde şu amaçla join edilir:
- başlık/yazar/meta gösterimi
- filter metadata

Bu join, doğru indeksle ucuz olur.

### Arama için önerilen pratik kurallar

1. `TOMEHUB_CONTENT` arama motoru tablosu olarak kalsın
2. Master tablo UI truth olsun
3. Arama çıktısında başlık/yazar gerekiyorsa:
   - mümkünse `TOMEHUB_CONTENT`te denormalized display alanları compatibility için kalsın
   - orta vadede join veya view ile standardize edilsin

### Önerilen indeks iyileştirmeleri (canlı şemaya göre)

Mevcut güçlü taraflar:
- Vector index var: `IDX_TOMEHUB_VEC_EMBEDDING`
- Source filter index var
- User+source composite index var
- Normalized text domain index var (`IDX_NORM_CONTENT`)

Muhtemel eksikler / iyileştirme adayları:

1. `TOMEHUB_CONTENT (FIREBASE_UID, BOOK_ID, SOURCE_TYPE)`
- Per-item retrieval / sync / status kontrollerinde çok iş görür

2. `TOMEHUB_CONTENT (FIREBASE_UID, BOOK_ID, CREATED_AT)`
- item bazlı kronolojik highlight çekiminde faydalı

3. `TOMEHUB_BOOKS` (veya master tablo) için
- `(FIREBASE_UID, TYPE)`
- `(FIREBASE_UID, UPDATED_AT)`
- gerekirse `(FIREBASE_UID, READING_STATUS)`

Not:
- İndeks ekleme kararı mutlaka query plan ölçümüyle verilmelidir

## Veri Kaybı Riski Açısından Kurallar (Zorunlu)

Senin önceliğin `0 veri kaybı`. Bu şema düzenlemede şu kurallar şart:

1. Canonical tabloya geçmeden önce parity raporu
- count parity
- hash parity (özellikle highlights/insights)

2. Dual-write kısa süreli olabilir, ama audit log ile
- hangi kayıt nereye yazıldı izlenmeli

3. Master tablo authoritative olmadan eski yolu kapatma
- önce doğrulama, sonra cutover

4. `PERSONAL_NOTE` dahil tüm tipler için açık politika
- artık skip yoksa, şema ve sync de buna göre tek anlamlı olmalı

## Uygulama Önerisi (Sıralı)

### Faz 1: Şema Kararını Netleştir (DDL yok, tasarım kararı)

- `TOMEHUB_BOOKS` genişletilecek mi?
- yoksa `TOMEHUB_LIBRARY_ITEMS` yeni tablo mu açılacak?

Önerim:
- Yeni tablo (`TOMEHUB_LIBRARY_ITEMS`) daha temiz
- Ama düşük risk istiyorsan mevcut `TOMEHUB_BOOKS` genişletmek daha hızlı

### Faz 2: Master Alanları Oracle'a Taşı (Backfill)

Firestore item alanlarından:
- `status`, `readingStatus`, `tags`, `generalNotes`, `metadata`, `personalNoteCategory`, vb.

### Faz 3: Search Corpus'u Korumalı Temizleme

- `TOMEHUB_CONTENT`te canonical olmayan alanları "derived/compat" olarak işaretle
- yeni yazma yolunda master -> content projection standardize et

### Faz 4: Query Path Standardizasyonu

- UI list/detail = master tablo
- Layer 2 retrieval = content tablo
- mixed endpointler için net join/view standardı

## Nihai Görüş (Senin Soruna Direkt Cevap)

Bir kitabın/ögenin kayıtları dağınık olmamalıysa:

- `Ana kayıt (UID, yazar, metadata, status, inventory, category, summary)` -> **tek master tabloda**
- `PDF ingestion durumu` -> **TOMEHUB_INGESTED_FILES**
- `Arama chunk/highlight/insight/personal-note text` -> **TOMEHUB_CONTENT**

`TOMEHUB_CONTENT` "her şeyi tutan ana kayıt tablosu" değil, "arama motorunun içerik tablosu" olmalı.

Bu yaklaşım:
- sistemi düzenli yapar
- veri kaybı riskini azaltır
- search performansını korur
- arama doğruluğunu (parity sonrası) artırır

## Ek Not (Dokümantasyon Disiplini)

`.astro/warehouse.md` faydalı ama canlı şemadan sapabiliyor. Bu nedenle optimizasyon sürecinde:

- "Doküman" değil, "live schema query + code path" authoritative kabul edilmeli.

