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
