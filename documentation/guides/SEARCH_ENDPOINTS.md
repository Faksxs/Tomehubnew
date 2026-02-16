# Search Endpoints (Search vs Smart Search)

**Dil:** Turkce (ASCII)

## Ozet
TomeHub iki farkli arama hattina sahiptir:
- `/api/search`: RAG tabanli, graph retrieval ile zenginlesebilir.
- `/api/smart-search`: Layer-2 retrieval (exact/lemma/semantic); graph retrieval yoktur.

Bu fark uretimde kullanici deneyimini etkiler. Smart Search daha hizli ve determinizm odakli, Search ise graph ile daha genis kavramsal kapsama sahiptir.

## Temel Farklar
1. **Graph Retrieval**
   - `/api/search`: Graph kanalini kullanabilir (intent ve timeout politikalarina bagli).
   - `/api/smart-search`: Graph kanali yoktur.

2. **Cikis Tipi**
   - `/api/search`: Answer + sources + metadata
   - `/api/smart-search`: results + metadata (answer yok)

3. **Uygun Kullanim**
   - Kapsamli cevap/yorum: `/api/search`
   - Hizli, filterli retrieval: `/api/smart-search`

## Uretim Notu
Her iki endpoint response metadata icinde `search_variant` alanini tasir:
- `search` veya `smart_search`

Bu alan, izleme ve urun davranislarini ayristirmak icin kullanilmalidir.
