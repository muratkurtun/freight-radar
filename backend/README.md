# Opportunity Radar — Backend

Logistics / Freight Radar backend. Python + FastAPI + PostgreSQL + APScheduler + JWT.

## Setup

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
```

Edit `.env` and set `DATABASE_URL`, `JWT_SECRET`, `OPENAI_API_KEY`.

## Database

```bash
alembic upgrade head
python -m scripts.seed_tenant
```

## Run

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## Manual pipeline run

```bash
python -m scripts.run_pipeline_once --source-id <uuid>
```

## Creating a platform admin

`/auth/register` only ever creates `tenant_admin` users — the request
schema has no `role` field and `RegistrationService.register` hardcodes
the role. PLATFORM_ADMIN can therefore only be minted by an operator
with shell access, via the bootstrap script:

```bash
# Inside the backend container (PYTHONPATH=/app):
cd /app
python scripts/create_platform_admin.py \
    --email admin@opportunityradar.com \
    --password '<long-random-string>' \
    --full-name 'Platform Admin'
```

`User.tenant_id` is NOT NULL, so the script gets-or-creates a "platform
tenant" (default slug `platform`, name `Opportunity Radar Platform`).
Override with `--tenant-slug` / `--tenant-name`.

Re-run safety:

| Scenario | Default | `--update-existing` |
|----------|---------|---------------------|
| Email is new                              | create | create              |
| Email exists in the platform tenant       | rc=2   | promote + reset password |
| Email exists in a *different* tenant      | rc=2   | rc=2 (refuses to silently move) |

Output: `created user email=… role=platform_admin tenant=platform …`.
The plain password is never logged.

After creating the admin, log in once via `/auth/login`, hit
`/source-pool` (or `GET /platform/sources` directly with the bearer
token) and confirm a 200. A `tenant_admin` token must keep getting 403
on the same path — that's the contract.

## Seeding the platform source pool

The source pool is curated centrally — **tenants do not manage source
URLs**. Platform admins seed and update the pool from a JSON manifest:

```bash
# Inside the backend container, with PYTHONPATH=/app:
cd /app
python scripts/seed_source_pool.py --file seed/source_pool.example.json --dry-run
```

> Compose compatibility: examples below use `docker compose` (Compose
> v2). On hosts still running Compose v1 the equivalent invocation is
> `docker-compose` — every other argument is identical.

Real production manifests (`seed/source_pool.production.json`) are
excluded from the repo via `.gitignore`. Two example templates are
tracked:

- `seed/source_pool.example.json` — minimal scaffold with
  `example.com` URLs, used in the dry-run smoke test.
- `seed/source_pool.production.example.json` — production-shaped
  template with realistic tag combinations and `is_active: false`
  placeholders. Copy this to `seed/source_pool.production.json`,
  replace the `REPLACE-with-real-…` URLs with vetted feeds, and
  flip `is_active` to `true` per record after the platform admin
  reviews each one. Source pool is **never** managed by tenant users.

Each record supports: `name`, `source_type` (one of `news`,
`job_board`, `company_website`), `url`, `is_active`, the four tag
arrays (`region_tags`, `sector_tags`, `customer_type_tags`,
`signal_focus_tags`), `language`, `priority`, `quality_score` and
`noise_level` (both `Numeric(3,2)` so 0.00–1.00 — divide a 0–100
score by 100 before seeding), and `config` (collector-specific dict).
Validation is fail-fast unless `--skip-invalid` is passed.

Idempotency: the match key is the URL normalized to lowercase with
the trailing slash stripped. Running the same file twice is safe.

```bash
# Production roll-out (no dry-run, refresh existing rows in place):
PYTHONPATH=/app python scripts/seed_source_pool.py \
    --file seed/source_pool.production.json --update-existing
```

Output line: `created=N updated=N skipped=N invalid=N`.

Future source-quality analytics (signal_count / qualified / converted
/ not-relevant rate / auto noise update) will read from
`signal_feedback` + `detected_signals`. This script does not write
those metrics — only the static `quality_score`, `noise_level`,
`priority` columns the platform admin curates by hand.

## Layout

- `app/api` — FastAPI routers (transport only)
- `app/services` — business logic / orchestration
- `app/repositories` — tenant-aware DB access
- `app/domain` — ORM models, schemas, enums
- `app/collectors` — one crawler per source type (`news`, `job_board`, `company_website`)
- `app/detectors` — AI classification + extraction
- `app/scheduler` — APScheduler jobs
- `app/security` — JWT, passwords, tenant context
- `app/db`, `app/core`, `app/config.py` — infrastructure
