# Veritabanı Temizlik ve Optimizasyon Raporu

## 1. Kritik Sorunlar
*   **Yetim Kayıtlar:** 0 adet içerik parçası kütüphanede karşılığı olmadığı halde veritabanında yer kaplıyor. Bu, arama sırasında sistemin boş yere bu satırları taramasına neden olur.
*   **Eksik Vektörler:** 181 satır 'AI_ELIGIBLE' olarak işaretlenmiş ama anlamsal karşılığı (embedding) yok. Bu, arama kalitesini düşürür.

## 2. Gereksiz Tablolar (Silinebilir)
*   `TH_BKP_FSEEN_20260228` (0 satır)
*   `TOMEHUB_INGESTION_EVENTS` (0 satır)
*   `TOMEHUB_CONTENT_ODL_SHADOW` (0 satır)

## 3. Yedekleme Yükü
*   `TH_BKP_CTAGS_20260228` (581 satır)
*   `TH_BKP_FSEEN_20260228` (None satır)
