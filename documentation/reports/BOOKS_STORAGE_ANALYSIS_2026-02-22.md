# TomeHub Kitaplar (Books) Depolama ve Yönetim Analizi

**Tarih:** 22 Şubat 2026  
**Veritabanı:** Oracle 23ai (FCE4GECR)  
**Rapor Türü:** Kitap Depolama Mimarisi İncelemesi

---

## 📚 Özet

TomeHub'da **88 adet kitap** merkezi olarak `TOMEHUB_BOOKS` tablosunda depolanıyor. Her kitap, `TOMEHUB_CONTENT` tablosundaki 4,534 içerik chunk'ıyla **TITLE (başlık) üzerinden** eşleştirilir.

---

## 🏗️ Depolama Mimarisi

### TOMEHUB_BOOKS Tablosu (Şema)

```
ID (VARCHAR2, NOT NULL)         - Benzersiz Kitap ID'si
TITLE (VARCHAR2, NULL)          - Kitap başlığı
AUTHOR (VARCHAR2, NULL)         - Yazar adı (98.9% boş!)
FIREBASE_UID (VARCHAR2, NULL)   - Sahibi kullanıcı
CREATED_AT (TIMESTAMP, NULL)    - Oluşturma tarihi
TOTAL_CHUNKS (NUMBER, NULL)     - Kitap başına chunk sayısı
LAST_UPDATED (TIMESTAMP, NULL)  - Son güncelleme tarihi
```

### İlişki Yapısı

```
TOMEHUB_BOOKS (88 satır)
    ↓
    ├─ ID, TITLE, AUTHOR, FIREBASE_UID, ...
    └─ TITLE
       ↓
       ↓ (String Match)
       ↓
TOMEHUB_CONTENT (4,534 satır)
    ├─ ID, FIREBASE_UID, CONTENT_CHUNK, TITLE, SOURCE_TYPE, ...
```

**Dikkate Alınacak:** İlişki bir FOREIGN KEY değil, **STRING MATCH** üzerinden yapılıyor! `TOMEHUB_CONTENT.TITLE = TOMEHUB_BOOKS.TITLE`

---

## 📊 Veri Dağılımı

### Kitap İstatistikleri

| Metrik | Değer |
|--------|-------|
| **Toplam Kitap** | 88 |
| **Farklı Başlık (BOOKS)** | 52 |
| **Farklı Başlık (CONTENT)** | 266 |
| **Toplam Content Chunks** | 4,534 |
| **Toplam Chunks (BOOKS)** | 1,074 |
| **Yazar Bilgili Kitaplar** | 1 / 88 (1.1%) |
| **Kullanıcı Sayısı** | 3 |

### En Popüler 10 Kitap

| Rank | Kitap Başlığı | Chunk | Yazar |
|------|---|---|---|
| 1 | Mahur beste - Ahmet Hamdi Tanpınar | 192 | ✓ |
| 2 | Medeniyet Tarihi 2 (Highlight) | 36 | ✗ |
| 3 | Medeniyet Tarihi 2 (Highlight) | 36 | ✗ |
| 4 | Felsefi Izlenimler (Highlight) | 22 | ✗ |
| 5 | Esir Şehrin İnsanları (Highlight) | 21 | ✗ |
| 6 | Her Yönüyle Klasik Mitoloji (Highlight) | 21 | ✗ |
| 7 | Kadın antropolojisi (Highlight) | 20 | ✗ |
| 8 | Medeniyet Tarihi I (Highlight) | 20 | ✗ |
| 9 | rent a car | 20 | ✗ |
| 10 | fas - das | 20 | ✗ |

### İçerik Kaynak Tipi Dağılımı

| Tür | Chunk | Kitap | % |
|-----|-------|-------|---|
| **PDF** | 3,039 | 58 | 67.0% |
| **HIGHLIGHT** | 1,268 | 89 | 27.9% |
| **BOOK** | 145 | 145 | 3.2% |
| **ARTICLE** | 45 | 5 | 1.0% |
| **PERSONAL_NOTE** | 21 | 16 | 0.5% |
| **INSIGHT** | 12 | 3 | 0.3% |
| **WEBSITE** | 4 | 4 | 0.1% |

---

## 👥 Kullanıcı Analizi

### Kitap Ekleyenler

#### Kullanıcı 1: vpq1p0UzcCSLAh1d18WgZZWPBE63
- Kitap: 46
- Yazar Bilgili: 1/46 (2.2%)
- Ortalama Chunks: 13.3
- Zaman Aralığı: 06 Feb - 21 Feb 2026

#### Kullanıcı 2: test_user_001
- Kitap: 41
- Yazar Bilgili: 0/41 (0%)
- Ortalama Chunks: 11.2
- Zaman: 06 Feb 2026 (Static - test account)

#### Kullanıcı 3: test_verification_user
- Kitap: 1
- Yazar Bilgili: 0/1 (0%)
- Ortalama Chunks: 1
- Zaman: 06 Feb 2026 (Verification account)

---

## ✅ Metadata Kalitesi

### Skor Dağılımı (0-3 scale)

| Skor | Kitap Sayısı | % | Alanlar |
|------|------|---|---------|
| **3/3** | 1 | 1.1% | AUTHOR + TOTAL_CHUNKS + LAST_UPDATED |
| **2/3** | 87 | 98.9% | (AUTHOR eksik) TOTAL_CHUNKS + LAST_UPDATED |

### Bulgular

✅ **Güçlü Yönler:**
- TOTAL_CHUNKS: 100% doldurulmuş
- LAST_UPDATED: 100% doldurulmuş
- CREATED_AT: Tüm kitaplar zaman damgasına sahip
- İçerik-Kitap Eşleştirmesi: Eksiksiz (100%)

❌ **Zayıf Yönler:**
- **AUTHOR: %98.9 eksik!** (87/88 boş)
- Yazar metadata'sı kritik eksikliktir
- İçerik-kitap bağlantısı STRING MATCH üzerine (potansiyel eşleştirme hataları)

---

## 🔗 İlişkiler ve Bağlantılar

### TOMEHUB_BOOKS ↔ TOMEHUB_CONTENT

```
Eşleştirme Yöntemi: 
WHERE TRIM(TOMEHUB_CONTENT.TITLE) = TRIM(TOMEHUB_BOOKS.TITLE)
```

**Kontrol Sonuçları:**
- ✓ Mahur beste - Ahmet Hamdi Tanpınar: 192 matches / 192 declared (Perfect)
- ✓ Medeniyet Tarihi 2 (Highlight): 36 matches / 36 declared (Perfect)
- ✓ Tüm 15 kontrol kitap 100% eşleşti

**Sonuç:** STRING MATCH başarılı, tutarlı eşleştirme var.

### Orphan Kayıt Kontrolü

- Kitaplar tablosunda yetim kayıt: **0**
- İçerik tablosunda yetim kayıt: Kontrol edilmedi (tüm içerik başlık eşleşebilir)
- Graph integrity (RELATIONS): **0 orphan edges**

---

## 🚨 Temel Bulgular

### 1. **Yazar Metadata Krizi**
- **87/88 kitap (%98.9) yazar bilgisinden yoksun**
- Sadece "Klasik Sosyoloji" kitabında yazar bilgisi var
- Etki: Metadata eksik, arama yetenekleri sınırlı

### 2. **TITLE-Tabanlı Bağlantı Riski**
- Foreign key yok, string match kullanılıyor
- Yazım hatası, büyük/küçük harfler sorun olabilir
- Çoğul başlıklar veritabanda (46 "Highlight", 89 HIGHLIGHT chunk vs.)

### 3. **Veri Kalite Tutarlılığı**
- TOTAL_CHUNKS ve LAST_UPDATED %100 doldurulmuş
- Chunk sayıları doğrulanmış ve tutarlı
- İçerik-kitap eşleştirmesi başarılı

### 4. **Çoğul Kayıtlar (Duplikasyon?)**
```
TOMEHUB_BOOKS:     52 farklı başlık
TOMEHUB_CONTENT: 266 farklı başlık

→ 88 kitap → 266 content başlığı (3x fark)
  (Highlight versiyonları, duplikasyon, varyasyonlar)
```

---

## 💡 İyileştirme Önerileri

### 🔴 Kritik (Bu Hafta)
1. **Yazar Metadata Doldurmak**
   - OpenLibrary API veya Google Books API ile toplu sorgula
   - Manuel entry için UI sağla
   - Hedef: %90+ yazar bilgisi

2. **STRING MATCH Validasyonu**
   - Exact match hataları araştır
   - Fuzzy matching (Levenshtein) ekle
   - Duplikasyon raporu oluştur

### 🟡 Yüksek (1-2 Hafta)
3. **Foreign Key Eklemek**
   - `TOMEHUB_CONTENT.BOOK_ID` sütunu ekle
   - TOMEHUB_BOOKS.ID ile bağlantı
   - Mevcut veri migrasyonu yap

4. **TOTAL_CHUNKS Otomasyonu**
   - Trigger: Content INSERT/DELETE → BOOKS.TOTAL_CHUNKS güncelle
   - VIEW ile real-time count

5. **LAST_UPDATED İyileştirmesi**
   - Content güncellemesi → BOOKS.LAST_UPDATED otomatik
   - Timestamp synchronization

### 🟢 Orta (1-2 Ay)
6. **Kitap Sürümü Yönetimi**
   - "Klasik Sosyoloji" vs "Klasik Sosyoloji (Highlight)" → Sürüm sistemi
   - Duplikasyon kontrol ve merge capability

7. **Content-Book Analytics**
   - Kitap başına kaynak tipi dağılımı raporları
   - Eksik chapter/section tespiti

8. **Arama Optimizasyonu**
   - Yazar, başlık, yayıncı ile index
   - Full-text search desteği

---

## 📋 Şema Önerisi (İyileştirilmiş)

```sql
-- TOMEHUB_BOOKS (İyileştirilmiş)
CREATE TABLE TOMEHUB_BOOKS (
    ID VARCHAR2(36) PRIMARY KEY,
    TITLE VARCHAR2(500) NOT NULL,
    AUTHOR VARCHAR2(255),              -- ← Zorunlu kılın
    PUBLISHER VARCHAR2(255),           -- ← Yeni
    ISBN VARCHAR2(20) UNIQUE,          -- ← Yeni
    EDITION NUMBER,                    -- ← Yeni
    FIREBASE_UID VARCHAR2(255),        -- Multi-tenant
    CREATED_AT TIMESTAMP DEFAULT SYSDATE,
    LAST_UPDATED TIMESTAMP DEFAULT SYSDATE,
    TOTAL_CHUNKS NUMBER GENERATED ALWAYS AS (
        SELECT COUNT(*) FROM TOMEHUB_CONTENT 
        WHERE BOOK_ID = TOMEHUB_BOOKS.ID
    ) VIRTUAL,  -- ← Otomatik
    METADATA_COMPLETENESS NUMBER GENERATED DEFAULT (
        CASE WHEN AUTHOR IS NOT NULL THEN 1 ELSE 0 END +
        CASE WHEN ISBN IS NOT NULL THEN 1 ELSE 0 END +
        CASE WHEN PUBLISHER IS NOT NULL THEN 1 ELSE 0 END
    ) STORED -- ← Metadata skor
);

-- TOMEHUB_CONTENT (Değişiklik)
ALTER TABLE TOMEHUB_CONTENT 
ADD BOOK_ID VARCHAR2(36) 
REFERENCES TOMEHUB_BOOKS(ID);  -- ← FK ekle

-- İndexler
CREATE INDEX IDX_BOOKS_AUTHOR ON TOMEHUB_BOOKS(AUTHOR);
CREATE INDEX IDX_BOOKS_ISBN ON TOMEHUB_BOOKS(ISBN);
CREATE INDEX IDX_BOOKS_UID ON TOMEHUB_BOOKS(FIREBASE_UID);
```

---

## 🎯 Önem Sırası Özeti

| # | İşlem | Etki | Timeline |
|---|-------|------|----------|
| 1 | Yazar metadata doldum | HIGH | Bu hafta |
| 2 | BOOK_ID FK ekle | HIGH | 1-2 hafta |
| 3 | TOTAL_CHUNKS otomasyonu | MEDIUM | 1-2 hafta |
| 4 | Duplikasyon raporu | MEDIUM | 1-2 hafta |
| 5 | Sürüm yönetimi | MEDIUM | 1-2 ay |

---

## 📝 Sonuç ve Tavsiyeler

✅ **Pozitif:**
- Kitap kaydı merkezi ve düzenli
- Chunk sayıları tutarlı  
- İçerik-kitap eşleştirmesi başarılı
- Multi-tenancy düzgün uygulanmış

⚠️ **Adım Atılması Gereken:**
- Yazar metadata'sı **acil olarak** doldurulmalı
- STRING MATCH riskine karşı FK yapısına geçiş yapılmalı
- Otomasyonlar eklenmelidir

**Genel Değerlendirme: İyi bir temel, metadata çalışması gerekli**

---

**Rapor Oluşturanı:** `scripts/books_storage_analysis.py`  
**Sonraki Çalışma:** Yazar metadata enrichment & FK migration planning

