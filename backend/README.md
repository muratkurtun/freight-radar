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

Real production manifests (`seed/source_pool.production.json` etc.)
are excluded from the repo via `.gitignore`; only the syntactically-
valid example template is tracked.

`seed/source_pool.example.json` ships as a syntactically-valid template
with `is_active: false` placeholders only. It uses the RFC-2606
`example.com` domain, which does not return real feed data — replace
the URLs with real ones (`seed/source_pool.production.json` is a
common convention) before running without `--dry-run`.

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
