# Keşif Alanları (Layer 4) Kategori Filtreleme Sorunu Raporu

**Tarih:** 21 Şubat 2026
**Konu:** Felsefe kategorisi seçilmesine rağmen Edebiyat romanlarının (Bir Havva Kızı, Esir Şehrin İnsanları) Flux akışında görüntülenmesi.

## Sorunun Özeti
Layer 4 (Flux/Flow) ekranında sol menüden "Felsefe" (veya herhangi bir kategori) seçildiğinde, sistemin bu filtreyi akışa tam olarak yansıtamaması sorunu tespit edilmiştir. Seçilen kategoriye ait olmayan "Esir Şehrin İnsanları" (Kategorileri: *edebiyat, roman, tarih*) gibi kitaplar, kategori kısıtlaması olmadan ekrana yansımaktadır.

## Temel Neden (Root Cause)
Sorunun temel nedeni **Kategori Değişimi Sırasında Oturum Durumunun (Session State) Tam Güncellenmemesidir.**

İşleyiş adımları ve hatanın meydana geldiği nokta şu şekildedir:

1. **Frontend (Kullanıcı Hareketi):** Kullanıcı "Tümü" kategorisindeyken sol menüden "Felsefe"ye tıklar. `FlowContainer.tsx` içindeki `handleCategoryChange` fonksiyonu tetiklenir ve backend'e yeni kategori (`category="Felsefe"`) ile `resetFlowAnchor` (Konu Değiştirme) isteği atar.
2. **Backend (API):** İstek `flow_routes.py` üzerinden `flow_service.py` içerisindeki `reset_anchor` fonksiyonuna ulaşır.
3. **Sorunlu Nokta (`flow_service.py` - `reset_anchor` metodu):**
   * Metot, "Felsefe" kategorisini parametre olarak alır ve yeni bir başlangıç noktası (anchor) bulmak için bunu başarılı bir şekilde kullanır (`_resolve_anchor` çağrısında filtre çalışır).
   * **ANCAK**, yeni anchor verisini (vektörünü ve ID'sini) mevcut Flux oturumuna (Redis) kaydederken çağrılan `self.session_manager.update_session_anchor` metodu, **sadece anchor verilerini günceller.** Session'ın `category` ve `resource_type` özelliklerini güncellemez!
   * Sonuç olarak, Flux oturumunun hafızasındaki (Redis) `category` değeri eski halinde (çoğu senaryoda boş/tümü `None`) kalır.
4. **Veri Çekme (Next Batch):** İlk anchor değişiminden hemen sonra UI, yeni içerik kartlarını getirmek için `getNextFlowBatch` isteği atar.
5. **Filtresiz Sorgu:** `flow_service.py` içindeki `_generate_batch` fonksiyonu, oturum bilgilerini Redis'ten okur. Redis'teki `state.category` hala `None` (Null) olduğu için API, tüm algoritma sorgularına (Recency, Gravity, Serendipity) kategori filtresi **eklemeden** çalışır. 
6. Ekrana "Esir Şehrin İnsanları" ve "Bir Havva Kızı" gibi sisteme son yüklenmiş veya rastgele gelen ilgisiz romanlar (edebiyat kategorisindeki kitaplar) gelmiş olur.

## Veritabanı Kontrolü (Veri Doğruluğu)
Söz konusu kitapların veritabanındaki (*TOMEHUB_CONTENT_CATEGORIES*) etiketleri kontrol edilmiştir. Veritabanı kategorilendirmesinde sorun yoktur:
* **Esir Şehrin İnsanları:** `['edebiyat', 'roman', 'tarih']` 
Bu kitaplar veritabanında "felsefe" olarak etiketlenmemiştir; yukarıda anlatılan oturum (session) durumunun güncellenememesi hatasından ötürü çekilmektedir.

## Çözüm Önerisi (Plan)
*Not: İsteğiniz üzerine sadece rapor hazırlanmış olup, kodlarda herhangi bir değişiklik yapılmamıştır.*

Gelecekteki onarım adımları şu yollarla sağlanabilir:
1. `flow_session_service.py` içerisindeki `FlowSessionManager` sınıfına `update_session_filters(session_id, resource_type, category)` gibi bir metot eklenebilir.
2. `flow_service.py` içindeki `reset_anchor` metodunda, `self.session_manager.update_session_anchor(...)` çağrısından sonra, session state güncellenerek yeni `category` (ve opsiyonel olarak `resource_type`) kalıcı hale getirilebilir. 
(Örn. `state.category = category` ve `self.session_manager.update_session(state)`)
