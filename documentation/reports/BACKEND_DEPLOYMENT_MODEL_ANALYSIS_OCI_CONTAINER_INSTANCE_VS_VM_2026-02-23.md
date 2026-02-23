# TomeHub Backend Deployment Model Analysis (OCI Container Instance vs VM)

**Tarih:** 2026-02-23  
**Kapsam:** Backend-only deployment (FastAPI + Gunicorn/Uvicorn + Caddy)  
**Kısıtlar:** OCI Always Free öncelikli, düşük kullanım, ops önceliği = stabil + basit yönetim  
**Bölge:** AB içinde esnek (Amsterdam tercih, alternatif region kabul)

---

## 1. Executive Summary

### Sonuç (kısa cevap)

**Bugün için en doğru seçenek:**  
`OCI Compute VM (Ampere A1 / VM.Standard.A1.Flex) + Docker (backend-only deploy)`

### Neden

- Mevcut TomeHub backend mimarisi Docker/VM modeline doğal uyumlu
- Oracle wallet + OCI key + Firebase credential gibi **dosya-path bağımlılıkları** var
- Caddy certificate persistence ve uploads için **kalıcı storage/mount** ihtiyacı var
- Backend startup/lifespan ağır; VM üzerinde debug/tuning daha kolay
- Kullanım düşük olduğu için Container Instance’ın managed avantajı sınırlı
- Kullanıcı saha kanıtına göre `eu-amsterdam-1` içinde Container Instance shape availability belirsiz (`No items to display`)

### Secondary / Conditional seçenek

`OCI Container Instance (backend-only)` kullanılabilir, ancak:

- region/shape gerçekten create edilebilir olmalı
- secrets/volume stratejisi sadeleştirilmeli
- Caddy/cert/uploads yaklaşımı container-instance modeline özel netleştirilmeli

### Şu an önerilmeyen

`OCI VM (AMD E2.1.Micro, 1 GB)` production-primary backend için önerilmez.

- Düşük kullanım olsa bile memory headroom zayıf
- Repo içi SRE raporlarında memory pressure/OOM riskleri var

---

## 2. Analiz Amacı ve Karar Soruları

Bu rapor şu sorulara cevap verir:

1. Mevcut TomeHub backend için bugün en doğru deployment modeli hangisi?
2. Düşük kullanım senaryosunda `Container Instance` gerçekten avantaj sağlıyor mu?
3. Docker/container yaklaşımı mevcut sistemde pratikte uygun mu?
4. OCI region/shape availability belirsizliği varken hangi seçenek daha güvenli?

---

## 3. Mevcut Backend Deployment Gerçeği (Repo-truth)

Bu bölüm repo içindeki mevcut kod ve deployment dosyalarına dayanır.

### 3.1 Docker runtime mevcut ve aktif tasarlanmış

- `apps/backend/Dockerfile`
  - Python base image kullanıyor (`python:3.11-slim`) (`apps/backend/Dockerfile:4`)
  - `80/443/5000` portlarını expose ediyor (`apps/backend/Dockerfile:46`)
  - healthcheck tanımlı (`apps/backend/Dockerfile:49`)
  - entrypoint shell script ile başlıyor (`apps/backend/Dockerfile:53`)

- `apps/backend/entrypoint.sh`
  - Caddy config’i runtime’da üretiyor
  - Caddy reverse proxy ile `localhost:5000` backend’e proxy yapıyor (`apps/backend/entrypoint.sh:27`)
  - Gunicorn + UvicornWorker ile backend başlatıyor (`--workers 2`) (`apps/backend/entrypoint.sh:42`)

### 3.2 Docker Compose ile backend + observability stack tanımlı

- `infra/docker-compose.yml`
  - `backend` servisi var (`infra/docker-compose.yml:7`)
  - ayrıca `prometheus`, `grafana`, `loki`, `promtail` tanımlı (`infra/docker-compose.yml:45`, `57`, `73`, `86`)
  - backend için wallet ve private key mount ediliyor (`infra/docker-compose.yml:29`, `31`)
  - uploads ve Caddy data named volume ile persist ediliyor (`infra/docker-compose.yml:33`, `35`, `99`)
  - backend healthcheck mevcut (`infra/docker-compose.yml:36`)

### 3.3 Oracle DB bağlantısı wallet path’e bağımlı

- `apps/backend/infrastructure/db_manager.py`
  - wallet klasörünü backend dizini altından bekliyor (`wallet_location = .../wallet`) (`apps/backend/infrastructure/db_manager.py:28`)
  - read/write pool `oracledb.create_pool(...)` ile wallet/config_dir üzerinden kuruluyor (`apps/backend/infrastructure/db_manager.py:33`, `47`)

Bu, deployment modelinde dosya mount / secret file yönetimini kritik hale getirir.

### 3.4 Firebase credentials path bağımlılığı var

- `apps/backend/config.py`
  - `GOOGLE_APPLICATION_CREDENTIALS` env path’i okunuyor (`apps/backend/config.py:46`)
  - production ortamında Firebase hazır değilse startup fail oluyor (app startup flow içinde)

### 3.5 Backend startup/lifespan ağır ve probe tuning gerektirir

- `apps/backend/app.py`
  - `lifespan` startup bloğu var (`apps/backend/app.py:276`, `277`)
  - startup içinde:
    - model version validation
    - Firebase readiness kontrolü
    - DB pool init (`DatabaseManager.init_pool()`) (`apps/backend/app.py:312`)
    - cache init
    - memory monitor background task
    - metrics updater background task
  - root health endpoint var (`@app.get("/")`) (`apps/backend/app.py:436`)

Bu yapı container üzerinde de çalışır, ancak startup/readiness timeout ayarı doğru yapılmalıdır.

---

## 4. “Docker ile rahat çalışıyor mu?” Değerlendirmesi (Kanıt Seviyesiyle)

### 4.1 Repo-level readiness: **Yes**

Backend containerization için gerekli temel yapı hazır:

- Dockerfile mevcut
- entrypoint script mevcut
- compose stack mevcut
- healthcheck mevcut
- reverse proxy (Caddy) runtime’a entegre

### 4.2 Compose syntax readiness: **Yes**

`docker compose -f infra/docker-compose.yml config` parse edildi (başarılı).

Not:
- `version` alanı için obsolete warning var (kritik değil)
- `docker compose config` çıktılarına secret değerleri dökülebiliyor; operasyonda dikkat edilmeli

### 4.3 Actual local build proof (bu çalışmada): **Not verified**

Bu çalışmada backend image build testini çalıştırma denemesi yapıldı ancak Docker daemon kapalıydı:

- `docker build -f apps/backend/Dockerfile apps/backend -t tomehub-backend-smokebuild:local`
- Hata: Docker Desktop Linux engine pipe erişilemedi (`dockerDesktopLinuxEngine`)

Bu durum:
- ürün/konfigürasyon hatası kanıtı değildir
- yalnızca **lokal makinede bu run sırasında daemon kapalı** olduğunu gösterir

### 4.4 Production-readiness (backend-only): **Yes, with ops setup requirements**

Docker ile production çalıştırma mümkündür, ancak şu kurallar zorunlu:

- wallet / key / Firebase creds güvenli mount
- persistent storage (Caddy cert + uploads) stratejisi
- startup/readiness timeout tuning
- worker/memory ayarı (özellikle düşük RAM shape’lerde)

---

## 5. OCI Container Instance Analizi (TomeHub’a Özel)

## 5.1 Güçlü yanlar

- Managed container runtime (host yönetimi yok)
- Backend-only, düşük trafik API workload için teorik olarak uygun olabilir
- OCI native container çalıştırma deneyimi basit olabilir

## 5.2 Mevcut TomeHub’a özel sürtünmeler

### A. Secrets ve file-path bağımlılığı

Mevcut sistemde:

- Oracle wallet klasörü mount ediliyor
- OCI private key file mount ediliyor
- Firebase credentials file path kullanılıyor

Container Instance ile bu yapılabilir, ama mevcut VM+Docker kadar doğal/kolay bir parity sağlamaz. Özellikle mevcut compose modelinden geçişte ops karmaşıklığı artar.

### B. Kalıcı storage ihtiyacı

Backend tarafında:

- `/app/uploads`
- `/data` (Caddy cert persistence)

ihtiyacı var. Container Instance tarafında volume modeli mevcut olsa da (EmptyDir/ConfigFile), persistent davranış ve operasyon modeli mevcut compose yaklaşımından farklıdır. EmptyDir tabanlı volume’lar **ephemeral** davranabilir.

### C. Startup/lifespan ağır

Backend startup’ta DB/Firebase/cache/background task başlatıyor. Bu da:

- health probe
- restart policy
- graceful shutdown

ayarlarını doğru tasarlamayı zorunlu kılıyor.

### D. Compose parity düşük

Localde compose ile çalışan sistemi prod’da Container Instance’a taşıdığında:

- aynı deployment modeli korunmuyor
- debug/diff analizi zorlaşıyor
- ops runbook’ları farklılaşıyor

## 5.3 Yeni kritik saha bulgusu (kullanıcı ekranı)

Kullanıcının OCI Console ekranında `eu-amsterdam-1` için Container Instance shape seçiminde:

- `No items to display`

görünüyor. Bu şu anlama gelebilir:

- region/AD capacity yok
- tenancy quota/policy/filter sorunu
- o bölgede shape availability kısıtı

Bu yüzden:

**Teknik olarak uygun bir servis olması**, **operasyonel olarak hemen kullanılabilir olduğu** anlamına gelmiyor.

> Bu raporda bu durum “provisioning risk” olarak değerlendirilmiştir.

---

## 6. OCI VM Analizi (Always Free AMD vs Ampere Arm)

## 6.1 AMD Always Free (`VM.Standard.E2.1.Micro`, 1 GB) — Production Primary için zayıf aday

### Neden riskli

Repo içi SRE raporunda memory pressure/OOM sinyalleri var:

- worker başına memory aralığı ve OOM riski işaretlenmiş (`documentation/reports/SRE_STRESS_TEST_REPORT.md:16`)
- memory pressure örnekleri (`documentation/reports/SRE_STRESS_TEST_REPORT.md:353`, `361`)
- OOM killer senaryosu (`documentation/reports/SRE_STRESS_TEST_REPORT.md:371`)
- “typical VM = 2GB” referansı var (`documentation/reports/SRE_STRESS_TEST_REPORT.md:672`)

Mevcut backend defaultları da hafif değil:

- DB pool default max `40` (`apps/backend/config.py:36`)
- read/write split pool max’lar türetiliyor (`apps/backend/config.py:42`, `43`)
- startup’ta DB pool + cache + background tasks çalışıyor

### Karar

`AMD 1GB`:
- **test / light staging / geçici deneme** için olabilir
- **production-primary backend** için önerilmez

## 6.2 Ampere A1 (`VM.Standard.A1.Flex`, Always Free bütçe içinde) — Primary aday

### Neden güçlü

- Daha yüksek RAM headroom (Always Free Ampere bütçesi altında esnek dağıtım)
- Docker + file mounts + debug/SSH operasyonu kolay
- Mevcut compose/Docker modeline daha yakın
- Düşük kullanımda bile stabil çalışma tamponu sağlar

### Dikkat edilmesi gerekenler

- ARM uyumluluğu build/run ile doğrulanmalı (Python deps / binary wheels)
- Always Free capacity bölgesel olarak değişebilir
- Bölge/AD değişimi gerekebilir

### Karar

Backend-only deployment için bugün en iyi aday:

**`OCI VM (Ampere A1) + Docker`**

---

## 7. Region Availability & Capacity Risk (Yeni Bölüm)

Bu analizde kritik saha verisi:

- `eu-amsterdam-1` Container Instance shape ekranında liste boş (`No items to display`)

Bu bilgi karar kuralını değiştirir:

### Karar kuralı

Availability belirsiz + ops önceliği yüksekse:

**VM lehine karar verilir**

Çünkü:

- VM tarafında alternatif AD/region ile deneme ve debug akışı daha olgun
- Container Instance’ta provisioning aşamasında takılma riski varsa düşük kullanım için bile zaman kaybı yaratır

### AB region esnekliği etkisi

AB içinde başka region kabul edildiği için:

- Container Instance tamamen elenmez
- ancak **primary olmaktan çıkar**
- **secondary / conditional** statüsüne iner

---

## 8. Weighted Decision Matrix (Düşük Kullanım + Basit Ops Önceliği)

### Ağırlıklar

- Operasyonel basitlik / debug: **30%**
- Gerçek provisioning uygulanabilirliği (region/shape): **20%**
- Always Free uyumu: **20%**
- Mevcut mimariyle sürtünmesizlik: **20%**
- Gelecek ölçeklenme esnekliği: **10%**

### Skor tablosu (1-5, yüksek daha iyi)

| Seçenek | Ops Basitliği (30) | Provisioning Uygulanabilirlik (20) | Always Free (20) | Mimari Uyum (20) | Gelecek Esneklik (10) | Toplam (100) | Yorum |
|---|---:|---:|---:|---:|---:|---:|---|
| OCI VM (Ampere A1) + Docker | 5 | 4 | 5 | 5 | 4 | **47/50 ≈ 94** | **Primary** |
| OCI Container Instance (AB region availability varsa) | 3 | 2 | 3 | 2 | 4 | **28/50 ≈ 56** | Secondary / conditional |
| OCI VM (AMD 1GB) + Docker | 4 | 4 | 5 | 4 | 2 | **39/50 ≈ 78** | Test/light staging; production primary değil (memory riski) |

Not:
- AMD 1GB puanı overall fena görünse de **memory headroom kritik risk** olduğu için production-primary’de veto edilir.
- Container Instance puanı özellikle **availability + file/secrets/storage sürtünmesi** yüzünden düşmektedir.

---

## 9. Nihai Öneri

## 9.1 Primary Recommendation

### `OCI Compute VM (Ampere A1, AB region) + Docker (backend-only deploy)`

**Neden:**

- Mevcut mimariyle en uyumlu (Docker + mount + Caddy + wallet)
- Düşük kullanım için stabil ve debug edilebilir
- Secrets/file path yönetimi daha basit
- Container Instance shape availability riskine göre daha yönetilebilir
- Ops runbook’ları mevcut repo yaklaşımına daha yakın

## 9.2 Secondary / Conditional Recommendation

### `OCI Container Instance (backend-only)`

Aşağıdaki koşullar sağlanırsa değerlendirilebilir:

- Hedef region/AD’de shape gerçekten create edilebiliyor
- Secrets ve file mount modeli yeniden düzenleniyor
- Caddy/cert persistence stratejisi netleşiyor (veya TLS katmanı ayrıştırılıyor)
- Startup/readiness probe’lar Container Instance davranışına göre test ediliyor

## 9.3 Not Recommended Now

### `OCI VM (AMD E2.1.Micro, 1 GB)` (production-primary backend)

**Sebep:** Memory headroom yetersizliği / OOM riskine açık yapı.

---

## 10. Operasyonel Uygulama Notları (Backend-only)

## 10.1 VM (Ampere A1) seçilirse

Önerilen yaklaşım:

1. Backend-only Docker deployment (gerekirse compose varyantı)
2. Wallet ve credential mount’ları read-only
3. Caddy cert persistence için kalıcı volume/dizin
4. Uploads için kalıcı dizin veya dış storage stratejisi
5. Startup/readiness timeout tuning
6. Worker sayısını RAM’e göre sınırla (gerekirse `workers=1`)
7. Basit monitoring/log rotation ekle

## 10.2 Container Instance seçilirse (şartlı)

Ön koşul checklist:

1. Region/AD shape availability doğrulandı mı?
2. Secrets injection yöntemi net mi?
3. Wallet ve Firebase credential file delivery modeli net mi?
4. Caddy cert persistence nasıl sağlanacak?
5. Uploads ephemeral mi, external mi?
6. Health probe + graceful shutdown test edildi mi?

Bu checklist geçmeden production-primary önerilmez.

---

## 11. Kararı Değiştirecek Trigger’lar

Bu koşullarda karar yeniden değerlendirilmeli:

- Trafik/concurrency belirgin artarsa
- Container Instance shape availability hedef region’da stabil hale gelirse
- Secrets/wallet yönetimi object storage + secrets service ile sadeleşirse
- Backend daha stateless hale gelirse (Caddy ayrışır, uploads dışsallaşır)
- OKE/Kubernetes veya çoklu servis orchestration ihtiyacı doğarsa

---

## 12. Kanıt Özeti (Bu Analizde Kullanılanlar)

## 12.1 Repo kanıtları

- `apps/backend/Dockerfile`
- `apps/backend/entrypoint.sh`
- `infra/docker-compose.yml`
- `apps/backend/infrastructure/db_manager.py`
- `apps/backend/config.py`
- `apps/backend/app.py`
- `documentation/reports/SRE_STRESS_TEST_REPORT.md`

## 12.2 Çalıştırılan kontroller (lokal)

- `docker compose -f infra/docker-compose.yml config` → **başarılı**
- `docker build ...` → **doğrulanamadı (Docker daemon kapalı)**

## 12.3 Kullanıcı saha kanıtı

- OCI Console (`eu-amsterdam-1`) Container Instance shape ekranında `No items to display`

## 12.4 OCI resmi dokümanlar (karşılaştırma için)

- OCI Always Free Resources (Compute VM limits / Ampere + AMD Always Free)
- OCI Container Instances docs (volume types, health check, shape/resource model)
- OCI Container Instances product page (service positioning)

> Güncel platform davranışı region/tenant bazında değişebileceği için provisioning sırasında console doğrulaması esas alınmalıdır.

---

## 13. Final Karar (Tek Cümle)

**Mevcut TomeHub backend mimarisi ve düşük kullanım senaryosunda, OCI Always Free önceliğiyle en doğru deployment modeli `Ampere A1 VM + Docker` olup, `Container Instance` bu aşamada yalnızca region availability ve secrets/storage modeli netleşirse secondary seçenek olarak değerlendirilmelidir.**

---

## 14. Kaynaklar (OCI)

- OCI Always Free Resources: https://docs.oracle.com/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm
- OCI Container Instances product page: https://www.oracle.com/cloud/cloud-native/container-instances/
- OCI Container Instances (Terraform provider resource doc, volumes/health checks fields): https://docs.oracle.com/en-us/iaas/tools/terraform-provider-oci/7.7.0/docs/r/container_instances_container_instance.html
- OCI Container Instances common types (official OCI docs family, volume/health check types): https://docs.oracle.com/en-us/iaas/Content/pl-sql-sdk/doc/container_instances_t.html

