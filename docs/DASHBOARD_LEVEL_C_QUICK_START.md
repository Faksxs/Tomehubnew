# Dashboard Level C: Başlangıç Kontrol Listesi (Quick Start)

**Durum:** Rapor tamamlandı, 2 ana dokümantasyon dosyası hazır.

---

## 📋 Dosyaları Oku (İlk Adım)

Yeni oluşturulan dosyaları sırayla oku:

1. **[`DASHBOARD_LEVEL_C_IMPROVEMENT_REPORT.md`](./DASHBOARD_LEVEL_C_IMPROVEMENT_REPORT.md)** ← START HERE
   - Geniş özet: mevcut durum, 8 metrik tanımı, yol haritası
   - 10 bölüm, ~4000 satır
   - **Okuma süresi:** 30 dakika

2. **[`DASHBOARD_METRICS_TECHNICAL_GUIDE.md`](./DASHBOARD_METRICS_TECHNICAL_GUIDE.md)** ← FOR DEVELOPERS
   - SQL template'ler (kopyala-yapıştır hazır)
   - Python skeleton code (`dashboard_metrics_service.py`)
   - Frontend hook'lar, test'ler
   - **Okuma süresi:** 20 dakika (geliştiriciler için)

---

## 🎯 Hızlı Özet (1 Dakikalık Versiyon)

```
PROBLEM ÇÖZÜYORUZ:
├─ Dashboard Level C şu anda 6 widget gösteriyor (kullanmadı)
├─ Detaylı insight'lar yoktur (tıklandığında "INSIGHTS" sekmesine git)
└─ "Why is this metric?" açıklamalar eksikdir

ÇÖZÜM: 8 Yeni Metrik
├─ Engagement (3): Knowledge Velocity, Concept Maturity, Search→Insight
├─ Content Quality (3): RAG Index, Depth Distribution, Freshness
└─ Discovery (2): Discovery Rate, Bookmark Velocity, (+Heatmap)

DETAYLAR:
├─ Tüm veriler zaten veritabanında (yeni schema yok)
├─ API response: 250–350ms (cache'li)
├─ Implementation: 2–3 hafta (1 ön-end + 1 arka-end dev)
└─ PR'lar: ~1500 LOC total

BAŞLA:
1. Raporu oku (30 min)
2. Teknik guide'ı oku (20 min)
3. Backend: dashboard_metrics_service.py yaz (1–2 gün)
4. Frontend: UI refactor (1–2 gün)
5. Test & deploy (3 gün)
```

---

## 🚀 Implementasyona Geçmeden Önce Sorular

Takımla diskütabileceğin konular:

1. **Metric Granularity**: 90 gün lookup'ı fixed mi yoksa user-configurable?
   - Rapor varsayıyor: Fixed 90 gün
   - Alternatif: 30/90/180 gün seçim

2. **Heatmap Complexity**: Serendipity heatmap'ı (expensive query) dahil mı?
   - Rapor: Yes (24h cache'li)
   - Alternatif: MVP'de skip, Phase 2'de ekle

3. **Cache Strategy**: Redis var mı yoksa in-memory cache yeterli?
   - Mevcut: `cache_service.py` (cachetools + optional Redis)
   - Impact: Multi-instance'ta L1-only ≠ L2-shared

4. **Backward Compat**: Eski 6 widget'ları kalsın mı yoksa replace?
   - Rapor: Keep (+ new section below)
   - Alternatif: Complete replacement

5. **Mobile**: Responsive breakpoint'ler düzeltilsin mi?
   - Rapor: Yes (Tailwind md:/lg: prefixes)
   - Note: KnowledgeDashboard zaten mobile-friendly

---

## ✅ Ön-koşullar Check

Implementasyona başlamadan:

- [ ] Backend Python environment aktif (`pip list | grep cachetools`)
- [ ] Frontend `npm` installed (`node -v`)
- [ ] Oracle DB bağlantısı test (`apps/backend/scripts/diag_db.py`)
- [ ] Git branch hazır (`git checkout -b feature/dashboard-level-c`)
- [ ] Access: Database'e write access, VS Code workspace'e

---

## 📂 Kod Yapısı (Ne Nereye Gider)

```
Yeni/Değişen Dosyalar:

BACKEND:
apps/backend/
├─ services/
│  ├─ dashboard_metrics_service.py (NEW, 600 lines)
│  └─ cache_service.py (update cache patterns docs)
├─ app.py (add /api/analytics/dashboard-metrics endpoint, ~20 lines)
├─ models/request_models.py (add DashboardMetricsRequest, ~5 lines)
└─ tests/
   └─ test_dashboard_metrics.py (NEW, 150 lines)

FRONTEND:
apps/frontend/src/
├─ components/dashboard/
│  ├─ KnowledgeDashboard.tsx (refactor Level C section, ~150 lines modified)
│  ├─ MetricSection.tsx (NEW, reusable card, 150 lines)
│  └─ DiscoverySection.tsx (NEW, heatmap + cards, 200 lines)
├─ hooks/
│  └─ useDashboardMetrics.ts (NEW, 80 lines)
├─ services/
│  └─ backendApiService.ts (add getDashboardMetrics method, ~30 lines)
├─ types/
│  └─ dashboard.ts (NEW, interfaces, 80 lines)
└─ tests/
   └─ KnowledgeDashboard.test.tsx (update, +100 lines)

DOCS:
docs/
├─ DASHBOARD_LEVEL_C_IMPROVEMENT_REPORT.md (THIS REPORT, 600 lines)
├─ DASHBOARD_METRICS_TECHNICAL_GUIDE.md (SQL + code, 400 lines)
└─ API_GUIDE.md (update endpoint list)

TOTAL NEW LINES: ~2000
TOTAL MODIFIED LINES: ~400
TOTAL TC TIME: 80–100 hours
```

---

## 🔴 Riskler & Mitigations

| Risk | Severity | Mitigation |
|------|----------|-----------|
| **Cache invalidation delay** | HIGH | Event-driven invalidation (item.ingested → cache.invalidate) |
| **Slow concept query** | MEDIUM | Weekly materialized view + index |
| **Mobile UI cramped** | MEDIUM | Responsive design pass + tablet testing |
| **SQL injection (if careless)** | HIGH | Use prepared statements only, code review |
| **Performance regression** | MEDIUM | Load test 200ms SLA, APM monitoring |
| **User confusion (metric meaning)** | LOW | Tooltip hover explanations + docs link |

---

## 🎬 Next Steps (Hangi Dosyayı Ne Zaman Oku)

### Eğer sen Product Manager/Designer iseniz:
1. ✅ Bu dosyayı oku (done)
2. 📖 Rapor'un Section 1–2'sini oku (Product context)
3. 💬 Teknik lead ile "Sorular" bölümünü disküt (30 min)
4. 📝 Approval ver (GO/NO-GO)

### Eğer sen Backend Developer iseniz:
1. ✅ Bu dosyayı oku (done)
2. 📖 Rapor'un Section 3–4'ünü oku (Architecture)
3. 💻 Technical Guide'ın SQL'ini oku + dbclient'te test et
4. 🧪 Test sorguları (10 min)
5. 💻 dashboard_metrics_service.py yaz (1–2 gün)
6. 🔍 Code review + deploy

### Eğer sen Frontend Developer iseniz:
1. ✅ Bu dosyayı oku (done)
2. 📖 Rapor'un Section 4'ünü oku (UI)
3. 💻 Technical Guide'ın TypeScript/React'ini oku
4. 🎨 MetricSection.tsx, DiscoverySection.tsx yaz (1–2 gün)
5. 🧪 Mobile responsive test (iPad/iPhone)
6. 🔍 Code review + deploy

---

## 📊 Status Board Template

Rapor tamamlandıktan sonra, bu template'i kullanarak ilerlemeyi track'le:

```markdown
## Dashboard Level C Implementation Status

**Phase 1: Backend Aggregation** (Week 1)
- [x] Rapor tamamlandı
- [ ] Approval alındı
- [ ] SQL queries onaylandı
- [ ] dashboard_metrics_service.py yazıldı
- [ ] Unit tests geçti
- [ ] Endpoint deployed to staging

**Phase 2: Frontend Integration** (Week 1–2)
- [ ] DashboardMetrics type tanımlandı
- [ ] MetricSection.tsx yazıldı
- [ ] DiscoverySection.tsx yazıldı
- [ ] UI staging'de test edildi
- [ ] Mobile responsive checked

**Phase 3: Polish & Deploy** (Week 2–3)
- [ ] Tooltips eklendi
- [ ] Dark mode verified
- [ ] A11y audit passed
- [ ] E2E tests passed
- [ ] Load test passed (200ms SLA)
- [ ] Prod deployed

**Current:** [Link to GH Project]
**Owner:** @backend-dev, @frontend-dev
**Stakeholder:** @product-manager
```

---

## 📞 Sorulabilecek Sorular

Implementasyon sırasında sıkılırsan:

1. **"Bu SQL sorgusunun cost'u çok yüksek mi?"**
   → EXPLAIN PLAN çalıştır, index suggestions'ı kontrol et

2. **"Cache invalidation'ında race condition var mı?"**
   → Distributed lock kullan (Redis SETNX) veya async queue

3. **"Serendipity heatmap'ı hesaplaması 500ms alıyor!"**
   → Batch job'a ya da materialized view'a taşı, daily schedule'de run

4. **"Mobile'da metrikler okuma zorluğu çekiyor"**
   → Font size artır, bar chart'ları sparklines'a değiştir

---

## 🏁 Success = Checklist Tamamlandı

Bittiğinde ne olacak?

✅ Dashboard Level C, **8 anlamlı metrik** gösteriyor  
✅ Metrikler **250ms'de load** oluyor (cache'li)  
✅ Kullanıcı **click-through** trend'i 10%+ artıyor  
✅ "Why?" sorusunun cevabı **hemen görünüyor** (tooltip)  
✅ Mobile/tablet'te **responsive** görünüyor  
✅ No performance regression (APM dashboard clean)  

---

## 📚 Referans Kütüphanesi

Rapor içinde referans edilen code:

| Komponent | Dosya | Satır |
|-----------|-------|-------|
| Level C UI | `KnowledgeDashboard.tsx` | [97–450](../../apps/frontend/src/components/dashboard/KnowledgeDashboard.tsx#L97) |
| Analitik endpoint'ler | `app.py` | [1145–1295](../../apps/backend/app.py#L1145) |
| Cache service | `cache_service.py` | [1–100](../../apps/backend/services/cache_service.py#L1) |
| Mevcut metrikler | `analytics_service.py` | [1–100](../../apps/backend/services/analytics_service.py#L1) |

---

## 🎓 Learning Resources

- **Oracle SQL Performance:** https://docs.oracle.com/en/database/
- **Cachetools:** https://cachetools.readthedocs.io/
- **React Hooks:** https://react.dev/reference/react/hooks
- **Tailwind Responsive:** https://tailwindcss.com/docs/responsive-design

---

**Sonuç:** Rapor hazır, teknik guide hazır, kontrol listesi hazır.  
**Sonraki Adım:** Approval + Sprint Planning  
**Tahmini Tamamlanma:** 2–3 hafta (2 dev)

---

*Generated: March 2, 2026 | TomeHub Analytics Team*
