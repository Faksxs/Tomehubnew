# Addendum Review (Mevcut Repo Durumu) - 2026-02-12

**Kapsam:** AS_IS_RAG_VS_SEARCH_AGENT_REPORT_2026-02-10_ADDENDUM.md iceriklerinin guncel repo ile karsilastirmasi.  
**Dil:** Turkce (ASCII)  
**Not:** Kod referansi/line yok; sadece servis/modul/akil yurutme.

---

## 1) RRF ve Fusion Durumu
**Durum:** Eskimis / Kismen dogru
**Gerekce:** Addendum, RRF yolunun tamamen devre disi oldugunu ve strict concat kullanildigini iddia ediyor. Guncel durumda fusion modu konfigurasyonla seciliyor; RRF yolu mevcut ve `concat` varsayilan. Yani rapordaki “RRF yok” ifadesi artik dogru degil, ancak varsayilan davranisin concat olmasi nedeniyle pratikte RRF devre disi kalabiliyor.
**Not:** Uretimde RRF acik mi kapali mi net degilse kalite/latency etkisi belirsiz kalir.

## 2) Graph Retrieval Kanal Kapsami
**Durum:** Dogru
**Gerekce:** `/api/search` hattinda graph retrieval aktifken `/api/smart-search` hattinda graph yok. Bu ayrim halen suruyor ve urun davranisini dogrudan etkiliyor.
**Not:** Kullanici beklentisi bu farki bilmiyorsa, “neden benzer sorgularda farkli sonuc” algisi olusabilir.

## 3) Graph Enrichment Mekanizmasi
**Durum:** Eskimis
**Gerekce:** Addendum, graph enrichment’i batch/script tabanli ve inline degil olarak tanimliyor. Guncel durumda ingestion sonrasi async graph enrichment tetikleyici mevcut (flag ile). Yani sadece batch degil, fire-and-forget enrichment var.
**Not:** Flag/limit dusukse pratikte yine “gec” algisi olabilir; ama “batch-only” artik dogru degil.

## 4) Semantic Router ve Route Secimi
**Durum:** Eskimis / Kismen dogru
**Gerekce:** Addendum, orchestrator’un statik tum-strateji kosumunda oldugunu soyluyor. Guncel repo, rule-based semantic router ile bucket secimi yapabiliyor. Yani “router yok” iddiasi guncel degil; ancak router’in kapsam/kalite etkisi halen sinirli olabilir.
**Not:** Router aktifse bile karar mantigi basit; kalitenin ana belirleyicisi hala retrieval ve fusion.

## 5) Query Expansion ve LLM Kullanimi
**Durum:** Dogru
**Gerekce:** Query expansion LLM tabanli ve kosullu. Tek kelime sorgularda expansion devreye girmiyor ve API key yoksa otomatik devre disi kalabiliyor.
**Not:** Bu, typo/tek kelime sorunlarinda beklenen recall artisini saglamaz.

## 6) Metadata / KPI Onerileri
**Durum:** Kismen dogru
**Gerekce:** Rapor, metadata alanlari ve KPI’lari oneriyor; guncel durumda bazi metadata alanlari zaten mevcut, ancak tum oneriler tam olarak uygulanmis degil. Bu nedenle “eksik var” yorumu genel olarak dogru, ama “hic yok” seklinde degil.
**Not:** Hangi alanlarin gercekten gormek istendigi urun kararini netlestirir.

## 7) Maliyet/Latency Tespitleri (Judge vs Work AI)
**Durum:** Kismen dogru
**Gerekce:** Judge servisinin agirligi rule-based verification’a kaymis ve LLM maliyeti sinirli. Maliyet artisinin ana surucusu Work AI retry olabilir; ancak bu, runtime telemetrisi olmadan %100 kesinlenemez.
**Not:** Kesinlik icin canli telemetry ve token usage metrikleri gerekir.

---

# Genel Degerlendirme
Addendum raporu, 2026-02-10 tarihi icin makul olabilir; ancak guncel repo ile bazi iddialar eskimis. En kritik farklar: RRF yolu mevcut, graph enrichment tetiklenebiliyor, router aktif.

# Gelistirilebilir / Eksik Kalanlar
1. RRF vs concat davranisinin uretimde netlestirilmesi (feature flag + telemetry).
2. `/api/search` ve `/api/smart-search` farkinin urun/dokuman seviyesinde netlestirilmesi.
3. Graph enrichment tetikleyicisinin etkisinin gorsellestirilmesi (state/coverage raporu).
4. Query expansion’in tek kelime/typo etkisinin sistematik ele alinmasi.

---

**Sonuc:** Raporun ana cikarimlari kismen hala gecerli, ancak bazi kritik “tespit” maddeleri guncel repo ile uyusmuyor.
