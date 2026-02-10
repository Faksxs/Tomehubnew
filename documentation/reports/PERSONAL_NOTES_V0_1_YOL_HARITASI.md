# Personal Notes V0.1 Yol Haritasi (Mimariye Uyumlu Rapor)

Bu dokuman, mevcut TomeHub mimarisi (Books/Articles/Websites highlight akisi + Personal Notes) ile uyumlu olacak sekilde Personal Notes V0.1 kapsamini netlestirir.

## 1) Kapsam ve Urun Felsefesi

- Personal Notes, highlight sisteminden ayri bir "pratik not defteri" deneyimi olacak.
- Baslangicta sade ve hizli kullanim hedeflenir; editor derinlestirme sonraki iterasyonlara birakilir.
- Whiteboard/cizim ozelligi V0.1 kapsamindan cikarilmistir.

## 2) Kategori Modeli (Ana Karar)

V0.1'de Personal Notes icin 3 ana kategori:

1. `Private`
2. `Daily`
3. `Ideas`

Her not bir ana kategoriye bagli olur. Ek olarak alt klasor (sub-folder) desteklenir.

- Alt klasorler sadece duzenleme amaclidir.
- Yetki/erisim davranisi ana kategoriden miras alir.
- Yani alt klasor, ana kategori politikasini degistiremez.

## 3) Erisim ve Indeksleme Politikasi

| Alan | Private | Daily | Ideas |
|---|---|---|---|
| Personal Notes local search | Evet | Evet | Evet |
| Genel arama (global search/RAG) | Hayir | Hayir | Evet |
| AI icerik uretimi baglami | Hayir | Hayir | Evet |
| Graph node / graphrag | Hayir | Hayir | Evet |
| Vector indeksleme | Hayir | Hayir | Evet |

Not:
- `Private` ve `Daily` notlar yalnizca Personal Notes icerisindeki lokal aramada gorunur.
- `Ideas`, sistemde "paylasilabilir bilgi" sinifina girer; arama/AI/graph akislarina katilir.

## 4) Tag Kurali (Revizyon)

Tag olusumu AI tarafindan yapilir.

- Her tag **1 ile 4 kelime** arasinda olmalidir.
- Kisa, anlamsal ve tekrar etmeyen etiketler uretilmelidir.
- Ornek format:
  - `ahlaki gerilim`
  - `modern toplum`
  - `kimlik krizi`

Opsiyonel:
- Kullanici manuel tag ekleyebilir; AI tagleri ile birlestirilir.

## 5) Ağırliklandirma Kurali (Ideas vs Highlight)

- `Ideas` notlari global arama/AI'da kullanilsin.
- Ancak ayni konuya dair klasik highlight kayitlarina gore **biraz daha dusuk agirlik** alsin.
- Pratik onerilen baslangic:
  - Highlight taban puani: `1.00`
  - Ideas taban puani: `0.85 - 0.90` araligi

Bu oran daha sonra kalite metriklerine gore ayarlanir.

## 6) Geri Uyumluluk Karari

- Su an Personal Notes kayit sayisi dusuk oldugu icin (`~6`), V0.1'de kapsamli geri uyumluluk migrasyonu zorunlu degil.
- Gerekirse notlar yeniden eklenebilir.
- Buna ragmen sistemde tip/politika esleme katmani korunur (ileride veri buyurse migration kolay olsun diye).

## 7) V0.1 Editor Kapsami

V0.1 icin editorde minimum islev seti:

- Baslik + govde metni
- Bullet list
- Numbered list
- Checklist / checkbox
- Kalin, italik, alti cizili temel bicimlendirme

Detayli editor optimizasyonu V0.2+ fazina birakilir.

## 8) Mimari Esleme (Frontend -> Backend/DB)

Frontend kavramlari:
- `Personal Notes` (UI not defteri)
- Ana kategori: `Private | Daily | Ideas`
- Alt klasor yolu: `folderPath` (opsiyonel)

Backend/DB karsiliklari (onerilen):
- `resource_type = PERSONAL_NOTE`
- `note_category = PRIVATE | DAILY | IDEAS`
- `folder_path` (text)
- `is_local_only`:
  - `true` for Private/Daily
  - `false` for Ideas
- `index_scope`:
  - `LOCAL_ONLY` for Private/Daily
  - `GLOBAL` for Ideas
- `search_weight`:
  - Private/Daily: indekslenmez
  - Ideas: `0.85-0.90` (highlight'tan dusuk)

## 9) Uygulama Sirasi (Kisa Plan)

1. Veri modeli: kategori + folder + policy alanlari
2. Kayit ve listeleme: Personal Notes UI (kategori/folder secimi)
3. Indeksleme kurali:
   - Private/Daily -> sadece local
   - Ideas -> global + graph + AI
4. Arama katmani ayrimi:
   - local personal search
   - global search
5. Rank agirligi:
   - Ideas boost kalibrasyonu (`0.85-0.90`)
6. Editor V0.1 temel araclari

## 10) V0.1 Kapsam Disi

- Whiteboard / kalemle cizim
- Gelismis block editor (database-view, kanban vb.)
- Otomatik karma graph optimizasyonlari (ileri faz)

