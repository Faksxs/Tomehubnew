# Phase-3 Router Kickoff Report (2026-02-11)

## 1. Amaç

Statik orchestrator davranisini, dusuk riskli bir `rule_based` semantic router ile dinamik strateji secimine gecirmek.

## 2. Uygulanan Degisiklikler

1. Yeni router modulu:
   - `apps/backend/services/search_system/semantic_router.py`
   - Cikti:
     - `selected_buckets`: `exact|lemma|semantic`
     - `reason`
2. Config:
   - `apps/backend/config.py`
   - `apps/backend/.env.example`
   - Yeni ayar: `SEARCH_ROUTER_MODE` (`static|rule_based`)
3. Orchestrator entegrasyonu:
   - `apps/backend/services/search_system/orchestrator.py`
   - Router kararina gore strateji kosumu
   - Semantic variation kosumu sadece semantic seciliyse
   - Metadata:
     - `router_mode`
     - `router_reason`
     - `selected_buckets`
     - `executed_strategies`
4. `/api/search` metadata forwarding:
   - `apps/backend/services/search_service.py`
   - Router metadata response'a tasindi.

## 3. Smoke Test Sonuclari

1. `POST /api/smart-search` query: `kitabin adi neydi`
   - `router_mode=rule_based`
   - `router_reason=pattern:\\bkitab(?:i|ın|in) ad[ıi]\\b`
   - `selected_buckets=[exact, lemma]`
   - `executed_strategies=[ExactMatchStrategy, LemmaMatchStrategy]`
2. `POST /api/smart-search` query: `ahlak kavrami nedir`
   - `router_mode=rule_based`
   - `router_reason=conceptual_hint`
   - `selected_buckets=[lemma, semantic, exact]`
   - `executed_strategies=[ExactMatchStrategy, LemmaMatchStrategy, SemanticMatchStrategy]`
3. `POST /api/search` metadata icinde router alanlari gorundu.

## 4. Beklenen Etki

1. Gereksiz strategy kosumlarinin azalmasi
2. Latency ve maliyet optimizasyonu
3. Davranis gozlenebilirligi (metadata uzerinden)

## 5. Sonraki Faz-3 Adimlari

1. Router A/B olcumu (`static` vs `rule_based`)
2. Tool secim matrisiyle kural seti genisletme
3. `429` ve timeout durumlari icin adaptive backoff/pacing
