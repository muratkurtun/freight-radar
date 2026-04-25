# Soft Launch Runbook — Opportunity Radar MVP

**Yol:** B (kodda enforcement yok, dış güvenlik ağları aktif)
**Tarih:** soft launch günü
**Operatör:** sen + 1 backup kişi (LE renewal email + bu doc)

---

## 0. Placeholders — bu satırları kafanda tut, runbook'tan geçerken ikame et

| Yer tutucu | Açıklama |
|---|---|
| `<DOMAIN>` | Asıl domain, ör. `opportunityradar.com` |
| `<REPO_URL>` | Git URL, ör. `git@github.com:you/opportunity-radar.git` |
| `<LE_EMAIL>` | Let's Encrypt email |
| `<SERVER_IP>` | Hetzner Cloud server'ın public IP'si |
| `<ANTHROPIC_API_KEY>` | Anthropic console'dan, soft launch'tan önce **hard limit ayarlı olmalı** |
| `<ADMIN_EMAIL>` / `<ADMIN_PASSWORD>` | İlk register'ı kimle yapacağın |

`<DOMAIN>` DNS'inde A record `<SERVER_IP>`'ye, `www.<DOMAIN>` CNAME `<DOMAIN>`'e işaret etmeli. Soft launch'tan ≥30 dk önce DNS yayınla (TTL 300s öner).

---

## 1. Hetzner sunucu ilk kurulum

Hetzner Cloud Console (web):

1. **Add Server**
   - Location: Nuremberg veya Helsinki
   - Image: **Ubuntu 24.04**
   - Type: **CX22** (2 vCPU / 4 GB / 40 GB SSD, ~€4.50/ay)
   - Networking: IPv4 + IPv6 ON
   - SSH Keys: kendi public key'ini ekle (Hetzner panel'den)
   - Firewalls: aşağıdaki "Hetzner Firewall" kuralı seçili
   - Volumes: yok (40GB disk yeter)
   - Name: `opportunity-radar-prod`

2. **Hetzner Cloud Firewall** (Server'ı oluşturmadan önce yarat, server'a attach et):
   ```
   Inbound:
     22/tcp    from 0.0.0.0/0, ::/0
     80/tcp    from 0.0.0.0/0, ::/0
     443/tcp   from 0.0.0.0/0, ::/0
   Outbound: allow all
   ```

3. **DNS** (registrar / DNS provider):
   ```
   <DOMAIN>      A      <SERVER_IP>     TTL 300
   www.<DOMAIN>  CNAME  <DOMAIN>        TTL 300
   ```
   Doğrulama (lokalden):
   ```bash
   dig +short <DOMAIN>
   # → <SERVER_IP> dönmeli
   ```

4. **İlk SSH erişimi:**
   ```bash
   ssh root@<SERVER_IP>
   ```
   Hetzner ilk login'de bir password değişikliği isteyebilir; SSH key kullandıysan zaten girersin.

⚠ **DNS yayılana kadar SSL adımına geçme.** Let's Encrypt domain doğrulaması başarısız olur ve cert bootstrap'i kirletir.

---

## 2. Ubuntu güvenlik ayarları + Docker + Compose + UFW + Swap (tek script)

Repo'da `ops/server-setup.sh` zaten her şeyi idempotent halletiyor. Lokalden upload + çalıştır:

```bash
# Lokalden (repo root'undan):
scp ops/server-setup.sh root@<SERVER_IP>:/root/

# Sunucuda (root SSH):
ssh root@<SERVER_IP>
bash /root/server-setup.sh
```

Script şunları yapar (~3 dk):
- apt update + base paketler (curl, git, gnupg, ufw, fail2ban, unattended-upgrades, cron)
- Timezone UTC
- Docker Engine + Compose plugin (resmi apt repo)
- Docker log rotation (10m × 3 file)
- `deploy` user + docker/sudo grupları + passwordless sudo
- root'un `authorized_keys`'ini deploy'a kopyala
- SSH hardening (root login + password auth kapalı) → **sshd -t validate sonrası restart**
- UFW: 22/80/443 allow, gerisi deny
- fail2ban + unattended-upgrades aktif
- 2GB swap
- `/opt/opportunity-radar`, `/opt/or-backups` dizinleri

⚠ **deploy user'ın authorized_keys'i yoksa script SSH hardening'i atlar.** Çıktıyı oku — uyarı varsa `/home/deploy/.ssh/authorized_keys` dosyasını manuel doldur, scripti tekrar çalıştır.

Doğrulama:
```bash
# Yeni terminal:
ssh deploy@<SERVER_IP>
docker ps                 # boş liste, izin var
docker compose version    # v2.x
sudo ufw status verbose   # 22, 80, 443 ALLOW
free -h                   # 2GB swap görünür
```

Bu noktadan sonra **`root` SSH kapalı**. Her şey `deploy` user'ı altında.

---

## 3. Docker + Compose kurulumu

Adım 2'de bitti — `server-setup.sh` resmi apt repo'sundan kuruyor. Doğrulama yukarıda.

---

## 4. Nginx kurulumu

⚠ **Host'a nginx YÜKLEMİYORUZ.** Nginx, `docker-compose.prod.yml` içinde container olarak çalışıyor; 80/443'ü o dinleyecek. Host nginx kurmak port çakıştırır.

UFW'da 80/443 zaten açık (adım 2). Port'ların dolu olmadığını doğrula:
```bash
ssh deploy@<SERVER_IP>
sudo ss -ltnp | grep -E ':(80|443)\b' || echo "ports free"
```
Çıktı: `ports free`. (Container ayağa kalktıktan sonra burada nginx görünecek — normal.)

---

## 5. Domain / subdomain yönlendirme mantığı

Tek domain, path-based routing — soft launch için en sade:

| URL | Ne yapar |
|---|---|
| `https://<DOMAIN>/` | Angular bundle (login, register, trial-*, opportunities, ...) |
| `https://<DOMAIN>/api/*` | FastAPI backend (proxy_pass trailing slash ile `/api` strip) |
| `https://www.<DOMAIN>/*` | Aynı server_name, aynı bundle |
| `http://<DOMAIN>/*` | 301 → https |

`api.<DOMAIN>` veya `app.<DOMAIN>` ayırma **yapma** — soft launch için ekstra cert + CORS karmaşıklığı, faydası yok.

---

## 6. SSL kurulumu — Let's Encrypt

Adım 13'teki `first-deploy.sh` scripti `init-letsencrypt.sh`'i otomatik çağırır. Manuel akışı bilmen gerekirse:

1. Nginx config'inde `${DOMAIN}` placeholder'ı `<DOMAIN>` ile değiştirilir (script yapar)
2. `init-letsencrypt.sh`:
   - Dummy self-signed cert üret (nginx boot edebilsin)
   - Nginx başlat
   - Dummy'yi sil, `certbot certonly --webroot` ile gerçek cert iste
   - Nginx reload
3. `certbot` sidecar container'ı 12 saatte bir `certbot renew`. Cert 30 günden taze ise no-op.

⚠ **Önce staging cert ile dene** (rate-limit yememek için):
```bash
# first-deploy.sh çalıştırmadan önce, isteğe bağlı:
ssh deploy@<SERVER_IP>
cd /opt/opportunity-radar
STAGING=1 ./ops/init-letsencrypt.sh <DOMAIN> <LE_EMAIL>
# Browser'da self-signed uyarı görürsen yapı doğru → STAGING=0 ile gerçek cert
```

---

## 7. Proje klasör yapısı

`server-setup.sh` zaten yarattı, `first-deploy.sh` doldurur:

```
/opt/opportunity-radar/        ← repo clone (deploy:deploy, 755)
├── backend/
├── frontend/
├── docker-compose.prod.yml
├── ops/
│   ├── nginx/
│   │   ├── nginx.conf
│   │   └── conf.d/opportunity-radar.conf
│   ├── init-letsencrypt.sh
│   ├── first-deploy.sh
│   ├── server-setup.sh
│   └── backup/
│       ├── pg_backup.sh
│       └── pg_restore.sh
├── .env                       ← chmod 600, deploy:deploy, .gitignore'da
├── .cert-issued-<DOMAIN>      ← bootstrap sentinel (otomatik)
└── ...

/opt/or-backups/               ← daily pg_dump dosyaları (deploy:deploy)
/var/log/or-backup.log         ← cron log
```

---

## 8. `.env` production örneği

`first-deploy.sh` ilk çalışmada `.env`'i otomatik üretir (JWT_SECRET + POSTGRES_PASSWORD random). Ama bilmen gereken son hali — soft launch için **Yol B**'ye uygun:

```bash
# /opt/opportunity-radar/.env  — chmod 600, .gitignore'da

APP_ENV=production
APP_DEBUG=false
APP_HOST=0.0.0.0
APP_PORT=8000

DOMAIN=<DOMAIN>
LETSENCRYPT_EMAIL=<LE_EMAIL>

# Postgres
POSTGRES_USER=opr
POSTGRES_PASSWORD=<openssl rand 32 chars>
POSTGRES_DB=opportunity_radar

# Auth
JWT_SECRET=<openssl rand 64 chars>
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=60

# LLM
ANTHROPIC_API_KEY=<ANTHROPIC_API_KEY>
LLM_MODEL=claude-haiku-4-5-20251001

# Scheduler — soft launch START: KAPALI. Manuel test sonrası adım 19'da aç.
SCHEDULER_ENABLED=false
PIPELINE_INTERVAL_MINUTES=120

# Trial
TRIAL_DAYS=7

# ⚠ AŞAĞIDAKİ ÜÇ DEĞİŞKEN ŞU AN KODDA ENFORCE EDİLMİYOR (Yol B kararı).
# Belgelenmiş niyet olarak duruyorlar. Gerçek koruma:
#   - MAX_ITEMS_PER_QUERY: scheduler kapalı + manuel test ile sınırlı
#   - AI_DAILY_CALL_LIMIT: Anthropic Console'da hard limit (adım 20)
#   - PUBLIC_REGISTER_ENABLED: zaten her zaman 'true' davranışı geçerli
MAX_ITEMS_PER_QUERY=3
AI_DAILY_CALL_LIMIT=50
PUBLIC_REGISTER_ENABLED=true
```

⚠ **Sırlar:** `JWT_SECRET` rotate edilirse tüm kullanıcı session'ları invalidate olur. Soft launch'ta bunu yapma; gerçekten gerekli olduğunda zaten birkaç kullanıcı vardır, planlı yapılır.

---

## 9. `docker-compose.prod.yml`

Repoda zaten var (`/opt/opportunity-radar/docker-compose.prod.yml`). Soft launch'tan önce sadece **bir kontrol**:

```bash
ssh deploy@<SERVER_IP>
cd /opt/opportunity-radar
grep -E 'SCHEDULER_ENABLED|TRIAL_DAYS|PIPELINE_INTERVAL|CORS_ORIGINS' docker-compose.prod.yml
```
Beklenen: 5 satır görünmeli, hepsi `${VARIABLE_NAME}` formatında `.env`'den okuyacak şekilde.

`CORS_ORIGINS: https://${DOMAIN}` satırı önemli — sadece prod domain CORS'da. Dev/localhost yok.

---

## 10. Backend Dockerfile kontrolü

```bash
ssh deploy@<SERVER_IP>
cd /opt/opportunity-radar
grep -E '^(FROM|CMD|EXPOSE)' backend/Dockerfile
```

Beklenen son satır:
```
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

⚠ `--reload` **olmamalı**. Olursa prod'da her dosya değişikliğinde restart eder. Mevcut dosyada yok, sadece dev compose `command:` ile override ediyor; teyit edelim:
```bash
grep -- '--reload' docker-compose.prod.yml
# çıktı boş olmalı
```

---

## 11. Angular production build kontrolü

```bash
cd /opt/opportunity-radar
grep -E '^FROM|^CMD|configuration production|browser' frontend/Dockerfile.prod
```

Beklenen:
- `FROM node:22-alpine AS build` (build stage)
- `RUN npx ng build --configuration production`
- `FROM nginx:1.27-alpine AS runtime`
- `COPY --from=build /app/dist/opportunity-radar-admin/browser /usr/share/nginx/html`

`environment.prod.ts` API base URL kontrolü:
```bash
cat frontend/src/environments/environment.prod.ts
# apiBaseUrl: '/api'   olmalı  (NOT http://localhost:8000)
```

⚠ Eğer geliştirme tarafında bu değeri değiştirdiyseniz, prod build yanlış URL ile gider, frontend backend'e ulaşamaz. Dosyayı kontrol et.

---

## 12. Migration çalıştırma sırası

`first-deploy.sh` otomatik yapar. Manuel sıralama (referans):

```bash
cd /opt/opportunity-radar

# Postgres ayağa kalkmış ve healthy olmalı
docker compose -f docker-compose.prod.yml up -d postgres
docker compose -f docker-compose.prod.yml ps postgres
# STATUS sütunu: Up X seconds (healthy) görünmeli

# Şema:
docker compose -f docker-compose.prod.yml run --rm backend alembic upgrade head
# beklenen son satırlar:
#   Running upgrade  -> 0001_initial
#   Running upgrade 0001_initial -> 0002_user_full_name
#   Running upgrade 0002_user_full_name -> 0003_tenant_trial

# Doğrulama:
docker compose -f docker-compose.prod.yml run --rm backend alembic current
# 0003_tenant_trial (head)
```

⚠ Migration sırası kritik: backend container'ı app servisleri ayağa kalkmadan önce şema **mutlaka** `0003_tenant_trial` olmalı. Yoksa register endpoint'i `subscription_status` kolonunu bulamaz, 500 döner.

---

## 13. İlk `docker-compose up` adımı — `first-deploy.sh`

Soft launch'ın **tek komutluk** kalbi. Lokalden:

```bash
# 1. Scripti deploy user'a upload (eğer repo henüz clone edilmemişse):
scp ops/first-deploy.sh deploy@<SERVER_IP>:~/
```

Sunucuda:
```bash
ssh deploy@<SERVER_IP>

REPO_URL=<REPO_URL> \
DOMAIN=<DOMAIN> \
LETSENCRYPT_EMAIL=<LE_EMAIL> \
ANTHROPIC_API_KEY=<ANTHROPIC_API_KEY> \
bash ~/first-deploy.sh
```

Script şunları sırayla yapar:
1. Sanity (docker erişimi)
2. Repo clone → `/opt/opportunity-radar`
3. `.env` üret (random secrets)
4. Nginx config'inde `${DOMAIN}` → `<DOMAIN>` substitution
5. `docker compose build --pull`
6. Postgres başlat, healthy bekle
7. `alembic upgrade head`
8. Let's Encrypt cert (sentinel'e bağlı, ilk çalışmada işler)
9. Tüm stack `up -d`
10. `https://<DOMAIN>/api/health` smoke test
11. Her servisin son 25 satır log'unu yazdır
12. Nightly backup cron kur

**İlk çalışmada ~6-8 dk** (image build + cert).

⚠ Çıktıyı oku, kırmızı `XX` veya sarı `!!` satırı varsa devam etme.

---

## 14. Healthcheck kontrolleri

```bash
ssh deploy@<SERVER_IP>
cd /opt/opportunity-radar

# 1. Container durumu
docker compose -f docker-compose.prod.yml ps
```
Beklenen 5 servis: `postgres (healthy)`, `backend`, `frontend`, `nginx`, `certbot` — hepsi `Up`.

```bash
# 2. Backend health
curl -fsS https://<DOMAIN>/api/health
# {"status":"ok"}

# 3. HSTS + redirect
curl -sI http://<DOMAIN>/
# HTTP/1.1 301 Moved Permanently
# Location: https://<DOMAIN>/

curl -sI https://<DOMAIN>/ | grep -i 'strict-transport-security'
# strict-transport-security: max-age=31536000; includeSubDomains

# 4. Postgres
docker exec or_postgres pg_isready -U opr
# /var/run/postgresql:5432 - accepting connections

# 5. Disk
df -h /
# %Use < 30%
```

---

## 15. Register / login testleri

Sırayla, gerçek smoke flow:

```bash
# 1. REGISTER (yeni tenant + admin user + 7 gün trial)
curl -sS -X POST https://<DOMAIN>/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_name": "Smoke Test Co",
    "full_name":   "Smoke Test",
    "email":       "<ADMIN_EMAIL>",
    "password":    "<ADMIN_PASSWORD>"
  }' | tee /tmp/register.json
# beklenen: {"access_token":"...","token_type":"bearer","user":{...,"subscription_status":"trial","trial_ends_at":"..."}}

TOKEN=$(jq -r .access_token /tmp/register.json)
# jq yoksa: TOKEN=$(grep -oP '"access_token":"[^"]+' /tmp/register.json | cut -d'"' -f4)

# 2. ME
curl -sS https://<DOMAIN>/api/auth/me \
  -H "Authorization: Bearer $TOKEN" | jq
# {"user_id":"...", "subscription_status":"trial", "trial_ends_at":"...", ...}

# 3. LOGIN (ayrı session)
curl -sS -X POST https://<DOMAIN>/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"<ADMIN_EMAIL>","password":"<ADMIN_PASSWORD>"}' \
  | jq -r .access_token
# 64+ char JWT dönmeli

# 4. Yanlış parola → opak 401
curl -sS -X POST https://<DOMAIN>/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"<ADMIN_EMAIL>","password":"WRONG"}' | jq
# {"error":{"code":"unauthorized","message":"Invalid email or password"}}

# 5. Aynı email ile ikinci register → 409
curl -sS -X POST https://<DOMAIN>/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"tenant_name":"X","full_name":"X","email":"<ADMIN_EMAIL>","password":"AnotherPass1"}' | jq
# {"error":{"code":"conflict","message":"An account with this email already exists"}}
```

---

## 16. Trial testleri

Trial happy path adım 15'te zaten geçti (`subscription_status:"trial"` döndü). Şimdi expired test:

```bash
# 1. Tenant'ın trial_ends_at'ini DB'de geriye al (tek smoke için):
docker exec -it or_postgres psql -U opr -d opportunity_radar -c "
  UPDATE tenants
     SET trial_ends_at = NOW() - INTERVAL '1 hour'
   WHERE slug = 'smoke-test-co';
"

# 2. Şimdi /api/opportunities → 403 trial_expired
curl -sS https://<DOMAIN>/api/opportunities \
  -H "Authorization: Bearer $TOKEN" | jq
# {"error":{"code":"trial_expired","message":"Your trial has ended"}}

# 3. Ama /auth/me hâlâ çalışmalı (gate dışı)
curl -sS https://<DOMAIN>/api/auth/me \
  -H "Authorization: Bearer $TOKEN" | jq .subscription_status
# "expired"

# 4. Geri al (smoke tenant'ı temizle):
docker exec -it or_postgres psql -U opr -d opportunity_radar -c "
  UPDATE tenants
     SET trial_ends_at = NOW() + INTERVAL '7 days'
   WHERE slug = 'smoke-test-co';
"
```

⚠ Smoke tenant'ı tutmak istemezsen launch'tan önce sil:
```bash
docker exec -it or_postgres psql -U opr -d opportunity_radar -c "
  DELETE FROM tenants WHERE slug = 'smoke-test-co';
"
# CASCADE ile user + signals + reviews da gider.
```

---

## 17. Manuel pipeline run testi

Önce en az 1 kaynak ekle (admin JWT ile):

```bash
# Smoke tenant admin token'ı (adım 15'teki TOKEN hâlâ geçerliyse onu kullan):
curl -sS -X POST https://<DOMAIN>/api/sources \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "source_type": "news",
    "name":        "BBC News Business",
    "url":         "https://feeds.bbci.co.uk/news/business/rss.xml",
    "is_active":   true
  }' | jq

# Pipeline'ı manuel tetikle:
curl -sS -X POST https://<DOMAIN>/api/pipeline/run \
  -H "Authorization: Bearer $TOKEN" | jq
# {"status":"accepted","tenant_id":"...","message":"Pipeline run scheduled"}

# 30-60 sn bekle, sonra runs listesini gör:
sleep 60
curl -sS https://<DOMAIN>/api/pipeline-runs \
  -H "Authorization: Bearer $TOKEN" | jq '.items[0]'
# status: "success" veya "failed", error_message null veya stack trace
```

Backend log'larında pipeline tick'i izle:
```bash
docker compose -f docker-compose.prod.yml logs --tail 100 backend | grep -E 'tick|run|signal'
```

⚠ **Maliyet uyarısı:** RSS feed'inde 30+ haber varsa, prefilter'dan geçenler her biri için bir Anthropic çağrısı atılır. Soft launch'ta bir tek manuel tetikleme yeterli. **Manuel tetiği döngüye alma** — adım 19'da scheduler'ı açana kadar.

---

## 18. Scheduler'ı ilk etapta kapalı başlatma

`.env`'de zaten:
```
SCHEDULER_ENABLED=false
```

Doğrula:
```bash
docker exec or_backend env | grep SCHEDULER
# SCHEDULER_ENABLED=false

docker compose -f docker-compose.prod.yml logs backend | grep -i scheduler
# "Scheduler disabled by config (scheduler_enabled=False)"
```

Bu mod'da:
- APScheduler **hiç başlamaz**
- `pipeline_runs` tablosunda yeni satır oluşmaz (manuel `/pipeline/run` hariç)
- Anthropic'e otomatik çağrı **YOK** — bütçe sıfır maruz

Soft launch ilk 24 saati bu mod'da kalsın.

---

## 19. Scheduler'ı güvenli şekilde açma

**Açma kararı kriterleri** (24 saat sonra):
- [ ] Manuel `/pipeline/run` ≥ 2 kez başarılı, hata yok
- [ ] Anthropic console'da maliyet beklenenle uyumlu (adım 20)
- [ ] Pending review queue makul (sayı ≤ 50)
- [ ] `pipeline_runs.error_message` null
- [ ] Logs'ta exception yok

**Açma adımı:**
```bash
ssh deploy@<SERVER_IP>
cd /opt/opportunity-radar

# Edit .env:
sed -i 's/^SCHEDULER_ENABLED=false/SCHEDULER_ENABLED=true/' .env
grep SCHEDULER_ENABLED .env
# SCHEDULER_ENABLED=true

# Sadece backend'i restart (postgres ve diğerleri etkilenmez):
docker compose -f docker-compose.prod.yml up -d --no-deps backend

# Scheduler log'unu izle:
docker compose -f docker-compose.prod.yml logs -f backend | grep -i 'scheduler\|tick'
```

İlk 5 dakika izle. Beklenen log satırı:
```
Scheduler started job=pipeline_all_tenants interval_minutes=120
Scheduled pipeline tick started
```

`PIPELINE_INTERVAL_MINUTES=120` olduğu için ilk otomatik tick **boot anında** atılır (`next_run_time=utcnow()` config'imize gereği), sonra 120 dakikada bir.

⚠ İlk tick'ten sonra 30 dk Anthropic console'u izle. Anormal faturalama varsa anında kapat:
```bash
sed -i 's/^SCHEDULER_ENABLED=true/SCHEDULER_ENABLED=false/' .env
docker compose -f docker-compose.prod.yml up -d --no-deps backend
```

---

## 20. AI API maliyet limitleri

⚠ **Yol B'nin kritik bağımlılığı.** Kod tarafında hiçbir cap yok; tüm güvenlik Anthropic Console'da.

**Anthropic Console (https://console.anthropic.com):**

1. **Billing → Usage limits:**
   - **Hard limit:** $20/ay (soft launch için makul)
   - **Soft limit (alert):** $10/ay → email gönderir
   - Hard limit aşılırsa Anthropic **API'yi 429 ile kapatır**, fatura kontrol altında kalır

2. **API key:** soft launch için **dedicated key** üret (tenant başına değil, bu deployment için tek key). Acil durumda `.env`'i değiştirip backend restart → 30 sn'de yeni key aktif.

3. **Model pinning:** `LLM_MODEL=claude-haiku-4-5-20251001` — Haiku ucuz (~$0.25/M input token). Sonnet'e **YANLIŞLIKLA** geçmek (~10x maliyet) için model adını manuel kontrol et.

`.env`'deki uyarı satırlarını da hatırla — `MAX_ITEMS_PER_QUERY` ve `AI_DAILY_CALL_LIMIT` sadece dokümante intent. Real cap = Anthropic Console hard limit.

**Soft launch ilk 48 saat:**
```bash
# Günde 1 kere bak — 2 dk işin
open https://console.anthropic.com/settings/billing
# Daily cost: <$0.50 normal soft launch için.
# >$2/gün → bir şey terslik var, scheduler'ı kapat ve incele.
```

---

## 21. PostgreSQL volume + backup

**Volume:** `pg_data` named volume.
```bash
docker volume inspect opportunity-radar_pg_data
# "Mountpoint": "/var/lib/docker/volumes/opportunity-radar_pg_data/_data"
```
Bu dizini **manuel silme**. `docker compose down` (volume kalır) güvenli; `down -v` her şeyi siler.

**Backup cron** — `first-deploy.sh` zaten kurdu. Doğrula:
```bash
crontab -l
# 0 3 * * * /opt/opportunity-radar/ops/backup/pg_backup.sh >> /var/log/or-backup.log 2>&1
```

**Manuel backup test (launch'tan önce ZORUNLU):**
```bash
# Lokalde dump al:
/opt/opportunity-radar/ops/backup/pg_backup.sh

ls -lh /opt/or-backups/
# or_<timestamp>.sql.gz dosyası, boyut > 10KB

# Restore prova (TEST DB'sine, prod'a değil):
docker exec -it or_postgres psql -U opr -d postgres -c "CREATE DATABASE restore_test;"
gunzip -c /opt/or-backups/or_<timestamp>.sql.gz | \
  docker exec -i or_postgres psql -U opr -d restore_test
docker exec -it or_postgres psql -U opr -d restore_test -c "SELECT COUNT(*) FROM tenants;"
docker exec -it or_postgres psql -U opr -d postgres -c "DROP DATABASE restore_test;"
```

⚠ **Off-site backup yok** (Yol B kararı). 7 gün lokal retention. Hetzner Cloud snapshot (haftalık, ~€0.50/ay) opsiyonel ek güvenlik:
- Hetzner Console → Server → Snapshots → "Take snapshot"

---

## 22. Log izleme komutları

```bash
ssh deploy@<SERVER_IP>
cd /opt/opportunity-radar
COMPOSE='docker compose -f docker-compose.prod.yml'

# Tüm servisler, canlı:
$COMPOSE logs -f --tail 50

# Tek servis:
$COMPOSE logs -f --tail 100 backend
$COMPOSE logs -f --tail 100 nginx
$COMPOSE logs -f --tail 100 postgres

# Son 1 saatte error/exception:
$COMPOSE logs --since 1h backend | grep -iE 'error|exception|traceback'

# Pipeline tick'leri:
$COMPOSE logs --since 6h backend | grep -i 'tick\|pipeline'

# Anthropic çağrı izi:
$COMPOSE logs --since 6h backend | grep -i 'llm\|anthropic'

# Nginx 5xx:
$COMPOSE logs --since 1h nginx | grep -E ' 5[0-9]{2} '

# Postgres slow query (1sn+):
$COMPOSE exec postgres psql -U opr -d opportunity_radar -c \
  "SELECT calls, mean_exec_time, query FROM pg_stat_statements ORDER BY mean_exec_time DESC LIMIT 10;" \
  2>/dev/null || echo "pg_stat_statements not enabled (OK for MVP)"
```

⚠ Log rotation: Docker daemon `/etc/docker/daemon.json` ile her container'a 10m × 3 file (server-setup.sh kurdu). Manuel rotation kontrolü:
```bash
docker inspect --format='{{json .HostConfig.LogConfig}}' or_backend | jq
# {"Type":"json-file","Config":{"max-file":"3","max-size":"10m"}}
```

---

## 23. Rollback planı

**Senaryo A — Code rollback (deploy sonrası backend bug):**

```bash
ssh deploy@<SERVER_IP>
cd /opt/opportunity-radar

# Hangi commit deploy edildi:
git log --oneline -5

# Önceki çalışan commit'e dön:
git reset --hard <previous-good-sha>

# Rebuild + restart:
docker compose -f docker-compose.prod.yml build backend frontend
docker compose -f docker-compose.prod.yml up -d backend frontend

# Smoke:
curl -fsS https://<DOMAIN>/api/health
```

⚠ **Schema-incompatible rollback:** Eğer rollback'te alembic migration geri alınması gerekiyorsa:
```bash
docker compose -f docker-compose.prod.yml run --rm backend alembic downgrade -1
```
Riskli. Yapmadan önce backup al (yapılmış olmalı).

**Senaryo B — Veri rollback (yanlış migration / data corruption):**

```bash
# 1. Stack'i durdur:
docker compose -f docker-compose.prod.yml stop backend frontend nginx

# 2. Postgres ayakta:
docker compose -f docker-compose.prod.yml ps postgres

# 3. Backup'tan restore (en son backup):
LATEST=$(ls -t /opt/or-backups/or_*.sql.gz | head -1)
echo "Restoring from: $LATEST"

# pg_restore.sh DB'yi drop edip yeniden oluşturur:
/opt/opportunity-radar/ops/backup/pg_restore.sh $LATEST

# 4. Stack'i kaldır:
docker compose -f docker-compose.prod.yml up -d
```

**Senaryo C — Tüm sunucu felaketi:**
- Hetzner snapshot varsa: Hetzner Console → Snapshots → "Rebuild from snapshot"
- Yoksa: yeni server + bu runbook'u baştan uygula + en son `.sql.gz`'yi laptop'tan restore et
- RTO: ~30 dk (snapshot ile), ~2 saat (sıfırdan)

---

## 24. Soft launch checklist

Launch'tan **30 dakika önce** her satırın yanına ✓ at:

### Sunucu / network
- [ ] DNS A record `<SERVER_IP>`'ye işaret ediyor (`dig +short <DOMAIN>`)
- [ ] DNS yayılma onaylandı (ikinci farklı DNS resolver'dan da test)
- [ ] Hetzner firewall: 22/80/443 only
- [ ] UFW: 22/80/443 only
- [ ] SSH: root login kapalı, password auth kapalı

### Container'lar
- [ ] `docker compose ps` → 5 servis Up, postgres healthy
- [ ] Backend container env: `SCHEDULER_ENABLED=false`, `APP_ENV=production`, `APP_DEBUG=false`
- [ ] Migration: `alembic current` = `0003_tenant_trial`

### TLS
- [ ] `https://<DOMAIN>/` → 200 + HSTS header
- [ ] `http://<DOMAIN>/` → 301 → https
- [ ] Cert expiry > 60 gün (`echo | openssl s_client -connect <DOMAIN>:443 2>/dev/null | openssl x509 -noout -enddate`)

### Smoke
- [ ] `/api/health` → 200
- [ ] `/api/auth/register` ile yeni tenant açıldı
- [ ] `/api/auth/login` çalışıyor
- [ ] `/api/auth/me` `subscription_status:"trial"` döndürdü
- [ ] Trial expired simülasyonu yapıldı, 403 `trial_expired` doğrulandı, geri alındı
- [ ] Smoke tenant temizlendi (veya tutuluyorsa not düşülmüş)

### Backup / cost
- [ ] `pg_backup.sh` manuel çalıştırıldı, `.sql.gz` üretti
- [ ] `pg_restore.sh` test DB'sine restore prova edildi
- [ ] `crontab -l` → backup cron 03:00 var
- [ ] Anthropic Console hard limit ≤ $20, soft alert $10
- [ ] LLM_MODEL `claude-haiku-4-5-*` (Sonnet değil)

### İletişim / izleme
- [ ] UptimeRobot monitor: `https://<DOMAIN>/api/health`, 5 dk interval, email alert
- [ ] SSL expiry monitor (UptimeRobot free tier)
- [ ] Bu runbook ekibin erişebildiği bir yerde (Notion / git repo README)
- [ ] Acil rollback komutu (adım 23) ezberde

### Frontend
- [ ] `https://<DOMAIN>/login` browser'da render ediyor
- [ ] `https://<DOMAIN>/register` form gösteriyor
- [ ] Browser console'da error yok
- [ ] Mobil tarayıcı testi (responsive bozuk değil)

**Çıkış:** 30 satırda ≥28 ✓ → **GO**.
Eksik 1-2 madde varsa, kritik olmadığını teyit et + not düş + go.
Daha fazlası varsa launch'ı 1-2 saat ertele.

---

## 25. İlk 48 saat metrikleri

Senior hat: **bu süreyi ekran başında geçirme.** Yapılandırılmış check'ler bırak, alarm seni çağırsın.

### Pasif (alarm)
- **UptimeRobot** → `/api/health` 5 dk down → email + SMS
- **Anthropic Console** → soft alert $10 → email
- **SSL expiry** → 14 gün önce → email

### Aktif (sen bakacaksın)

**T+1 saat:**
```bash
ssh deploy@<SERVER_IP>
cd /opt/opportunity-radar
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml logs --since 1h backend | grep -iE 'error|exception' | wc -l
# ≤ 3 satır beklenir (login fail vs)
```

**T+6 saat:**
```bash
# Disk + memory
df -h /
free -h

# Container resource:
docker stats --no-stream

# Anthropic Console — daily cost:
# < $0.10 (scheduler kapalı + manuel test = beklenen)
```

**T+24 saat — scheduler açma kararı:**
```bash
# Pending tenant + signal sayıları:
docker exec or_postgres psql -U opr -d opportunity_radar -c "
SELECT
  (SELECT COUNT(*) FROM tenants WHERE is_active) AS active_tenants,
  (SELECT COUNT(*) FROM tenants WHERE subscription_status='trial') AS trial_tenants,
  (SELECT COUNT(*) FROM detected_signals) AS signals_total,
  (SELECT COUNT(*) FROM detected_signals WHERE review_status='pending_review') AS pending,
  (SELECT COUNT(*) FROM pipeline_runs WHERE status='failed') AS failed_runs;
"

# Eğer:
#   failed_runs = 0
#   pending < 50
#   Anthropic cost < $1
# → Scheduler aç (adım 19).
```

**T+48 saat — soft launch raporu:**

İzlenecek 7 metrik:

| Metrik | Sorgu | Kabul aralığı |
|---|---|---|
| Active tenants | `SELECT COUNT(*) FROM tenants WHERE is_active` | beklenenle uyumlu |
| Trial tenants | `WHERE subscription_status='trial'` | %80+ trial normal |
| Pipeline run success | `pipeline_runs WHERE started_at > NOW()-48h` → status dağılımı | success ≥ %90 |
| Signals/24h | `detected_signals WHERE created_at > NOW()-24h` | varsa kabul, sıfırsa source/prompt sorunu |
| Approval rate | `signal_reviews` 48h içinde | ≥ %40 (low base rate normal) |
| LLM cost (Anthropic) | console daily | <$2/gün |
| Disk usage | `df -h /` | < %50 |
| Memory usage | `free -h` | swap kullanımı < 200MB |
| Error rate | `nginx logs 5xx` count | < 1/dk |

48 saat sonunda metrikleri tek satırda yaz, bir hafta sonra kohort karşılaştırması için sakla:

```
2026-04-27 08:00 UTC  | tenants=3 trial=3  runs=12 success=12 failed=0
                      | signals=47 approved=21 rejected=8 pending=18
                      | llm_cost=$1.23  disk=12% memory=52%
                      | errors_24h=2 (both auth-related)
```

---

## Appendix: Tek mesajlık özet

Bu runbook'u uygulamak için **lokalde** sırayla çalıştıracağın komutlar (placeholder'lar dolmuş varsayımıyla):

```bash
# 1. Hetzner'da server provision (Console)
# 2. DNS A record set, yayılma bekle
# 3. Server bootstrap:
scp ops/server-setup.sh root@<SERVER_IP>:/root/
ssh root@<SERVER_IP> "bash /root/server-setup.sh"

# 4. Deploy:
scp ops/first-deploy.sh deploy@<SERVER_IP>:~/
ssh deploy@<SERVER_IP>
REPO_URL=<REPO_URL> \
DOMAIN=<DOMAIN> \
LETSENCRYPT_EMAIL=<LE_EMAIL> \
ANTHROPIC_API_KEY=<ANTHROPIC_API_KEY> \
bash ~/first-deploy.sh

# 5. Smoke (sen):
curl https://<DOMAIN>/api/health
# register/login/me/trial testleri (adım 15-16)

# 6. Manuel pipeline test (adım 17)

# 7. T+24h scheduler aç (adım 19)
```

Sorun çıkarsa sırayla:
- adım 14 healthcheck → hangi servis down?
- adım 22 logs → hata mesajı ne?
- adım 23 rollback → kararsız kalmadan dön

Senior tavsiye: **launch günü kahveni doldur, 4 saat boyunca bilgisayarın başında ol, sonra 24 saat passive monitoring'e geç**. Soft launch'ın doğru tanımı bu.

İyi launch'lar.
