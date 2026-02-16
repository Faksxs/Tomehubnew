# TomeHub As-Is Sistem Anlama Raporu (Kod Degisikligi Yok)
**Tarih:** 2026-02-10  
**Dil:** Turkce  
**Kapsam:** As-is mimari + karar dokumani (uygulama kodunda degisiklik yok)

## 1. Amac ve Kapsam
Bu rapor, TomeHub'in mevcut sistemini kod degisikligi yapmadan anlamak ve "RAG vs search-agent" iddiasini mimari gerceklik uzerinden degerlendirmek icin hazirlanmistir. Degerlendirme, repository'deki guncel endpoint akislari, servis implementasyonlari, veri modeli ve urun politikasi belgelerine dayanmaktadir.

## 2. As-Is Mimari Haritasi
### 2.1 Ana endpoint ayrimi
- `apps/backend/app.py:358` -> `/api/search` (RAG tabanli cevap uretimi)
- `apps/backend/app.py:496` -> `/api/chat` (stateful chat, Explorer secenegi)
- `apps/backend/app.py:916` -> `/api/smart-search` (retrieval odakli sonuc listesi)

### 2.2 `/api/search` akisi (RAG Answer Pipeline)
- Endpoint, `generate_answer(...)` cagirir: `apps/backend/app.py:462`
- `generate_answer`, `get_rag_context(...)` ile retrieval yapar: `apps/backend/services/search_service.py:744`, `apps/backend/services/search_service.py:534`
- `get_rag_context`, retrieval icin `perform_search(...)` kullanir: `apps/backend/services/search_service.py:570`
- `perform_search`, `SearchOrchestrator` baslatir: `apps/backend/services/smart_search_service.py:173`, `apps/backend/services/smart_search_service.py:188`

### 2.3 `/api/smart-search` akisi (Retrieval Layer)
- Dogrudan `perform_search(...)` cagrilir: `apps/backend/app.py:935`
- Sonuc: `results + metadata` (LLM answer generation yok)

### 2.4 `/api/chat` + Explorer akisi
- Explorer secimi `chat_request.mode == 'EXPLORER'` ile yapilir: `apps/backend/app.py:647`
- Explorer modunda `get_rag_context(...)` + `generate_evaluated_answer(...)` zinciri calisir: `apps/backend/app.py:675`, `apps/backend/app.py:688`
- Bu zincir Work AI + Judge AI degerlendirme/yeniden deneme mantigi icerir: `apps/backend/services/dual_ai_orchestrator.py`

### 2.5 Search Orchestrator akisi (kritik bulgu)
- Paralel strateji kosumu var: `ThreadPoolExecutor(max_workers=6)` -> `apps/backend/services/search_system/orchestrator.py:83`
- Query expansion var: `apps/backend/services/query_expander.py:27`
- Stratejiler: exact, lemma, semantic (`SemanticMatchStrategy`) -> `apps/backend/services/search_system/strategies.py:206`
- Ancak mevcut dosyada final birlestirme "STRICT CONCATENATION & DEDUPLICATION (No RRF)" olarak geciyor: `apps/backend/services/search_system/orchestrator.py:140`

### 2.6 Flow sistemi (kesif motoru)
- Flow mode/horizon modeli: `apps/backend/models/flow_models.py:13`, `apps/backend/models/flow_models.py:27`
- Serviste zone/horizon/pivot mekanigi: `apps/backend/services/flow_service.py:180`, `apps/backend/services/flow_service.py:373`, `apps/backend/services/flow_service.py:949`, `apps/backend/services/flow_service.py:1069`
- API katmani: `apps/backend/routes/flow_routes.py:36`, `apps/backend/routes/flow_routes.py:82`

## 3. Arama Katmanlari Karsilastirmasi
### 3.1 `/api/search`
- Amac: kaynakli cevap uretmek
- Retrieval + generation birlikte
- Kullaniciya "answer + sources" dondurur

### 3.2 `/api/smart-search`
- Amac: retrieval sonuclarini dogrudan gostermek
- LLM answer generation yok
- Sonuclar daha "arama motoru" tipi

### 3.3 `/api/chat` (Explorer)
- Amac: derin, denetlenen, cok adimli cevap kalitesi
- Retrieval + Work/Judge degerlendirme
- Maliyet ve gecikme daha yuksek, kalite kontrolu daha yuksek

## 4. "Search-agent mantigi var mi?" Teknik Yanit
### 4.1 Var olanlar
- Coklu retrieval stratejisi orkestrasyonu var
- Query expansion var
- Explorer'da self-evaluation ve regenerate karari var
- Flow'da horizon ve pivot ile yarim-otonom kesif var

### 4.2 Olmayanlar (tam agent tanimi)
- Genel arama hattinda arac secip iteratif tool-calling yapan planner-agent yok
- Retrieval -> evaluate -> yeni tool karari dongusu standart aramada yok
- "Autonomous agentic search" yerine "orchestrated hybrid retrieval" var

### 4.3 Sonuc
TomeHub'da **search-agent benzeri prensipler** var, ama sistemin cekirdegi **tam agentic search** degil; bugun icin baskin desen **hibrit orkestrasyonlu RAG/retrieval**.

## 5. Gorseldeki Iddialarin Dogruluk Analizi
### Iddia A: "En iyi RAG, olu RAG"
- Degerlendirme (TomeHub baglaminda): **Yanlis (mutlak ifade olarak)**, **Kismen dogru (asiri karmasik RAG elestirisi olarak)**
- Gerekce:
  - TomeHub'in urun degeri "kaynaktan cevap" ve "kisisel kutuphane baglami" uzerine kurulu (`/api/search` + sources)
  - RAG tamamen kaldirilirsa cevabin dayanak kalitesi duser
  - Ancak asiri agir retrieval katmanlari sadeleştirilebilir

### Iddia B: "Metin dosyasi + search-agent daha yalin/hizli/etkin"
- Degerlendirme: **Kismen dogru**
- Gerekce:
  - Kod asistanlari gibi domainlerde bu model cok etkili olabilir
  - TomeHub'da ise morphology (lemma), semantic yakinlik, source_type politikasi, tenant izolasyonu, graph baglari gibi gereksinimler var
  - Salt metin dosyasi aramasi bu gereksinimlerin bir kismini kaybettirebilir

### Iddia C: "En fazla Postgres vector, fazlasi gereksiz"
- Degerlendirme: **TomeHub icin dogrudan uygulanamaz**
- Gerekce:
  - Mevcut yapi Oracle vector + property graph kullaniyor: `apps/backend/create_graph_schema.sql:8`, `apps/backend/create_graph_schema.sql:9`, `apps/backend/create_graph_schema.sql:35`
  - Buradaki karar "hangi DB" degil, "hangi retrieval davranisi" olmalidir

## 6. TomeHub Uygulama Felsefesi ile Uyum
Personal Notes V0.1 dokumani, urun felsefesini net cizer:
- Private/Daily notlar global RAG'e dahil edilmez
- Ideas notlari global search/AI/graph akislarina dahil edilir
- Referans: `documentation/reports/PERSONAL_NOTES_V0_1_YOL_HARITASI.md:30`, `documentation/reports/PERSONAL_NOTES_V0_1_YOL_HARITASI.md:36`, `documentation/reports/PERSONAL_NOTES_V0_1_YOL_HARITASI.md:37`, `documentation/reports/PERSONAL_NOTES_V0_1_YOL_HARITASI.md:95`

Bu nedenle "tek tip agentic arama" yerine "politika-duyarli hibrit retrieval" TomeHub felsefesine daha uyumludur.

## 7. Riskler ve Trade-off'lar (As-Is)
### 7.1 Guclu taraflar
- Endpoint ayrimi net: search / smart-search / chat-explorer
- Embedding tarafinda circuit breaker + fallback var: `apps/backend/services/embedding_service.py:45`, `apps/backend/services/embedding_service.py:174`, `apps/backend/services/embedding_service.py:177`, `apps/backend/services/embedding_service.py:269`
- Read/write pool ayrimi var: `apps/backend/infrastructure/db_manager.py:33`, `apps/backend/infrastructure/db_manager.py:47`

### 7.2 Kritik trade-off ve gozlemler
- Terminoloji drift'i: belgelerde "RRF fusion" vurgusu var, mevcut orchestrator dosyasi "No RRF" diyor (`apps/backend/services/search_system/orchestrator.py:140`)
- `/api/search` request modelinde `mode` var ama endpointte kullanilmiyor (`apps/backend/models/request_models.py:8`; kullanilan alanlar: `apps/backend/app.py:462`, `apps/backend/app.py:464`, `apps/backend/app.py:467`)
- Dev modda auth fallback davranisi var:
  - `apps/backend/middleware/auth_middleware.py:51`, `apps/backend/middleware/auth_middleware.py:63`, `apps/backend/middleware/auth_middleware.py:70`
  - Flow rotalarinda da body UID fallback mevcut: `apps/backend/routes/flow_routes.py:50`, `apps/backend/routes/flow_routes.py:90`

## 8. Entegrasyon Mantigi: Tam Gecis mi Hibrit mi?
### Karar
**Tam gecis (RAG'i kapat, full search-agent gec): onerilmez.**  
**Hibrit modelin korunmasi + hedefli agentic entegrasyon: onerilir.**

### Neden
- TomeHub urun vaadi: kaynakli, kullanici-kutuphanesi icinde, politika-duyarli cevap
- Bu vaatte retrieval kalite/izlenebilirlik en az generation kadar kritik
- Agentic search, ozellikle Explorer/Flow tarafinda yuksek deger uretebilir; ama ana search hattinda dogrudan yerine gecmesi erken ve riskli

## 9. Fazli Yol Haritasi (Kodsuz Karar Dokumani)
### Faz 0 (hemen, kodsiz analiz)
- Terminolojiyi netlestir: "RAG", "Smart Search", "Explorer", "Flow"
- Hangi hattin hangi problemi cozdugunu urun dilinde standardize et

### Faz 1 (pilot entegrasyon adayi)
- Agentic retrieval'i sadece Explorer veya Flow benzeri derin kesif senaryolarinda konumlandir
- Basit `/api/search` hattini hiz/istikrar odakli koru

### Faz 2 (olcum)
- 5 senaryo setiyle kalite, latency, maliyet, kaynak tutarliligi karsilastirmasi
- Karar metriigi: "kalite artisi / latency artisi" ve "hallucination riski"

### Faz 3 (standartlastirma)
- Basariliysa kontrollu rollout + metadata standardizasyonu
- Basarisizsa agentic katmani sadece niche (Explorer/Flow) modda tut

## 10. Test ve Senaryo Seti (Analiz Amacli, Kodsuz)
1. Ayni sorgu: `/api/search` vs `/api/smart-search` sonuc farki
2. Explorer modu: retrieval + evaluation + retry davranisi
3. Embedding degrade durumu: semantic fallback kalitesi
4. Ideas vs Private/Daily notlarin global aramaya etkisi
5. Kaynak gosterimi: cevap-iddia-kaynak tutarliligi

## 11. Public API / Interface / Type Etkisi
Bu rapor calismasinda uygulanan degisiklik:
- **YOK** (API/interface/type degisikligi yapilmamistir)

Opsiyonel ileri asama onerisi (sadece oneridir):
- metadata alanlari: `retrieval_mode`, `retrieval_steps`, `degradation_reason`, `agentic_path_used`

## 12. Yonetici Ozeti (Net Karar Cumleleri)
1. TomeHub bugun tam agentic search sistemi degildir; hibrit orkestrasyonlu retrieval + RAG sistemidir.
2. "RAG oldurulmeli" tezi TomeHub icin dogrudan dogru degildir; urun degerini zayiflatir.
3. Search-agent yaklasimi tamamen reddedilmemeli; Explorer/Flow gibi derin kesif modlarinda hedefli entegre edilmelidir.
4. Ana arama hattinda en dogru strateji: mevcut hibrit yapiyi koruyup olcum-temelli sadeleştirme yapmaktir.
5. Mimari yon: "replace" degil, "layered augmentation".

---

## Notlar
- Bu rapor statik kod ve dokuman incelemesine dayanir.
- Calisma kapsaminda endpoint canli trafik A/B testi kosulmamistir.
- Kod degisikligi yapilmamistir; sadece dokumantasyon ciktilari uretilmistir.
