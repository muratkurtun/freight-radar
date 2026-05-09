# First Production Source Pool — Curation Worksheet (Phase 12.1)

> **Audience:** the platform admin sitting down to fill the production
> source pool for the first time.
> **Status:** operator-driven worksheet — methodology, checklist, and
> a candidate-row template. The actual URLs, validation results, and
> accept / reject decisions are filled in by the operator during the
> seeding session, **not** by the AI assistant.

---

## 1. Why this isn't a list of URLs

The Phase 12 strategy doc (categories A–H, tag standard, anti-patterns)
gave us the rules. This worksheet is the gate every candidate URL has
to pass before it lands in the production pool.

Two reasons the URLs are operator-supplied, not AI-generated:

1. **Real validation needs real fetches.** A URL that was a healthy RSS
   feed last quarter may be a 410 today. Only a live `curl` answers
   that, and the assistant building this worksheet has no outbound HTTP.
2. **The platform owner accepts liability for what the pipeline scrapes.**
   The operator knows the publications, knows which paywalls appeared
   in the last six months, and knows which sites their lawyer has
   already cleared.

The validator script automates the boring half (HTTP reachability,
feed parseability, entry count). The judgement half — "does this feed
actually name companies in lead-shaped sentences?" — stays with you.

---

## 2. First-wave scope

| Dimension      | Values for the first wave |
|----------------|----------------------------|
| Region         | `turkey`, `eu` (with `germany` / `uk` / `global` allowed where it lines up with category D / F) |
| Customer type  | `exporter`, `manufacturer`, `importer`, `distributor` |
| Sector         | `textile`, `automotive`, `machinery`, `food`, `chemical`, `industrial`, `retail` |
| Signal focus   | `export_expansion`, `new_market_entry`, `capacity_increase`, `new_factory`, `new_warehouse`, `hiring_export_role`, `hiring_logistics_role`, `investment_incentive` |

The other taxonomies (`ecommerce_growth`, `tender_or_contract`,
`supply_chain_problem`, …) intentionally sit out of wave 1 — pick
them up in a follow-up after the first 4–6 sources prove out.

Target source count: **16 candidates → 12–14 acceptances → 4–5
active for the first soft-launch run** (Phase 0/1 in the strategy doc).

---

## 3. Category distribution

| Code | Category                              | Wave-1 candidate count |
|------|---------------------------------------|------------------------|
| A    | Vertical trade / industry news        | 3 (1 EN, 1 TR, 1 sector-broad) |
| B    | Government / chamber / industry orgs  | 2 |
| C    | Sector-specific export news           | 3 (1 textile, 1 machinery, 1 food) |
| D    | E-commerce / retail expansion         | 0 in wave 1 (deferred)  |
| E    | Job boards (logistics / export)       | 2 (1 TR, 1 EU/EN) |
| F    | Manufacturer press / newsrooms        | 3 (machinery / automotive / textile pick) |
| G    | Tender / public contract              | 0 in wave 1 (deferred) |
| H    | Distributorship / dealership          | 3 (TR-EU corridor focus) |

= **16 candidates**. D and G stay out of wave 1; the strategy doc
schedules them for later phases.

---

## 4. Candidate row template (operator working file)

Copy the JSON block below into a working file the operator owns —
**not** committed to the repo:

```bash
cp /dev/stdin backend/seed/candidates.working.json << 'JSON_EOF'
... paste from the block below, then fill in URLs ...
JSON_EOF
```

`backend/seed/candidates.working.json` is gitignored by the existing
`backend/seed/*` rule, so it stays local. Replace every
`REPLACE_WITH_REAL_URL` with a vetted URL before running the
validator. If a candidate is rejected outright, delete the row;
don't ship a placeholder into validation.

```json
[
  {
    "name": "REPLACE: TR vertical trade news (EN section)",
    "source_type": "news",
    "url": "REPLACE_WITH_REAL_URL",
    "category_code": "A1",
    "expected_signal_focus": ["export_expansion", "new_factory", "capacity_increase"],
    "expected_customer_type": ["exporter", "manufacturer", "importer"],
    "expected_sector": ["industrial", "machinery", "textile"],
    "expected_region": ["turkey"],
    "language": "en",
    "validation_status": "pending",
    "validation_notes": "EN-language section of a TR business publication. Confirm at least 5 of the last 10 items name a Turkish exporter or manufacturer.",
    "decision": "needs operator validation"
  },
  {
    "name": "REPLACE: TR vertical trade news (TR section)",
    "source_type": "news",
    "url": "REPLACE_WITH_REAL_URL",
    "category_code": "A2",
    "expected_signal_focus": ["export_expansion", "investment_incentive", "new_factory", "new_market_entry"],
    "expected_customer_type": ["exporter", "manufacturer", "importer"],
    "expected_sector": ["textile", "machinery", "food", "industrial"],
    "expected_region": ["turkey"],
    "language": "tr",
    "validation_status": "pending",
    "validation_notes": "Pair with A1 — TR-language version catches local coverage that doesn't get an English release.",
    "decision": "needs operator validation"
  },
  {
    "name": "REPLACE: EU vertical industrial news",
    "source_type": "news",
    "url": "REPLACE_WITH_REAL_URL",
    "category_code": "A3",
    "expected_signal_focus": ["export_expansion", "new_factory", "capacity_increase", "new_market_entry"],
    "expected_customer_type": ["exporter", "manufacturer"],
    "expected_sector": ["industrial", "machinery", "automotive", "chemical"],
    "expected_region": ["eu", "germany"],
    "language": "en",
    "validation_status": "pending",
    "validation_notes": "Pan-EU industrial publication. Reject if the last 10 items are dominated by analyst-style commentary without company names.",
    "decision": "needs operator validation"
  },
  {
    "name": "REPLACE: TR investment incentive announcements",
    "source_type": "news",
    "url": "REPLACE_WITH_REAL_URL",
    "category_code": "B1",
    "expected_signal_focus": ["investment_incentive", "new_factory", "capacity_increase"],
    "expected_customer_type": ["manufacturer", "exporter"],
    "expected_sector": ["industrial", "machinery", "automotive", "chemical"],
    "expected_region": ["turkey"],
    "language": "tr",
    "validation_status": "pending",
    "validation_notes": "Government / chamber feed. Quality typically high (named companies, capacity figures), cadence slow.",
    "decision": "needs operator validation"
  },
  {
    "name": "REPLACE: TR exporters' association announcements",
    "source_type": "news",
    "url": "REPLACE_WITH_REAL_URL",
    "category_code": "B2",
    "expected_signal_focus": ["export_expansion", "new_market_entry", "tender_or_contract"],
    "expected_customer_type": ["exporter", "manufacturer"],
    "expected_sector": ["textile", "machinery", "food", "chemical"],
    "expected_region": ["turkey"],
    "language": "tr",
    "validation_status": "pending",
    "validation_notes": "Sector-spanning exporters' union news room. Watch for award-style press releases that don't carry a company outcome.",
    "decision": "needs operator validation"
  },
  {
    "name": "REPLACE: TR textile sector news",
    "source_type": "news",
    "url": "REPLACE_WITH_REAL_URL",
    "category_code": "C1",
    "expected_signal_focus": ["export_expansion", "new_market_entry", "distributorship"],
    "expected_customer_type": ["exporter", "manufacturer"],
    "expected_sector": ["textile"],
    "expected_region": ["turkey", "eu"],
    "language": "tr",
    "validation_status": "pending",
    "validation_notes": "Single-sector publication. Tag sector_tags=[\"textile\"] only — do not multi-tag.",
    "decision": "needs operator validation"
  },
  {
    "name": "REPLACE: EU machinery sector news",
    "source_type": "news",
    "url": "REPLACE_WITH_REAL_URL",
    "category_code": "C2",
    "expected_signal_focus": ["export_expansion", "new_factory", "capacity_increase"],
    "expected_customer_type": ["manufacturer", "exporter"],
    "expected_sector": ["machinery"],
    "expected_region": ["eu", "germany"],
    "language": "en",
    "validation_status": "pending",
    "validation_notes": "Industrial-machinery trade press. Highest expected lead density of the C-row sources.",
    "decision": "needs operator validation"
  },
  {
    "name": "REPLACE: TR/EU food sector news",
    "source_type": "news",
    "url": "REPLACE_WITH_REAL_URL",
    "category_code": "C3",
    "expected_signal_focus": ["export_expansion", "new_market_entry", "capacity_increase"],
    "expected_customer_type": ["exporter", "manufacturer", "distributor"],
    "expected_sector": ["food"],
    "expected_region": ["turkey", "eu"],
    "language": "en",
    "validation_status": "pending",
    "validation_notes": "Food sector — watch noise level on retail/foodservice marketing copy.",
    "decision": "needs operator validation"
  },
  {
    "name": "REPLACE: TR logistics / export job board",
    "source_type": "job_board",
    "url": "REPLACE_WITH_REAL_URL",
    "category_code": "E1",
    "expected_signal_focus": ["hiring_logistics_role", "hiring_export_role"],
    "expected_customer_type": ["exporter", "importer", "manufacturer", "distributor"],
    "expected_sector": ["industrial", "retail", "machinery", "textile"],
    "expected_region": ["turkey"],
    "language": "tr",
    "validation_status": "pending",
    "validation_notes": "Confirm the listing-page selectors the JOB_BOARD collector expects (see backend/app/collectors/job_board_collector.py). Without selectors the collector returns zero items.",
    "decision": "needs operator validation"
  },
  {
    "name": "REPLACE: EU logistics / export job board",
    "source_type": "job_board",
    "url": "REPLACE_WITH_REAL_URL",
    "category_code": "E2",
    "expected_signal_focus": ["hiring_logistics_role", "hiring_export_role"],
    "expected_customer_type": ["exporter", "importer", "manufacturer", "distributor"],
    "expected_sector": ["industrial", "retail", "machinery"],
    "expected_region": ["eu"],
    "language": "en",
    "validation_status": "pending",
    "validation_notes": "Same selector requirement as E1; pick a board that surfaces the company name on the listing page, not just on the detail page.",
    "decision": "needs operator validation"
  },
  {
    "name": "REPLACE: EU machinery manufacturer press / newsroom",
    "source_type": "company_website",
    "url": "REPLACE_WITH_REAL_URL",
    "category_code": "F1",
    "expected_signal_focus": ["new_factory", "capacity_increase", "investment_incentive"],
    "expected_customer_type": ["manufacturer", "exporter"],
    "expected_sector": ["machinery", "industrial"],
    "expected_region": ["eu", "germany"],
    "language": "en",
    "validation_status": "pending",
    "validation_notes": "Single-company newsroom — accept only if the listing page renders without JS. Confirm COMPANY_WEBSITE selectors.",
    "decision": "needs operator validation"
  },
  {
    "name": "REPLACE: EU automotive Tier-1 newsroom",
    "source_type": "company_website",
    "url": "REPLACE_WITH_REAL_URL",
    "category_code": "F2",
    "expected_signal_focus": ["new_factory", "capacity_increase", "new_market_entry"],
    "expected_customer_type": ["manufacturer"],
    "expected_sector": ["automotive", "industrial"],
    "expected_region": ["eu", "germany"],
    "language": "en",
    "validation_status": "pending",
    "validation_notes": "Tier-1 supplier press page; expect lower cadence but high-quality leads.",
    "decision": "needs operator validation"
  },
  {
    "name": "REPLACE: TR textile manufacturer newsroom",
    "source_type": "company_website",
    "url": "REPLACE_WITH_REAL_URL",
    "category_code": "F3",
    "expected_signal_focus": ["export_expansion", "new_market_entry", "capacity_increase"],
    "expected_customer_type": ["manufacturer", "exporter"],
    "expected_sector": ["textile"],
    "expected_region": ["turkey"],
    "language": "tr",
    "validation_status": "pending",
    "validation_notes": "Pick an established TR textile producer with regular press cadence.",
    "decision": "needs operator validation"
  },
  {
    "name": "REPLACE: TR distributorship / dealership news",
    "source_type": "news",
    "url": "REPLACE_WITH_REAL_URL",
    "category_code": "H1",
    "expected_signal_focus": ["distributorship", "new_market_entry"],
    "expected_customer_type": ["distributor", "importer"],
    "expected_sector": ["industrial", "automotive", "machinery", "retail"],
    "expected_region": ["turkey"],
    "language": "tr",
    "validation_status": "pending",
    "validation_notes": "Watch for awards / dealer-of-the-year press that doesn't actually name a new partnership.",
    "decision": "needs operator validation"
  },
  {
    "name": "REPLACE: EU distributorship news",
    "source_type": "news",
    "url": "REPLACE_WITH_REAL_URL",
    "category_code": "H2",
    "expected_signal_focus": ["distributorship", "new_market_entry"],
    "expected_customer_type": ["distributor", "importer", "retailer"],
    "expected_sector": ["industrial", "machinery", "retail"],
    "expected_region": ["eu"],
    "language": "en",
    "validation_status": "pending",
    "validation_notes": "Pan-EU distribution beat. May overlap with A3; deactivate the noisier of the two if they double-fire.",
    "decision": "needs operator validation"
  },
  {
    "name": "REPLACE: TR/EU corridor distributorship news",
    "source_type": "news",
    "url": "REPLACE_WITH_REAL_URL",
    "category_code": "H3",
    "expected_signal_focus": ["distributorship", "new_market_entry", "import_need"],
    "expected_customer_type": ["distributor", "importer"],
    "expected_sector": ["industrial", "automotive", "machinery"],
    "expected_region": ["turkey", "eu"],
    "language": "en",
    "validation_status": "pending",
    "validation_notes": "Cross-corridor publication — confirm coverage actually spans both regions and isn't EU-only with a token TR mention.",
    "decision": "needs operator validation"
  }
]
```

`category_code`, `expected_*`, `validation_status`, `validation_notes`,
and `decision` are bookkeeping fields — they live in the working file
but get dropped before the manifest is fed to `seed_source_pool.py`.
The seed script only reads the production manifest schema documented
in Phase 9.

---

## 5. Validation procedure

For each candidate row, in order:

```bash
# 1. Fill the URL in candidates.working.json. Save.
# 2. Run automated checks (HTTP + feed parse).
docker compose -f docker-compose.prod.yml exec backend bash -lc \
  "cd /app && python scripts/validate_source_candidates.py \
     --file seed/candidates.working.json --format md"
```

The validator covers:

| Step | Source of truth |
|------|-----------------|
| HTTP reachable (200 / 301 / 302) | validator |
| News feed parses, ≥1 entry         | validator |
| Body non-empty                     | validator |
| Tag accuracy (tags ↔ content)      | operator (read 5 random items) |
| Lead-sentence company names        | operator (read 10 recent items) |
| Paywall / login wall               | operator (browser visit) |
| Selector match (job_board, company_website) | operator + collector dry-run |
| Quality / noise estimate           | operator (rubric in §4 of strategy doc) |

For each candidate:

* Reachable + feed_parsed=ok + ≥3 entries  → mark `validation_status: ok`
* Reachable but no entries                 → mark `pending`, dig in
* Unreachable                              → mark `failed`, decide
* Selectors required (job_board / company_website) → mark `pending until selectors`

Then make the decision call:

* `accept` — passes every line above; ready to seed `is_active=false`
* `reject` — drop the row from candidates.working.json before the
  pre-seed step
* `manual review` — quality borderline; seed `is_active=false`,
  observe in dry-run only, decide after one full pipeline tick

---

## 6. Seeding the accepted set

After validation, build the production manifest from the accepted
rows. Strip the bookkeeping fields and keep only the seed-script
schema:

```bash
# Hand-edit (or jq) candidates.working.json into source_pool.production.json
# Drop: category_code, expected_*, validation_status, validation_notes, decision
# Keep / add: name, source_type, url, is_active, region_tags,
#             sector_tags, customer_type_tags, signal_focus_tags,
#             language, priority, quality_score, noise_level, config

# All accepted rows ship is_active=false on first seed.
# Activate selectively per §7 below.
```

Then dry-run + apply (commands documented in `backend/README.md`
"Production source pool — operations workflow"):

```bash
docker compose -f docker-compose.prod.yml exec backend bash -lc \
  "cd /app && python scripts/seed_source_pool.py \
     --file seed/source_pool.production.json --dry-run"

docker compose -f docker-compose.prod.yml exec backend bash -lc \
  "cd /app && python scripts/seed_source_pool.py \
     --file seed/source_pool.production.json --update-existing"
```

---

## 7. First-active recommendation (3–5 sources)

The strategy doc's Phase 0/1 picks categories A, B, C, F. From the
candidate list above, this means the first sources to flip
`is_active=true` after a successful seed are:

| # | Code | Why first |
|---|------|-----------|
| 1 | B1 — TR investment incentive announcements | Highest expected quality / lowest noise. Any signal it produces is high-confidence. |
| 2 | A2 — TR vertical trade news (TR section) | Broad TR coverage; primary lead source for the first tenant. |
| 3 | C2 — EU machinery sector news            | Highest expected lead density on the EU side; covers the dominant first-wave sector. |
| 4 | F1 — EU machinery manufacturer newsroom  | Single-company press — low noise, occasional high-quality factory / capacity signals. |
| 5 | A1 — TR vertical trade news (EN section) — *optional, only if A2 underperforms within 24 hours* |

E (job boards) and H (distributorship news) wait for Phase 2 — they
have higher noise and need more eyeballs on the first false-positive
batch before going live.

---

## 8. Smoke test plan

After the first active flip, watch:

```bash
# Backend log line per source (from PipelineService — see Phase 4):
docker compose -f docker-compose.prod.yml logs --tail 200 backend \
  | grep -E "Detection finished tenant=.* source="
# Each line is:
#   Detection finished tenant=… source=… items=N llm_calls=N
#   gate_skips=N signals=N failures=N
```

Expected for a single tenant whose targeting matches the four sources:

| Metric                | Healthy first-tick range |
|-----------------------|---------------------------|
| `active_sources` (run summary) | ≥ 1 (matches) |
| `collected` per source | 5–50 |
| `llm_calls` per source | 1–20 (recall-first gate; verifier short-circuits non-business items) |
| `signals` per source   | 0–5 in the first 24h is normal |
| `failures` per source  | 0; non-zero is a real bug |

Cross-checks in the platform admin UI (`/source-pool`):

* Seeded rows render with the correct tag chips per source.
* Active toggle flips status atomically.
* `tenant_admin` token loading `/source-pool` still gets a 403 —
  that's the contract.

Cross-checks in the tenant view (`/company-leads`):

* At least one company appears within 24h after the active flip.
* Targeting filters (sector / region) collapse the list as expected.
* Tenant feedback (Relevant / Not Relevant) writes to
  `/signals/{id}/feedback`.

If `signals` stays at zero after 48h on the first-active set, the
problem is upstream of the pool: the verifier is rejecting items, or
the LLM key is missing. The strategy doc §5 is the playbook —
re-validate the four sources and confirm tag overlap with the test
tenant's targeting before adding more rows.

---

## 9. Files this phase touches

* `docs/phase_12_1_first_production_source_pool_curation.md` — this doc
* `backend/scripts/validate_source_candidates.py` — automation for the
  HTTP / feed-parse half of the §5 checklist; tested
* `backend/tests/test_validate_source_candidates.py` — unit tests
* `backend/README.md` — short link to the validator command

**Not** touched / created: backend code, frontend code, migrations,
`backend/seed/source_pool.production.json` (operator deliverable).
