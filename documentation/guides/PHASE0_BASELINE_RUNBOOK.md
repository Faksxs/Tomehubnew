# Phase-0 Baseline Runbook

Bu runbook, Faz 0 baseline olcumunu standart ve tekrar edilebilir sekilde calistirmak icin hazirlandi.

## 1. Hedef

Asagidaki metrikler icin baseline toplamak:

1. `success_rate`, `timeout_rate`
2. `latency p50/p95`
3. `result_count`
4. `MRR`, `nDCG@10` (heuristic relevance)
5. Explorer tarafi icin `attempt` ve `fallback_timeout_rate`
6. Graph probe ile `graph_hit_rate` (service-level)

## 2. Faz 0 Cikti Dosyalari

1. Query set generator:
   `apps/backend/scripts/phase0_generate_query_set.py`
2. Benchmark runner:
   `apps/backend/scripts/phase0_benchmark.py`
3. Query set:
   `apps/backend/data/phase0_query_set.json`
4. Rapor ciktilari:
   `documentation/reports/phase0_baseline_<timestamp>.json`
   `documentation/reports/phase0_baseline_<timestamp>.md`

## 3. Query Set Uretimi (120 Sorgu)

```bash
cd apps/backend
python scripts/phase0_generate_query_set.py
```

Kategori dagilimi:

1. `DIRECT` (20)
2. `COMPARATIVE` (20)
3. `SYNTHESIS` (20)
4. `PHILOSOPHICAL` (20)
5. `ANALYTIC` (20)
6. `FOLLOW_UP` (20)

## 4. Dry-Run Dogrulama

```bash
cd apps/backend
python scripts/phase0_benchmark.py --uid <FIREBASE_UID> --dry-run
```

Bu adim API'ye istek atmaz, sadece dataset yapisini ve kategori dagilimini dogrular.

## 5. Baseline Calistirma

Backend calisiyor olmali (`/api/search`, `/api/smart-search`, `/api/chat` erisilebilir).

```bash
cd apps/backend
python scripts/phase0_benchmark.py --uid <FIREBASE_UID> --base-url http://localhost:5001
```

Not:

1. Explorer endpoint maliyetli oldugu icin varsayilan `chat_sample_size=30`.
2. Graph probe varsayilan aciktir ve `graph_probe_size=30` ile calisir.

## 6. Opsiyonlar

Explorer kapat:

```bash
python scripts/phase0_benchmark.py --uid <FIREBASE_UID> --disable-chat
```

Graph probe kapat:

```bash
python scripts/phase0_benchmark.py --uid <FIREBASE_UID> --disable-graph-probe
```

Explorer orneklem sayisini arttir:

```bash
python scripts/phase0_benchmark.py --uid <FIREBASE_UID> --chat-sample-size 60
```

## 7. Faz 0 Kabul Kriterleri

Bu fazda amac baseline olcumu oldugu icin dogrudan pass/fail yerine referans olusturulur.
Sonraki fazlarda degisiklikler su hedeflere gore degerlendirilir:

1. `quality_gain_target_pct >= +5%`
2. `latency_increase_ceiling_pct <= +10%`
3. `explorer_p95_target_ms <= 12000`

## 8. Sonraki Adim (Faz 1 girisi)

Faz 0 rapor ciktilari alindiktan sonra:

1. `concat` vs `rrf` flagli A/B benchmark
2. Explorer retry guardrail
3. Graph freshness state (vector_ready / graph_ready / fully_ready)

