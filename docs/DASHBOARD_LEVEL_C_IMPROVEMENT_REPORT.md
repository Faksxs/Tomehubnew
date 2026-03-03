# TomeHub Dashboard Level C: Geliştirme Raporu
**Tarih:** Mart 2026 | **Durum:** Analiz Tamamlandı

---

## Özet

Dashboard Level C, 6 ileri istatistik sunmakta (Pulse, T-Profile, Rust Index, vb.). Sistem, mevcut verileri etkili kullanmakta fakat **kullanıcı-odaklı insights** ve **sistem yükünü kontrol altında tutmak** açısından geliştirme fırsatları vardır.

Bu rapor, basit UI ile fakat derin analitiği sunacak 8 yeni metrik önerir. Tüm veriler **zaten veritabanında** mevcuttur—yeni sorgulara ihtiyaç yoktur.

---

## 1. Mevcut Durum Analizi

### 1.1 Frontend Dashboard (Mevcut Level C)

Dosya: [`apps/frontend/src/components/dashboard/KnowledgeDashboard.tsx`](apps/frontend/src/components/dashboard/KnowledgeDashboard.tsx)

**6 Widget:**
- **Pulse** (30 gün aktivite): `items` ve `highlights` üzerinde timestamp hesabı
- **T-Profile** (Tag dağılımı): Tag frekansı + orphan analizi
- **Core Nexus** (Tag co-occurrence): Hangi taglar birlikte geçiyor
- **Rust Index** (90 gün inaktivite): % olarak gösterilir
- **Intellect Engine** (Ingestion oranı): Kaç item AI-ready?
- **Discovery** (Keşfedilmemiş): 0 highlight olan items

**Sorunlar:**
- Widgetler tıklandığında "INSIGHTS" sekmesine geçer ama detay analitik yok
- Her widget işlenme logic 30-90 gün range-leridir, daha granüler insight yok
- Reading/Inventory statusünün detaylı timeline'ı gösterilmiyor

### 1.2 Backend Analytics Endpoints

Dosya: [`apps/backend/app.py`](apps/backend/app.py#L1145)

**Mevcut Endpoints:**
- `GET /api/analytics/ingested-books` – Hangi booklar ingested
- `GET /api/analytics/epistemic-distribution` – Content granularity (Level A/B/C)
- `GET /api/analytics/concordance` – Word usage contexts (KWIC)
- `GET /api/analytics/distribution` – Word frequency by page
- `POST /api/analytics/compare` – Cross-book term comparison

**Sorun:**
- Endpoints, **book-level** analitikler sunuyor
- **User-level dashboard** agregasyonu yoktur

### 1.3 Veritabanında Mevcut Veriler

| Tablo | Satırlar | Kullanılabilir Insight |
|-------|----------|------------------------|
| `TOMEHUB_LIBRARY_ITEMS` | 65 | Item metadata, tags, reading status, dates |
| `TOMEHUB_CONTENT_V2` | 3,634 | Chunks, embeddings, page numbers, dates |
| `TOMEHUB_CHAT_SESSIONS` | 108 | User query history, interaction patterns |
| `TOMEHUB_SEARCH_LOGS` | 1,330 | User search behavior, queries, execution time |
| `TOMEHUB_FEEDBACK` | 14 | User satisfaction, ratings |
| `TOMEHUB_FLOW_SEEN` | 1,744 | Item discovery tracking, stay duration |
| `TOMEHUB_INGESTED_FILES` | 14 | PDF/EPUB ingestion status |
| `TOMEHUB_ITEM_INDEX_STATE` | 60 | Vector/Graph readiness |
| `TOMEHUB_BOOK_EPISTEMIC_METRICS` | 35 | Content depth (Level A/B/C) |
| `TOMEHUB_CONCEPTS` | 753 | Knowledge graph density |

---

## 2. Önerilen 8 Yeni Metrik

### Kategori A: Engagement & Learning

#### **A1. Knowledge Velocity (Bilgi Hızı)**
- **Tanım:** Son 90 gün içinde okunan + highlighted sayısı/gün
- **Formül:** (finished_items_count + highlight_count_90d) / 90
- **Veri Kaynağı:** `TOMEHUB_LIBRARY_ITEMS.READING_STATUS`, `TOMEHUB_FLOW_SEEN.SEEN_AT`
- **UI Gösterimi:**
  ```
  Knowledge Velocity: 2.3 items/day
  Trend: ↗ +15% vs month-1
  ```
- **Yararı:** Öğrenme ritmi takibi, motivasyon göstergesi
- **Maliyeti:** O(1) – histogram sorgusu caching ile

#### **A2. Concept Maturity Index (Kavram Olgunluğu)**
- **Tanım:** Kitaplar arası kavram tekrarı oranı (knowledge graph linkages)
- **Formül:** (concepts_appearing_in_2+ books) / total_concepts_extracted
- **Veri Kaynağı:** `TOMEHUB_CONCEPT_CHUNKS`, `TOMEHUB_CONCEPTS`, `TOMEHUB_RELATIONS`
- **UI Gösterimi:**
  ```
  Concept Maturity: 34%
  (14 of 41 concepts span across knowledge)
  ```
- **Yararı:** Kütüphane bütünlüğü, çapraz referans gücü
- **Maliyeti:** O(N concepts) – aylık cache

#### **A3. Search-to-Insight Conversion (Arama-Insight Dönüşümü)**
- **Tanım:** Search yapanların %'si feedback veriyor
- **Formül:** feedback_count / search_logs_count * 100
- **Veri Kaynağı:** `TOMEHUB_SEARCH_LOGS`, `TOMEHUB_FEEDBACK`
- **UI Gösterimi:**
  ```
  Search → Insight: 8.2%
  14 feedbacks from 1,330 searches
  Avg Rating: ⭐ 4.1/5
  ```
- **Yararı:** System relevance trust, feature effectiveness
- **Maliyeti:** O(1) – count query

### Kategori B: Content Quality & Readiness

#### **B1. RAG Index (Retrieval Augmented Generation Hazırlığı)**
- **Tanım:** Kaç % content için vector + graph hazır?
- **Formül:** fully_ready_items / total_items * 100
- **Veri Kaynağı:** `TOMEHUB_ITEM_INDEX_STATE.FULLY_READY`
- **UI Gösterimi:**
  ```
  RAG Index: 92%
  58 of 63 items fully indexed
  🟢 Ready for search
  ```
- **Yararı:** Search feature reliability, ingestion health
- **Maliyeti:** O(1) – count

#### **B2. Content Depth Distribution (İçerik Kalınlığı)**
- **Tanım:** Level A/B/C chunks oranı (how analyzable is the content)
- **Formül:** (count_level_c / total_chunks) * 100
- **Veri Kaynağı:** `TOMEHUB_BOOK_EPISTEMIC_METRICS.LEVEL_A/B/C`
- **UI Gösterimi:**
  ```
  Content Depth:
  🔵 Level A: 45% (shallow scanning)
  🟣 Level B: 35% (categorical)
  🟠 Level C: 20% (deep analysis)
  ```
- **Yararı:** İçerik karmaşıklığı, analitik potansiyel
- **Maliyeti:** O(1) – aggregation

#### **B3. Search Freshness (Arama Aktualitesi)**
- **Tanım:** Son 7 gün içinde indexed edilen % items
- **Formül:** items_indexed_last_7d / total_items * 100
- **Veri Kaynağı:** `TOMEHUB_ITEM_INDEX_STATE.LAST_CHECKED_AT`
- **UI Gösterimi:**
  ```
  Search Freshness: 71%
  45 items updated in last week
  Last sync: 2h ago
  ```
- **Yararı:** Index staleness detector, sync health
- **Maliyeti:** O(1)

### Kategori C: Serendipity & Discovery

#### **C1. Discovery Rate (Keşif Hızı)**
- **Tanım:** Flow seeding (+) vs Directly accessed items
- **Formül:** flow_discovered / (direct_access + flow_discovered) * 100
- **Veri Kaynağı:** `TOMEHUB_FLOW_SEEN.DISCOVERED_VIA`
- **UI Gösterimi:**
  ```
  Discovery Rate: 18%
  312 items via serendipity jumps
  vs 1,432 direct access
  🎲 Explore rate: +7% this week
  ```
- **Yararı:** Recommendation quality, serendipity effectiveness
- **Maliyeti:** O(N flow_seen) – weekly materialized view

#### **C2. Bookmark Velocity (İmler Dinamiği)**
- **Tanım:** Aylık ortalama yeni favorite item
- **Formül:** favorites_count / months_active
- **Veri Kaynağı:** `TOMEHUB_LIBRARY_ITEMS.IS_FAVORITE`, `.CREATED_AT`
- **UI Gösterimi:**
  ```
  Bookmark Pace: 3/month
  23 total favorites
  Last bookmark: 4 days ago
  ```
- **Yararı:** Priority curation metric, active curation signal
- **Maliyeti:** O(1)

#### **C3. Serendipity Heatmap (Keşif Sıcaklık Haritası)**
- **Tanım:** En çok discovered edilen 5 konsep
- **Formül:** Top co-occurring concepts in flow_discovered items
- **Veri Kaynağı:** `TOMEHUB_FLOW_SEEN`, `TOMEHUB_CONCEPTS`
- **UI Gösterimi:**
  ```
  🔥 Top Discovery Clusters:
  philosophy × ethics: 47 serendipities
  language × culture: 31 serendipities
  ```
- **Yararı:** Interest clusters, recommendation tuning
- **Maliyeti:** O(N concepts) – cached weekly

---

## 3. Teknik Implementasyon Katmanı

### 3.1 Backend Layer (Yeni Endpoint)

**Endpoint:** `GET /api/analytics/dashboard-metrics` (New)

```python
@app.get("/api/analytics/dashboard-metrics")
async def get_dashboard_metrics(
    firebase_uid: str,
    period_days: int = 90,
    include_heatmap: bool = False
):
    """
    Returns all 8 metrics for Level C dashboard.
    
    Response:
    {
        "engagement": {
            "knowledge_velocity": 2.3,  # items/day
            "concept_maturity": 34,      # %
            "search_to_insight": 8.2    # %
        },
        "content_quality": {
            "rag_index": 92,             # %
            "content_depth": {...},      # Level A/B/C distribution
            "search_freshness": 71       # %
        },
        "discovery": {
            "discovery_rate": 18,        # %
            "bookmark_velocity": 3,      # /month
            "heatmap": [...]             # Top clusters (if requested)
        },
        "timestamp": "2026-03-02T...",
        "computed_at_ms": 245
    }
    """
    result = compute_dashboard_metrics(firebase_uid, period_days, include_heatmap)
    return result
```

**Implement Dosyası:** `apps/backend/services/dashboard_metrics_service.py` (New)

### 3.2 Caching Strategy

```python
# L1 Cache (In-Memory, 10 min TTL)
CACHE_KEY_PATTERN: "dashboard_metrics:{firebase_uid}:{period_days}"

# L2 Cache (Redis, 30 min TTL) – Optional
# Only for metrics without user-feedback dependency

# Cache Invalidation Triggers:
# - New item added: Invalidate discovery_rate, bookmark_velocity
# - Search performed: Invalidate search_to_insight
# - Item indexed: Invalidate rag_index, search_freshness
```

### 3.3 Query Performance

All metrics use **aggregation-level** queries (no N+1):

| Metric | Query Type | Est. Time |
|--------|-----------|-----------|
| Knowledge Velocity | GROUP BY period | ~50ms |
| Concept Maturity | COUNT DISTINCT across graph | ~80ms |
| Search-to-Insight | COUNT joins | ~40ms |
| RAG Index | COUNT with filter | ~30ms |
| Content Depth | SUM aggregation | ~25ms |
| Search Freshness | COUNT with date filter | ~35ms |
| Discovery Rate | SUM with GROUP BY | ~60ms |
| Bookmark Velocity | AVG with date range | ~25ms |

**Total expected response time:** 250–350ms (with caching)

### 3.4 Data Freshness Policy

| Metric | Update Frequency | Freshness Window |
|--------|------------------|------------------|
| Engagement (A1–A3) | Real-time (on event) | < 1 min |
| Content Quality (B1–B3) | Hourly (batch) | < 1 hour |
| Discovery (C1–C3) | Daily (materialized view) | < 24 hours |

---

## 4. Frontend Implementation (Level C UI)

### 4.1 Kardiyogram Tasarımı (Simplified, Scannable)

**Mevcut Problem:** 6 widget kartı küçük text'le kalabalık.

**Yeni Tasarım:**

```
┌─────────────────────────────────────────────────────────┐
│ Level C • Deep Analytics  [expand ▼]                     │
├─────────────────────────────────────────────────────────┤
│
│ 📊 ENGAGEMENT & LEARNING
│  Knowledge Velocity: 2.3 items/day        [↗ +15% vs mo]
│  Concept Maturity:   34% (14/41)          [Deep links]
│  Search→Insight:     8.2% (14/1330)       [⭐ 4.1/5]
│
│ 🎯 CONTENT QUALITY  
│  RAG Index:          92% (58/63)          [READY]
│  Content Depth:      [░░░ 45%] [███ 20%] [Deep analysis]
│  Search Freshness:   71% (45 updated)    [2h ago]
│
│ 🎲 DISCOVERY & SERENDIPITY
│  Discovery Rate:     18% (312 serendipities) [↗]
│  Bookmark Velocity:  3 per month (23 total)
│ 🔥 Top Clusters:     philosophy×ethics (47)
│                      language×culture (31)
│
│ [View detailed network analysis →]
└─────────────────────────────────────────────────────────┘
```

**Özellikler:**
- 3 kategoriye ayrılmış, başlıklı section'lar
- Yüzde/ratio ürünleri **kısa bar chart'ler** ile gösterilir
- Trend indicator'ları ("↗ +15%")
- Statüs badge'leri ("READY", "2h ago")
- Collapsible heatmap footer

### 4.2 Code Changes (Frontend Component)

**File:** `apps/frontend/src/components/dashboard/KnowledgeDashboard.tsx`

```tsx
// New useFetch hook
const [metricsData, setMetricsData] = useState<DashboardMetrics | null>(null);

useEffect(() => {
  if (!userId) return;
  
  const fetchMetrics = async () => {
    try {
      const data = await backendApiService.getDashboardMetrics(
        userId, 
        { periodDays: 90, includeHeatmap: true }
      );
      setMetricsData(data);
    } catch (error) {
      logger.warn("Failed to fetch dashboard metrics", { error });
      // Graceful fallback to old Level C display
    }
  };

  fetchMetrics();
}, [userId]);

// Render new sections (replacing old widgetized approach)
return (
  <AnimatePresence>
    {showLevelC && metricsData && (
      <motion.div className="space-y-6">
        {/* Engagement Section */}
        <MetricSection
          title="📊 Engagement & Learning"
          metrics={[
            { label: "Knowledge Velocity", value: metricsData.engagement.knowledge_velocity, unit: "items/day" },
            { label: "Concept Maturity", value: metricsData.engagement.concept_maturity, unit: "%" },
            { label: "Search→Insight", value: metricsData.engagement.search_to_insight, unit: "%" }
          ]}
        />
        
        {/* Content Quality Section */}
        <MetricSection
          title="🎯 Content Quality"
          metrics={[...]}
        />
        
        {/* Discovery Section */}
        <DiscoverySection
          metrics={metricsData.discovery}
          heatmap={metricsData.discovery.heatmap}
        />
      </motion.div>
    )}
  </AnimatePresence>
);
```

**New Types:** `apps/frontend/src/types/dashboard.ts`

```typescript
interface DashboardMetrics {
  engagement: {
    knowledge_velocity: number;
    concept_maturity: number;
    search_to_insight: number;
  };
  content_quality: {
    rag_index: number;
    content_depth: ContentDepthBreakdown;
    search_freshness: number;
  };
  discovery: {
    discovery_rate: number;
    bookmark_velocity: number;
    heatmap: HeatmapCluster[];
  };
  timestamp: string;
  computed_at_ms: number;
}
```

---

## 5. Implementasyon Yol Haritası

### Phase 1: Temel Metrikler (1 hafta)

**Sprint 1.1: Backend Aggregation**
- [ ] `dashboard_metrics_service.py` oluştur
  - [ ] `compute_knowledge_velocity()`
  - [ ] `compute_concept_maturity()`
  - [ ] `compute_search_to_insight()`
  - [ ] `compute_rag_index()`
  - [ ] `compute_content_depth_distribution()`
  - [ ] `compute_search_freshness()`
  
- [ ] Caching layer entegre et (`cache_service.py` ile tie-in)
- [ ] `GET /api/analytics/dashboard-metrics` endpoint'i ekle
- [ ] Unit tests yaz (`test_dashboard_metrics.py`)

**Sprint 1.2: Frontend Integration**
- [ ] `DashboardMetrics` type'ı tanımla
- [ ] `backendApiService.getDashboardMetrics()` ekle
- [ ] Yeni metric'ler fetch eden `useDashboardMetrics` hook'u yaz
- [ ] KnowledgeDashboard.tsx refactor (bölümler'e ayır)

### Phase 2: Discovery Metrics (1 hafta)

**Sprint 2.1: Backend**
- [ ] `compute_discovery_rate()`
- [ ] `compute_bookmark_velocity()`
- [ ] `compute_serendipity_heatmap()` (materialized view veya batch)
- [ ] Cache strategy'si optimize et (discovery güncelleme sıklığı)

**Sprint 2.2: Frontend**
- [ ] `DiscoverySection` component'i oluştur
- [ ] Heatmap render'ı (simple chart, no external deps)

### Phase 3: UI/UX Polish (3 gün)

- [ ] Responsive breakpoint'ler optimize et
- [ ] Dark mode color scheme güzelaştır
- [ ] Metric tooltip'leri ekle (hover → explanation)
- [ ] Trend indicator'ları (↗ +15%) implementasyon
- [ ] Accessibility (a11y) audit

### Phase 4: Testing & Deployment (3 gün)

- [ ] E2E test'leri yaz (Level C açılıp metriklerin load olması)
- [ ] Load test'i çalıştır (200ms SLA'sını sağlamak için)
- [ ] Staging deploy'u, QA pass'ı
- [ ] Performance monitoring setup

---

## 6. Mevcut Kod ile Entegrasyon Noteları

### 6.1 Backend Alternatif: SQL Queries (No New Tables)

Tüm metrikler mevcut tablolardan hesaplanabilir:

```sql
-- Knowledge Velocity
SELECT 
  COUNT(DISTINCT CASE WHEN READING_STATUS='Finished' 
                       AND UPDATED_AT >= SYSDATE-90 THEN ITEM_ID END)
  + COUNT(DISTINCT CASE WHEN fs.SEEN_AT >= SYSDATE-90 THEN fs.CHUNK_ID END)
FROM TOMEHUB_LIBRARY_ITEMS li
  LEFT JOIN TOMEHUB_FLOW_SEEN fs ON li.ITEM_ID = fs.ITEM_ID 
                                     AND li.FIREBASE_UID = fs.FIREBASE_UID
WHERE li.FIREBASE_UID = :uid
  AND li.ITEM_TYPE != 'PERSONAL_NOTE';

-- Concept Maturity
SELECT 
  COUNT(DISTINCT CASE WHEN cnt > 1 THEN CONCEPT_ID END) * 100 
  / COUNT(DISTINCT CONCEPT_ID) as maturity_pct
FROM (
  SELECT C.CONCEPT_ID, COUNT(DISTINCT CC.CONTENT_ID) as cnt
  FROM TOMEHUB_CONCEPTS C
    LEFT JOIN TOMEHUB_CONCEPT_CHUNKS CC ON C.ID = CC.CONCEPT_ID
  GROUP BY C.CONCEPT_ID
);

-- Search-to-Insight
SELECT 
  COUNT(DISTINCT f.ID) * 100 / COUNT(DISTINCT sl.ID) as conversion_pct
FROM TOMEHUB_SEARCH_LOGS sl
  LEFT JOIN TOMEHUB_FEEDBACK f ON sl.ID = f.SEARCH_LOG_ID
WHERE sl.FIREBASE_UID = :uid
  AND sl.TIMESTAMP >= SYSDATE-90;
```

### 6.2 Cache Integration

`services/cache_service.py` ile uyumlu:

```python
from services.cache_service import get_cache, set_cache

def compute_dashboard_metrics(firebase_uid: str):
    cache_key = f"dashboard_metrics:{firebase_uid}:90d"
    
    # Check L1 + L2
    cached = get_cache(cache_key)
    if cached:
        return cached
    
    # Compute (50-350ms)
    result = {
        "engagement": {...},
        "content_quality": {...},
        "discovery": {...}
    }
    
    # Store (10-min L1, 30-min L2)
    set_cache(cache_key, result, ttl_seconds=600)
    return result
```

### 6.3 Search Logs Analysis

Mevcut `TOMEHUB_SEARCH_LOGS` tablosu zaten `TIMESTAMP`, `QUERY_TEXT`, `INTENT` kayıtlıyor.

- **Search-to-Insight:** Search logs'tan FEEDBACK join'i
- **Discovery Rate:** `TOMEHUB_FLOW_SEEN.DISCOVERED_VIA = 'search'` vs `'semantic_bridge'`

### 6.4 Concept Extraction (Graph Readiness)

`TOMEHUB_CONCEPTS` ve `TOMEHUB_CONCEPT_CHUNKS` zaten mevcuttur.

- **Concept Maturity:** Bipartite concept-document graph'ında span metric'i
- **Top Clusters:** Concept co-occurrence (existing `TOMEHUB_RELATIONS` table)

---

## 7. Potansiyel Zorluklar & Çözümler

| Zorluk | Çözüm | Priority |
|--------|-------|----------|
| **Cache Invalidation Timing** | Event-driven invalidation (on item.ingested, search.logged, flow.recorded) | HIGH |
| **Concept Maturity slow query** | Weekly materialized view + index on CONCEPT_ID | MEDIUM |
| **Serendipity Heatmap concurrency** | Batch compute (off-peak), store in temp table | LOW |
| **UX: Metric explanation clarity** | Tooltip (hover) + expandable detail cards | MEDIUM |
| **Backward compat with old Level C** | Keep existing widgets, add new section below | HIGH |

---

## 8. Başarı Kriterleri

| KPI | Target | Nasıl Ölçüleçek |
|-----|--------|------------------|
| **API Response Time** | < 350ms (p95) | APM dashboard |
| **Cache Hit Rate** | > 80% | Redis/cache logs |
| **Metric Accuracy** | ±1% vs manual calculation | Periodic audit |
| **UI Load Time** | < 500ms (metrics section) | Lighthouse/WebVitals |
| **User Engagement** | Click-through on metrics | Analytics.js event tracking |
| **System Load Impact** | < 2% additional DB CPU | Performance profiling |

---

## 9. Gelecek Roadmap (Phase 2 sonrası)

- **Metric Trends:** Haftalık snapshot'ları store et, line graph'lar göster
- **Anomaly Detection:** Metric spike'ları algıla (e.g. "Rust Index suddenly 60%")
- **Personalized Recommendations:** "Your knowledge_velocity is low → try these..."
- **Team/Social Analytics:** Multi-user aggregate metrics (if multi-tenancy supported)
- **Export to CSV:** Kullanıcı analitik'lerini indirmesi

---

## 10. Dosya Özeti & Checklist

### Yeni Dosyalar Oluşturulacak

- [ ] `apps/backend/services/dashboard_metrics_service.py` (450 lines)
- [ ] `apps/backend/tests/test_dashboard_metrics.py` (200 lines)
- [ ] `apps/frontend/src/types/dashboard.ts` (80 lines)
- [ ] `apps/frontend/src/services/dashboardMetricsApi.ts` (120 lines, backendApiService'e method add)
- [ ] `apps/frontend/src/components/dashboard/MetricSection.tsx` (150 lines, reusable card)
- [ ] `apps/frontend/src/components/dashboard/DiscoverySection.tsx` (200 lines, heatmap + cards)
- [ ] `apps/frontend/src/hooks/useDashboardMetrics.ts` (60 lines)

### Değiştirilecek Dosyalar

- [ ] `apps/backend/app.py` – `/api/analytics/dashboard-metrics` endpoint'ini ekle
- [ ] `apps/frontend/src/components/dashboard/KnowledgeDashboard.tsx` – Level C bölümü refactor
- [ ] `apps/backend/services/cache_service.py` – Cache pattern dokümantasyonu güncelle
- [ ] `docs/API_GUIDE.md` – Yeni endpoint documentation

---

## Sonuç

**Dashboard Level C** geliştirmesi:
- ✅ **Mevcut verileri maksimal kullan** (yeni tablo yok)
- ✅ **Sistem yükünü kontrol tutar** (250-350ms API, caching)
- ✅ **Kullanıcı deneyimini zenginleştirir** (8→6 anlamlı metric)
- ✅ **Clear implementasyon yolunu** takip eder (4 phase, 2-3 hafta)

Budget: ~80-100 mühendis-saat (1-2 hafta, 1 ön-end/1 arka-end dev)

---

**Hazırladı:** TomeHub Analytics & Dashboard Team  
**Review:** Architecture & UX Design Leads  
**Onay Bekleniyor:** Product Manager
