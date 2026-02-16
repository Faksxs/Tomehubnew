# TomeHub Ek Arastirma ve Karar Raporu (RRF, Graph Retrieval, Consistency, Router)
**Tarih:** 2026-02-10  
**Dil:** Turkce (ASCII)  
**Kapsam:** Kod degisikligi yok, kanit-temelli teknik degerlendirme + karar kapilari

## 1. Kisa Yonetici Ozeti
Bu ek rapor, onceki As-Is raporda acik kalan kritik sorulari kapatir.

Net sonuclar:
1. `SearchOrchestrator` bugun RRF kullanmiyor; `STRICT CONCATENATION` kullaniyor ve bu degisiklik 2026-02-04 tarihli `b952253` commit'i ile gelmis.
2. Graph retrieval, sadece oneride degil; `/api/search` hattinda aktif retrieval kanali. Ancak `/api/smart-search` hattinda graph yok.
3. `Ahlak -> Etik -> Vicdan` gibi graph komsuluk baglari teorik olarak getirilebilir; ama bunun onkosulu graph tablolari dolu olmali ve iliski skoru threshold'u gecmeli.
4. PDF ingest tarafi asenkron oldugu icin aramada eventual consistency var. Not/hightlight sync tarafi daha senkron. Graph enrichment ise inline degil, batch/script bagimli.
5. Explorer'daki maliyet artisinin ana nedeni Judge LLM degil, Work AI tekrar uretim denemeleri. Judge servisi agirlikla rule-based calisiyor.
6. Tam agent gecisi yerine hibrit yapinin korunup Semantic Router'in asamali eklenmesi en dogru risk/etki dengesi.

## 2. Yontem ve Kanit Kaynaklari
Degerlendirme asagidaki kaynaklardan yapildi:
- Endpoint zincirleri: `apps/backend/app.py`
- Arama orkestrasyonu: `apps/backend/services/search_system/orchestrator.py`
- Retrieval/RAG zinciri: `apps/backend/services/search_service.py`, `apps/backend/services/smart_search_service.py`
- Graph retrieval ve graph yazimi: `apps/backend/services/graph_service.py`, `apps/backend/scripts/build_graph.py`
- Ingestion ve commit davranisi: `apps/backend/services/ingestion_service.py`
- Explorer dual-AI dongusu: `apps/backend/services/dual_ai_orchestrator.py`, `apps/backend/services/judge_ai_service.py`
- Tarihsel degisim: `git blame` + `git show` (commit `b952253`)
- Sentetik ranking deneyi: `compute_rrf(...)` ile concat vs RRF karsilastirma calistirildi.

## 3. RRF Neden Yok? Kok Neden, Etki, Aciliyet
### 3.1 Mevcut durum (kesin bulgu)
- Orchestrator dosyasi acikca `No RRF` diyor: `apps/backend/services/search_system/orchestrator.py:140`.
- `compute_rrf` import ediliyor ama orchestrator'da cagrilmiyor: `apps/backend/services/search_system/orchestrator.py:7`.
- Sonuclar `bucket_exact -> bucket_lemma -> bucket_semantic` seklinde strict birlestiriliyor: `apps/backend/services/search_system/orchestrator.py:177`, `apps/backend/services/search_system/orchestrator.py:180`, `apps/backend/services/search_system/orchestrator.py:183`.

### 3.2 Ne zaman degisti?
- `git blame` gosteriyor: strict concat blogu `b952253` commit'i ile eklenmis (2026-02-04).
- Onceki surumde intent-aware weighted RRF vardi (`git show b952253^:.../orchestrator.py`):
  - `base_weights` hesaplama
  - `final_weights` uretme
  - `rrf_scores = compute_rrf(rankings, weights=final_weights)`

### 3.3 Muhtemel neden (inference)
Kod degisiminden cikan teknik niyet:
- Deterministik oncelik sirasi zorlamak (EXACT > LEMMA > SEMANTIC)
- Source type bazli UI/urun onceligi (highlight/insight/comment boost)
- Semantik gurultuyu bastirmak

Bu inference, dogrudan kod davranisina dayali; commit mesaji nedeni aciklamiyor.

### 3.4 Kalite etkisi (sentetik deney)
Calistirilan sentetik senaryoda:
- RRF siralamasinda merkezi belgeler ustte geliyor.
- Strict concat'ta `A_noise` benzeri bir exact sonucu 1. siraya kilitlenebiliyor.

Ornek cikti:
- RRF ilk 3: `B_mid`, `C_good`, `A_noise`
- Concat ilk 3: `A_noise`, `B_mid`, `C_good`

Bu, hibrit aramada fusion olmadan ranking kalitesinin bozulabilecegini dogrular.

### 3.5 Aciliyet seviyesi
- `/api/smart-search` icin: **Yuksek** (dogrudan retrieval kalitesi etkileniyor)
- `/api/search` icin: **Orta-Yuksek** (ustte ek graph + scoring katmanlari var ama temel retrieval kalitesi yine etkili)

## 4. Graph Sadece Oneri mi, Yoksa Retrieval mi?
### 4.1 Kesin cevap
- `/api/search` hattinda graph retrieval aktif:
  - `get_rag_context(...)` icinde vector ve graph paralel kosuyor: `apps/backend/services/search_service.py:565`, `apps/backend/services/search_service.py:584`
  - Graph sonuclari `GRAPH_RELATION` olarak merge ediliyor: `apps/backend/services/search_service.py:626`
- `/api/smart-search` hattinda graph retrieval yok:
  - Endpoint dogrudan `perform_search` (smart_search_service) cagiriyor: `apps/backend/app.py:916`, `apps/backend/services/smart_search_service.py:173`
  - Bu zincirde `get_graph_candidates(...)` cagrisi yok.

### 4.2 Graph query expansion mi?
- Hayir. Graph, query expansion degil, ayri bir retrieval kanali.
- Query expansion LLM tabanli ayri servisle yapiliyor: `apps/backend/services/query_expander.py:27`.
- Graph kanali `get_graph_candidates(...)` ile concept traversal yapip chunk getiriyor: `apps/backend/services/graph_service.py:269`.

## 5. "Ahlak" Sorgusunda Graph Komsulari Gelebilir mi?
### 5.1 Teknik olarak evet (kosullu)
`/api/search` icin akisin karar agaci:
1. Entry concept bulunur (`find_concepts_by_text`): `apps/backend/services/graph_service.py:302`
2. Bulunamazsa query uzerinden concept extraction fallback'i: `apps/backend/services/graph_service.py:309`
3. Hala yoksa concept description embedding fallback'i: `apps/backend/services/graph_service.py:317`
4. Bulunan entry conceptlerden komsu relation traversal yapilir: `apps/backend/services/graph_service.py:354`
5. `final_graph_score >= 0.5` olan chunklar tutulur: `apps/backend/services/graph_service.py:410`, `apps/backend/services/graph_service.py:413`
6. Sonuclar `/api/search` contextine merge edilir: `apps/backend/services/search_service.py:617`

Dolayisiyla `Ahlak -> Etik -> Vicdan` tipi baglar, graph tablolari doluysa ve skor threshold'u gecerse gelebilir.

### 5.2 Neden bazen gelmeyebilir?
- Graph tablolari bos veya stale olabilir.
- Relation tipi/weight dusuk olup 0.5 esigini gecemeyebilir.
- Sorgu concept mapping asamasinda entry concept bulunamayabilir.
- `/api/smart-search` kullaniliyorsa graph zaten devrede degil.

## 6. Ingestion, Freshness ve Consistency Riski
### 6.1 PDF ingest (asenkron)
- `/api/ingest` background task ile calisiyor: `apps/backend/app.py:1166`, `apps/backend/app.py:1217`
- Durum endpoint'i var: `/api/books/{book_id}/ingestion-status` -> `apps/backend/app.py:1240`
- Sonuc: PDF ekleme ile aramada gorunurluk arasinda dogal bir bekleme penceresi var (eventual consistency).

### 6.2 Add-item / highlight / personal-note (daha senkron)
- `ingest_text_item`, `sync_highlights_for_item`, `sync_personal_note_for_item` commit ederek donuyor:
  - `apps/backend/services/ingestion_service.py:586`
  - `apps/backend/services/ingestion_service.py:687`
  - `apps/backend/services/ingestion_service.py:778`

Bu nedenle vector/content aranabilirlik genelde islem donusune daha yakin.

### 6.3 Graph freshness kritik bulgusu
- `save_to_graph(...)` tanimli: `apps/backend/services/graph_service.py:75`
- Ingestion akisinda inline cagri kaniti yok.
- Graph yazimi batch scriptte goruluyor: `apps/backend/scripts/build_graph.py:15`, `apps/backend/scripts/build_graph.py:82`

Sonuc: `vector_ready` ve `graph_ready` zamani ayrisiyor. Kullanici notu hemen bulabilir ama graph iliski zenginlestirmesi gec gelebilir.

## 7. Explorer Latency ve Maliyet
### 7.1 Mevcut kontrol mekanigi
- `max_attempts=2`: `apps/backend/services/dual_ai_orchestrator.py:17`
- Explorer timeout: `45s`: `apps/backend/services/dual_ai_orchestrator.py:196`
- Fast-track kosullarinda Judge atlanabiliyor: `apps/backend/services/dual_ai_orchestrator.py:75`, `apps/backend/services/dual_ai_orchestrator.py:77`

### 7.2 Maliyet gercegi
- Judge servisi agirlikla rule-based verification kullaniyor: `apps/backend/services/judge_ai_service.py:337`
- Bu nedenle token maliyet artisinin ana surucusu Work AI yeniden uretim denemeleri.

### 7.3 Urun riski
- Explorer teknik olarak kaliteli olsa bile p95 gecikme yuksekse urun kullanimi duser.
- Bu ozellik icin karar metrigi kalite tek basina degil: `quality_gain / latency_cost` ve kullanici terk oranina etkisi.

## 8. Semantic Router Gerekli mi?
### 8.1 Bugunki durum
- Kismi routing var:
  - Analitik short-circuit var: `apps/backend/app.py:392`
  - Intent classification var: `apps/backend/services/epistemic_service.py:147`
- Ama search orchestrator halen statik sekilde coklu strateji kosuyor: `apps/backend/services/search_system/orchestrator.py:83`

### 8.2 Karar
- Tam autonomous agent'a gecis simdilik onerilmez.
- Ancak bir `Semantic Router v1` (rule-based + intent tabanli) **gerekli**:
  - Basit/fact sorgu -> keyword/sql agirlik
  - Kavramsal/felsefi sorgu -> vector + graph agirlik
  - Analitik sayim -> dogrudan analytics pipeline

### 8.3 Neden simdi?
- Statik tum-strateji kosumu hem latency hem maliyet hem de ranking gurultusu uretiyor.
- Router ile gereksiz strateji kosulari azaltilabilir.

## 9. Tam Gecis mi Hibrit mi? (Karar Matrisi)
1. Full "RAG kapat + full agent" gecisi: **Hayir** (urun vaadini ve izlenebilir kaynak cevabini zayiflatir)
2. Mevcut hibritin korunmasi: **Evet**
3. Hedefli augmentation (RRF iyilestirme + router + graph freshness): **Evet**

Nihai mimari yon: **replace degil, layered augmentation**.

## 10. Onerilen Duzeltme Backlog'u (Kodlama Oncesi Karar Hazirligi)
### P0 (hemen, yuksek etki)
1. `retrieval_fusion_mode` icin feature flag tasarla (`concat|rrf`).
2. Offline eval seti ile concat vs RRF kalite karsilastirmasi yap.
3. `/api/smart-search` metadata'ya retrieval path/fusion bilgisini ekleme taslagi cikar.

### P1 (kisa vade)
1. Graph freshness SLA modeli: `vector_ready`, `graph_ready`, `fully_ready` durumlari.
2. Graph enrichment'i batch-only modelden event-driven modele tasima fizibilitesi.
3. Explorer icin latency budget cap: p95 asiminda attempt/router kurali.

### P2 (orta vade)
1. Semantic Router v1 (rule-based) devreye alma.
2. Router v2 (hafif LLM router) sadece gerekli kaldigi noktalarda.
3. A/B ile kalite-latency-maliyet dengesi optimizasyonu.

## 11. KPI ve Olcum Plani
Asagidaki KPI'lar olmadan karar verilmemeli:
1. Search kalite: nDCG@k / MRR / source-groundedness
2. Latency: p50/p95 (ayri: `/api/search`, `/api/smart-search`, Explorer)
3. Maliyet: query basi token ve compute maliyeti
4. Freshness: ingest->search gorunurluk suresi (vector vs graph ayri)
5. Reliability: degradation rate, timeout rate, fallback rate

## 12. Test Senaryolari (Bu Rapor Kapsaminda Cevaplanan)
1. `/api/search` vs `/api/smart-search`: graph farki netlesti.
2. `Ahlak` benzeri sorgu: graph komsu retrieval kosullu olarak mumkun.
3. PDF ingest: eventual consistency var.
4. Not/sync ingest: commit-sonrasi vector aranabilirlik daha hizli.
5. Graph enrichment: inline degil, batch/script bagimli.
6. Explorer maliyet: Judge degil, Work retry agirlikli.
7. RRF eksigi: kalite riski teknik olarak dogrulandi.
8. Semantic router: gerekli ama asamali uygulanmali.

## 13. Public API / Type Etkisi (Bu Asamada)
- Uygulanan degisiklik: **YOK**
- Oneri olarak dusunulen metadata alanlari:
  - `retrieval_fusion_mode` (`concat|rrf`)
  - `retrieval_path` (`keyword|lemma|semantic|graph|hybrid`)
  - `index_freshness_state` (`vector_ready|graph_ready|fully_ready`)
  - `audit_cost_profile` (`attempts`, `latency_ms`, `estimated_tokens`)

## 14. Nihai Karar Cumleleri
1. RRF'nin su an devre disi olmasi kritik bir kalite riskidir; en azindan flagli geri alim/A-B ile acilen test edilmelidir.
2. Graph retrieval TomeHub'da gercektir, ama yalnizca belirli hatlarda aktiftir (`/api/search`); bu fark urun diliyle acik anlatilmalidir.
3. "Ahlak" tipi kavramsal sorgularda graph komsulari gelebilir; ancak graph freshness ve score threshold kosullarina baglidir.
4. Ingestion tarafinda vector ve graph hazir olma zamani ayrik oldugu icin consistency sozlesmesi (SLA/metadata) zorunludur.
5. Explorer maliyet optimizasyonu Work AI retry kontrolune odaklanmalidir; Judge tarafi ikincil etkidir.
6. Mimari yon tam gecis degil, hibritin korunup router + fusion + freshness katmanlariyla guclendirilmesidir.

---

## Notlar
- Bu rapor kod ve git gecmisi incelemesine dayanir.
- Bu turda repository'de uygulama kodu degistirilmemistir.
- Runtime metriklerin p50/p95 seviyesinde kesinlenmesi icin canli trafik veya kontrollu benchmark kosumu sonraki adimdir.


