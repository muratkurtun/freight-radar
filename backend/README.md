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
excluded from the repo via `.gitignore`. Two scaffolds are tracked:

- `seed/source_pool.example.json` — minimal dry-run scaffold with
  `example.com` URLs, used in the seed-script unit tests.
- `seed/source_pool.production.template.json` — operations-ready
  template aligned with the eight source categories defined in
  [`docs/phase_12_production_source_pool_strategy.md`](../docs/phase_12_production_source_pool_strategy.md).
  Every record carries an `_comment_category` tag (e.g. `A1`, `B1`,
  `E1`) so the next operator can trace a row back to the strategy
  doc. URLs are literal `REPLACE_WITH_REAL_URL` placeholders;
  `is_active` is `false` on every record.

### Production source pool — operations workflow

The source pool is **never** managed by tenant users; only the
platform admin curates it. The strategy doc is the contract for what
"good" looks like — tagging rules, eight category matrix, validation
checklist, phased rollout. The first-time seeding worksheet is in
[`docs/phase_12_1_first_production_source_pool_curation.md`](../docs/phase_12_1_first_production_source_pool_curation.md):
it walks the operator through 16 candidate rows, the validation
gate, and the first-active recommendation.

The workflow below is the day-to-day use of that doc.

> Validator helper: a working candidate file lives at
> `seed/candidates.working.json` (gitignored). To run automated
> reachability + feed-parse checks against it, render a Markdown
> table for the worksheet:
>
> ```bash
> docker compose -f docker-compose.prod.yml exec backend bash -lc \
>   "cd /app && python scripts/validate_source_candidates.py \
>      --file seed/candidates.working.json --format md"
> ```
>
> JSON output is also available with `--format json` for piping into
> other tools.

```bash
# 1. Copy the template to the gitignored production manifest.
cp seed/source_pool.production.template.json \
   seed/source_pool.production.json

# 2. For each record: replace REPLACE_WITH_REAL_URL with a vetted
#    feed; tweak tags so they accurately describe the publication;
#    keep is_active=false until the row passes the §5 checklist in
#    the strategy doc.

# 3. Dry-run validates without writing — confirms the JSON is
#    parseable and each record clears the script's strict validators.
docker compose -f docker-compose.prod.yml exec backend bash -lc \
  "cd /app && python scripts/seed_source_pool.py \
     --file seed/source_pool.production.json --dry-run"

# 4. Apply with --update-existing so re-runs converge instead of
#    erroring on a URL that already landed in the pool.
docker compose -f docker-compose.prod.yml exec backend bash -lc \
  "cd /app && python scripts/seed_source_pool.py \
     --file seed/source_pool.production.json --update-existing"
# Output: created=N updated=N skipped=N invalid=N
```

After the apply:

```bash
# 5. Verify in the Source Pool admin UI as PLATFORM_ADMIN —
#    https://<DOMAIN>/source-pool. Each row should show the
#    expected tags, status badge, and quality / noise numbers.

# 6. Targeting smoke from a tenant_admin: log in, run /onboarding
#    or hit /targeting, save, click "Run pipeline now". Watch the
#    backend log for one line per matched source:
#       Detection finished tenant=… source=… items=N llm_calls=N
#       gate_skips=N signals=N failures=N
#    A non-zero llm_calls + at least one signal within 24h means
#    the pool is producing leads for that tenant.
```

If `llm_calls` is high but `signals` is zero, the source's
`signal_focus_tags` probably do not match the LLM's actual
classifications — re-read the strategy doc §5 checklist before
flipping `is_active=true` on more rows from the same category.

Each record supports: `name`, `source_type` (one of `news`,
`news_html`, `job_board`, `company_website`), `url`, `is_active`,
the four tag arrays (`region_tags`, `sector_tags`,
`customer_type_tags`, `signal_focus_tags`), `language`, `priority`,
`quality_score` and `noise_level` (both `Numeric(3,2)` so
0.00–1.00 — divide a 0–100 score by 100 before seeding), and
`config` (collector-specific dict). Validation is fail-fast unless
`--skip-invalid` is passed.

`source_type` semantics:

| value             | what to point at                                             | collector            |
|-------------------|--------------------------------------------------------------|----------------------|
| `news`            | RSS / Atom feed URL                                          | feedparser-based     |
| `news_html`       | Publication category / archive HTML page (no usable RSS)     | HTML + CSS selectors |
| `job_board`       | Listing page where each row is a job posting                 | HTML + CSS selectors |
| `company_website` | Single-company press / newsroom listing page                 | HTML + CSS selectors |

`news_html` and `company_website` share the same collector
implementation — the split is semantic, for analytics and operator
discipline. Use `news_html` for a publication's category page (e.g.
`dunya.com/ihracat`) and `company_website` for a single company's
press list (e.g. an industrial firm's `/basin-bultenleri/`).
Migration `0008_drop_sources_source_type_check` lifted the legacy
DB CHECK that pinned the column to the original three values; from
that revision onwards the SourceType enum is the write authority.

> **Downgrade caveat for migration 0008.** The downgrade re-adds the
> original CHECK on the original three values. If any post-upgrade
> row carries `news_html`, the constraint creation will fail. A real
> rollback requires deleting or re-typing those rows first.

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
