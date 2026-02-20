# Kitap Tag Uretim Mantigi ve Akisi (Teknik + Akis)

- Tarih: 2026-02-19
- Kapsam: TomeHub'da kitap tag'lerinin uretimi, temizlenmesi, API akisiyla tasinmasi, veri katmanina yazimi ve tuketimi.
- Hedef: Muhendislik ekibi icin izlenebilir teknik referans.

## 1) Amac ve Kisa Ozet
Bu rapor, kitap tag'lerinin su sorulara cevap verecek sekilde nasil olustugunu dokumante eder:
- Tag'i kim uretir? (Frontend tetikleme + Backend LLM servis)
- Hangi kurallarla temizlenir? (format, adet, dil, duplicate)
- Hangi endpointlerden gecer? (enrich-book, enrich-batch, generate-tags)
- Hangi tablolara/yapilara yazilir? (`TOMEHUB_CONTENT.tags`, `TOMEHUB_CONTENT_TAGS`, Firestore item `tags`)
- Uygulamada nerede kullanilir? (liste filtreleri, dashboard, arama skoru)

## 2) Uctan Uca Akis (Metin Diyagram)
```text
[UI tetikleme]
  |- BookDetail / BookForm / BatchEnrichment
  v
[Frontend service: geminiService]
  |- POST /api/ai/enrich-book
  |- POST /api/ai/enrich-batch (stream)
  |- POST /api/ai/generate-tags
  v
[Backend app.py endpoint]
  |- request model validation
  |- auth + rate limit
  v
[Backend ai_service]
  |- prompt olusturma
  |- LLM cagrisi
  |- sanitize_generated_tags
  |- dil kontrolu (tags_match_target_language)
  |- mismatch fallback/retry
  v
[Frontend merge + persist]
  |- Firestore'a saveItemForUser ile yazim
  |- bazi akislarda /api/add-item, /sync-highlights ile Oracle AI store'a yazim
  v
[Tuketim]
  |- BookList filtre/search/tag facets
  |- Dashboard istatistikleri
  |- Smart search score boost (tag match)
```

## 3) Frontend Tetikleme Noktalari
### 3.1 Kitap enrichment (summary + tags)
- `enrichBookWithAI(...)` frontendten backend'e `/api/ai/enrich-book` cagrisi yapar.
  - Referans: `apps/frontend/src/services/geminiService.ts:456`, `apps/frontend/src/services/geminiService.ts:472`
- Batch enrichment `/api/ai/enrich-batch` ile stream/NDJSON benzeri akista alinir.
  - Referans: `apps/frontend/src/services/geminiService.ts:508`, `apps/frontend/src/services/geminiService.ts:515`
- Batch tetikleme hook'u:
  - Referans: `apps/frontend/src/hooks/useBatchEnrichment.ts:78`

### 3.2 Note/Highlight icin tag uretimi
- `generateTagsForNote(...)` -> `/api/ai/generate-tags`
  - Referans: `apps/frontend/src/services/geminiService.ts:258`, `apps/frontend/src/services/geminiService.ts:266`
- UI tetikleyicileri:
  - Book form note tag butonu: `apps/frontend/src/components/BookForm.tsx:135`
  - Highlight editor tag butonu: `apps/frontend/src/components/HighlightSection.tsx:120`

### 3.3 Harici kaynaklardan gelen ilk tag seti
- Google Books sonucundan `volumeInfo.categories` tag'e maplenir.
  - Referans: `apps/frontend/src/services/bookSearchService.ts:158`
- OpenLibrary sonucundan `subject` ilk 5 etiket olarak maplenir.
  - Referans: `apps/frontend/src/services/bookSearchService.ts:230`
- JSON import akisinda varsayilan `tags: []` ile baslanir.
  - Referans: `apps/frontend/src/components/ImportBooks.tsx:70`

## 4) Backend Uretim Katmani
### 4.1 Endpointler
- `POST /api/ai/enrich-book`
  - Referans: `apps/backend/app.py:2086`
- `POST /api/ai/enrich-batch`
  - Referans: `apps/backend/app.py:2105`
- `POST /api/ai/generate-tags`
  - Referans: `apps/backend/app.py:2134`

### 4.2 Prompt mantigi
- Kitap enrichment promptu: summary + tags + dil zorlamasi + JSON donus bekler.
  - Referans: `apps/backend/services/ai_service.py:24`
- Note tag promptu: 3-5 tag, not diliyle ayni dil, tag basina 1-4 kelime.
  - Referans: `apps/backend/services/ai_service.py:56`

### 4.3 Streaming davranisi (batch)
- `stream_enrichment(...)` her kitap icin satir bazli JSON chunk uretir.
- Toplam stream boyutu limiti vardir (`max_total_bytes`, default 1MB); asilirsa `limit_reached` durum mesaji doner.
  - Referans: `apps/backend/services/ai_service.py:424`

## 5) Validasyon ve Sanitization Kurallari
### 5.1 Request modeli
- `EnrichBookRequest` alanlari (title, author, tags vb.)
  - Referans: `apps/backend/models/request_models.py:178`
- `GenerateTagsRequest.note_content` min/max siniri (1..6000)
  - Referans: `apps/backend/models/request_models.py:214`
- `normalize_tags` validator'i **AddItemRequest** icinde bulunur (enrich request icinde degil).
  - Referans: `apps/backend/models/request_models.py:161`

### 5.2 Tag sanitize kurallari
`sanitize_generated_tags(...)` asagidaki filtreleri uygular:
- Sadece string tag kabul
- Bos/degersiz tag atilir
- 1..4 kelime zorunlulugu
- Case-insensitive duplicate temizligi
- Max 5 tag
- Referans: `apps/backend/services/ai_service.py:110`

## 6) Dil Politikasi ve Fallback
### 6.1 Tag dil kontrolu
- `tags_match_target_language(tags, target_lang)` dominant dil yaklasimi ile kontrol eder.
  - Referans: `apps/backend/services/language_policy_service.py:153`

### 6.2 Mismatch senaryosu
- Enrichment sonrasi `_language_mismatch_details(...)` ile summary/tag dil uyumu kontrol edilir.
  - Referans: `apps/backend/services/ai_service.py:154`
- Uyum bozuksa bir kez retry edilir.
  - Referans: `apps/backend/services/ai_service.py:224`, `apps/backend/services/ai_service.py:239`
- Hala bozuksa ve orijinal tag'ler hedef dildeyse orijinal tag seti sanitize edilip geri konur.
  - Referans: `apps/backend/services/ai_service.py:248`, `apps/backend/services/ai_service.py:249`

## 7) Veri Yazimi ve Indeksleme
### 7.1 Oracle AI store yazimi
- `_insert_content_tags(...)` tag'leri normalize edilmis sekliyle `TOMEHUB_CONTENT_TAGS` tablosuna yazar.
  - Referans: `apps/backend/services/ingestion_service.py:103`, `apps/backend/services/ingestion_service.py:110`
- `ingest_text_item(...)` akisinda:
  - `tags` JSON olarak `TOMEHUB_CONTENT.tags` alanina yazilir.
  - `prepare_labels(tags_json)` ile normalize label listesi cikartilir.
  - Sonra `_insert_content_tags` ile yan tabloya yazilir.
  - Referans: `apps/backend/services/ingestion_service.py:647`, `apps/backend/services/ingestion_service.py:686`, `apps/backend/services/ingestion_service.py:687`, `apps/backend/services/ingestion_service.py:710`
- `sync_highlights_for_item(...)` de benzer sekilde highlight tag'lerini yazar.
  - Referans: `apps/backend/services/ingestion_service.py:732`, `apps/backend/services/ingestion_service.py:789`, `apps/backend/services/ingestion_service.py:790`, `apps/backend/services/ingestion_service.py:813`

### 7.2 Frontend persist baglami
- Yeni item olustururken `Tags: ...` satiri text'e konup `/api/add-item` ile AI store'a da gonderilir.
  - Referans: `apps/frontend/src/App.tsx:265`, `apps/frontend/src/App.tsx:272`
- Enrichment sonucu Firestore item `tags` alanina merge edilip kaydedilir.
  - Referans: `apps/frontend/src/App.tsx:300`, `apps/frontend/src/App.tsx:323`

## 8) Tuketim Noktalari (UI / Arama / Analytics)
### 8.1 UI filtreleme ve kesif
- BookList'te kategori/tag filtrelemesi tag listesi uzerinden yapilir.
  - Referans: `apps/frontend/src/components/BookList.tsx:315`
- Serbest metin aramada tag alaninda da match aranir.
  - Referans: `apps/frontend/src/components/BookList.tsx:363`
- Top tags paneli hesaplanir/gosterilir.
  - Referans: `apps/frontend/src/components/BookList.tsx:419`, `apps/frontend/src/components/BookList.tsx:1021`

### 8.2 Dashboard ve istatistik
- Dashboard'ta top tag, category distribution ve bridge metriklerinde tag alanlari kullanilir.
  - Referans: `apps/frontend/src/components/dashboard/KnowledgeDashboard.tsx:113`, `apps/frontend/src/components/dashboard/KnowledgeDashboard.tsx:140`

### 8.3 Arama skoru etkisi
- Smart search katmaninda `Tags:` satirindan parse edilen tag'ler location boost alir (+15).
  - Referans: `apps/backend/services/smart_search_service.py:73`, `apps/backend/services/smart_search_service.py:258`, `apps/backend/services/smart_search_service.py:304`, `apps/backend/services/smart_search_service.py:337`

## 9) Sinirlar, Riskler ve Davranis Notlari
1. Prompt 3-5 tag ister; sanitize her durumda max 5'i enforce eder.
2. Dil mismatch'te retry + fallback var; yine de karma dil edge-case'leri olabilir.
3. LLM yaniti invalid JSON ise exception yolu calisir; endpoint 500 donebilir.
4. Batch stream 1MB limiti nedeniyle buyuk batchlerde erken kapanabilir (`limit_reached`).
5. `normalize_tags` validator'i AddItemRequest'te var; EnrichBookRequest icin ayrica zorlayici validator yok.
6. Frontend'de enrich sonucu Firestore'a yaziliyor; AI store ile birebir senkron her akista otomatik degil (akis-bazli).

## 10) Hata Senaryolari ve Fallback
- LLM timeout / servis hatasi: retry politikasi (`tenacity`) devreye girer; endpoint seviyesi exception 500 donebilir.
- Invalid JSON response: `clean_json_response + json.loads` hataya duser, loglanir.
- Bos/uygunsuz tag listesi: sanitize sonucu bos liste donebilir.
- Batch stream boyut limiti: istemci parcali sonuc alir, `limit_reached` mesajiyla sonlanir.

## 11) Kisa Iyilestirme Onerileri (Onceliklendirilmis)
1. `EnrichBookRequest.tags` icin de `normalize_tags` benzeri validator eklenmeli.
2. Enrichment sonrasi Firestore ve AI store tag senkronu net bir politika ile tek noktadan yonetilmeli.
3. Batch stream icin `limit_reached` durumunda istemciye "kalan is listesi" gibi devam mekanizmasi eklenmeli.
4. Tag kalite metrikleri (bos oran, dil mismatch oran, duplicate oran) izlenmeli.
5. Harici kaynak tag'leri icin (Google/OpenLibrary) canonicalization katmani eklenmeli.

## 12) Dogrulama Checklist'i
- [x] Rapor teknik iddialari dosya/endpoint referanslari ile izlenebilir.
- [x] UI -> API -> servis -> validasyon -> yazim -> tuketim zinciri kapsandi.
- [x] Tag adet/sanitize ve dil fallback davranislari aciklandi.
- [x] Hata/fallback senaryolari belgelendi.

---
Bu dokuman "as-is" davranisi anlatir; bu rapor kapsaminda kod sozlesmesi degistirilmemistir.
