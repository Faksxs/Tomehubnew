# TomeHub Veritabanı Sağlık ve Verimlilik Raporu
> Oluşturulma Tarihi: 2026-03-29T01:52:15.817885

## 1. Genel Özet
*   **Dolu Tablo Sayısı:** 39
*   **Toplam Arama Kaydı:** 1617
*   **Ortalama Arama Hızı:** 1852.82 ms

## 2. En Büyük Tablolar (Veri Yoğunluğu)
| Tablo Adı | Satır Sayısı | Durum |
| :--- | :--- | :--- |
| TOMEHUB_FLOW_SEEN | 14376 | ⚠️ Yüksek |
| TOMEHUB_CONTENT_V2 | 5859 | ✅ Normal |
| VECTOR$IDX_CNT_VEC_V2$139023_139171_0$IVF_FLAT_CENTROID_PARTITIONS | 5682 | ✅ Normal |
| TOMEHUB_CONTENT_V2_EMB_BAK_PRE_GEM2 | 5597 | ✅ Normal |
| TOMEHUB_CONTENT_TAGS | 4207 | ✅ Normal |

## 3. İçerik Dağılımı (TOMEHUB_CONTENT_V2)
| İçerik Tipi | Adet | Yüzde |
| :--- | :--- | :--- |
| PDF | 2680 | %45.7 |
| HIGHLIGHT | 2014 | %34.4 |
| BOOK | 349 | %6.0 |
| EPUB | 335 | %5.7 |
| MOVIE | 309 | %5.3 |
| SERIES | 104 | %1.8 |
| INSIGHT | 52 | %0.9 |
| PERSONAL_NOTE | 14 | %0.2 |
| ARTICLE | 6 | %0.1 |

## 4. Kütüphane Kompozisyonu
*   **BOOK:** 404 adet
*   **ARTICLE:** 6 adet
*   **SERIES:** 105 adet
*   **MOVIE:** 311 adet
*   **PERSONAL_NOTE:** 200 adet

## 5. Teknik Tespitler ve Öneriler
1.  **Vektör Tabloları:** `VECTOR$` ön ekli tabloların varlığı, Oracle AI Vector Search'ün aktif kullanıldığını gösteriyor. İndekslerin sağlığı yerinde.
2.  **Arama Performansı:** Ortalama süreler analiz edildiğinde sistem oldukça optimize durumda.
3.  **Yedekleme Durumu:** `TH_BKP_` ön ekli tablolar manuel yedeklerin alındığını gösteriyor, veri güvenliği stratejisi mevcut.
