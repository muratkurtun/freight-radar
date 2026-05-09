# Production Source Pool Strategy (Phase 12)

> **Audience:** Platform admin and product owner — the people deciding
> which sources land in the production pool.
> **Status:** strategy, not code. Minimum-change phase: no migrations,
> no backend behavior shifts, no frontend changes. Output is a doc, a
> seed template, and an operations workflow.

---

## 1. Why a strategy doc exists

The MVP detector + targeting model (Phases 4–11) is wired up, but the
production source pool is empty. Before populating it we need a
deliberate answer to: **which kinds of sources turn into actionable
logistics-sales leads, and which kinds drown the LLM in noise?**

This document is that answer for the first 10–20 sources. It is not a
list of URLs — Phase 11 was explicit that real production URLs come
from the platform owner's vetting, never from scratch.

### Product framing recap

The system surfaces companies that are *likely to need a freight
forwarder*, not companies that *are* freight forwarders. So the right
sources are ones that report on:

| The buyer side (what we want)            | The supplier side (what we DO NOT want) |
|------------------------------------------|------------------------------------------|
| Importers, exporters, manufacturers      | 3PL company press releases               |
| Distributors, retailers, e-commerce      | Carrier rate announcements               |
| New factory / warehouse openings         | Logistics-vendor branding content        |
| Capacity increases, tender wins          | Logistics-trade-show listicles           |
| Hiring of logistics / export staff       | Logistics-news editorial commentary      |

A logistics company announcing "we just won the Acme account" is
NOT a lead source. **Acme** announcing the same deal IS.

---

## 2. Source category matrix

Eight production categories cover the first wave. Each category lines
up with one or more `signal_focuses` from the tenant taxonomy and one
or more `customer_type_tags`. The platform admin builds the pool with
**1–3 sources per category**: that gives recall without piling
duplicates of the same content into the LLM.

| Code | Category                               | source_type       | Primary signal_focus_tags                                          | Primary customer_type_tags                            | Typical priority | Typical quality / noise |
|------|----------------------------------------|-------------------|--------------------------------------------------------------------|-------------------------------------------------------|------------------|--------------------------|
| A    | Vertical trade news (EN + TR)          | `news`            | export_expansion, new_factory, capacity_increase                   | exporter, manufacturer, importer                      | 100              | 0.75–0.80 / 0.20–0.25    |
| B    | Government / chamber announcements     | `news`            | investment_incentive, new_factory, capacity_increase, tender_or_contract | manufacturer, exporter                          | 90               | 0.85 / 0.10              |
| C    | Sector-specific export news            | `news`            | export_expansion, new_market_entry, distributorship                | exporter, manufacturer                                | 100              | 0.75 / 0.25              |
| D    | E-commerce / retail expansion          | `news`            | ecommerce_growth, new_warehouse, new_market_entry                  | ecommerce, retailer, distributor                      | 105              | 0.70 / 0.30              |
| E    | Job boards (logistics / export roles)  | `job_board`       | hiring_logistics_role, hiring_export_role                          | exporter, importer, distributor, manufacturer         | 110              | 0.70 / 0.35              |
| F    | Manufacturer press / newsrooms         | `company_website` | new_factory, capacity_increase, investment_incentive               | manufacturer, exporter                                | 105              | 0.80 / 0.20              |
| G    | Tender / public contract aggregators   | `news`            | tender_or_contract, import_need, capacity_increase                 | importer, manufacturer, distributor                   | 115              | 0.75 / 0.30              |
| H    | Distributorship / dealership news      | `news`            | distributorship, new_market_entry                                  | distributor, importer, retailer                       | 110              | 0.70 / 0.30              |

`region_tags` and `sector_tags` are picked per source — see §3.

### Why these are the right eight, not more

* Each category corresponds to a distinct *kind of company-naming
  paragraph*. The LLM prompt asks the verifier to extract a company
  name, and these categories all surface text where one is present.
* Categories that conflate buyer + supplier signals (e.g.
  generic "transportation news") are excluded — they push the false-
  positive rate up and produce "logistics company X did Y" non-leads.
* We deliberately leave out paywalled / login-walled feeds in the
  first wave: the collectors are unauthenticated.

---

## 3. Tag standard

Tags MUST be drawn from the taxonomies the tenant picks from, so a
platform-side tag and a tenant-side selection collide cleanly in the
matching SQL (`region_tags && :regions` etc., see Phase 4 commit
a9d0a3a). Out-of-vocab tags silently match nothing.

Reference (mirror of `frontend/src/app/core/models/preferences.model.ts`
and `backend/app/domain/enums.py SignalType`):

| Dimension              | Allowed values |
|------------------------|----------------|
| `region_tags`          | `turkey`, `eu`, `germany`, `uk`, `middle_east`, `global` |
| `sector_tags`          | `textile`, `automotive`, `machinery`, `food`, `chemical`, `furniture`, `electronics`, `medical`, `retail`, `industrial` |
| `customer_type_tags`   | `importer`, `exporter`, `manufacturer`, `distributor`, `retailer`, `ecommerce`, `wholesaler` |
| `signal_focus_tags`    | `export_expansion`, `import_need`, `new_factory`, `new_warehouse`, `capacity_increase`, `new_market_entry`, `distributorship`, `ecommerce_growth`, `hiring_logistics_role`, `hiring_export_role`, `investment_incentive`, `supply_chain_problem`, `tender_or_contract` |

**Tagging rules:**

1. Pick the *broadest credible* tag set: matching is intersection-
   based (the tenant's selection ∩ the source's tags ≠ ∅). A source
   tagged `["industrial"]` only matches a tenant whose sectors include
   `industrial`. A source tagged `["industrial","machinery"]` matches
   any tenant who picked at least one of the two.
2. Do not tag a source for sectors or regions it almost never covers.
   Recall is good, but tagging an EU machinery feed with `["medical"]`
   guarantees the matched tenant gets noise.
3. `language` is for analytics only — collectors don't read it. Set it
   honestly so future cost / quality reporting can split TR vs EN.
4. `priority` orders the per-tenant matched-source loop (lower first).
   Use it to push high-quality / low-noise sources earlier so the
   per-run cap (`MAX_ITEMS_PER_SOURCE_RUN`) is spent on the best
   sources first.

---

## 4. Quality and noise scoring

`quality_score` and `noise_level` are operator hints, both
`Numeric(3,2)` in the DB (range 0.00–1.00). The pipeline does not yet
read them — they exist for analytics and for human triage in the
Source Pool admin UI.

Scoring rubric we use when seeding:

| Signal                                                             | quality_score | noise_level |
|--------------------------------------------------------------------|---------------|-------------|
| Government registry / official chamber announcement                | 0.85–0.95     | 0.05–0.15   |
| Established trade publication, lead-sentence company names common  | 0.75–0.85     | 0.15–0.25   |
| Aggregator that mixes business news with marketing copy            | 0.55–0.70     | 0.30–0.45   |
| Job board listing pages                                            | 0.65–0.75     | 0.30–0.40   |
| Personal blogs, opinion-heavy outlets                              | DO NOT SEED.  Skip.       |

Anything where `quality_score - noise_level < 0.40` is a candidate
for human review — surface it on Source Pool with `is_active=false`
until proven.

---

## 5. Validation checklist (per source, before `is_active=true`)

A source MUST pass every check below before flipping `is_active` to
`true`. The platform admin runs this manually during initial seeding
and again whenever a source is renewed.

```
[ ] URL reachable: HTTP 200 from the deploy server (curl -I)
[ ] If source_type=news: feed parses (feedparser returns ≥1 entry)
[ ] If source_type=job_board: listing-page selectors return ≥1 row
    when the company_website / job_board collector renders the page
[ ] If source_type=company_website: same — listing selectors yield
    ≥1 entry
[ ] At least one of the last ~10 published items names a company
    (not just a sector or "the industry")
[ ] Articles plausibly trigger one of the source's signal_focus_tags
    (read 3 random items, ≥1 matches)
[ ] Tagging is correct: every region / sector / customer_type /
    signal_focus on the row genuinely describes the publication
[ ] No paywall / login wall / aggressive bot detection on the listing
    page (collectors run unauthenticated)
[ ] Language tag honest (TR / EN / DE / etc.)
[ ] Estimated quality_score / noise_level entered honestly per §4
[ ] Source category code (A1, B1, C1, …) noted in `_comment_category`
    so the next operator knows why this row exists
[ ] Dry-run passes:
      python scripts/seed_source_pool.py \
        --file seed/source_pool.production.json --dry-run
[ ] Pipeline run for a test tenant returns at least one signal
    within 24 hours
```

---

## 6. First-wave rollout (10–20 sources)

Phase the rollout instead of seeding everything at once. Each phase
ends with **24h observation** before the next batch.

| Phase | Categories | Source count | Goal |
|-------|------------|--------------|------|
| 0 — dry-run only | A, B, C, F | 4–6 | Confirm collectors don't break, the LLM produces well-formed JSON, the matching SQL returns expected sources for the test tenant. is_active=false, full pipeline run is a no-op. |
| 1 — soft active   | A, B, C, F | 4–6 | Flip is_active=true. Watch llm_calls / source / day; expect 5–20 calls, watch the OpenAI Console hard limit. |
| 2 — expand        | + D, G     | +4   | Add e-commerce + tender categories. Quality bar same as Phase 1. |
| 3 — hiring + dist | + E, H     | +4   | Add job boards + distributorship news. These have higher noise — watch the false-positive rate in Reviews. |
| 4 — saturate      | revisit    | up to 20 | Add 1–2 more sources per high-performing category; cull underperformers (signals/day < 1 over 2 weeks). |

Total target: 16–20 active platform sources, distributed roughly
A:3 / B:2 / C:3 / D:2 / E:2 / F:2 / G:2 / H:2.

### Anti-patterns (do not seed)

* Pure logistics-vendor newsrooms (Maersk press, DHL blog, etc.) —
  they advertise *the supplier*, not the buyer.
* "Top 10 logistics trends" listicles — no company names.
* Twitter / X firehoses — too noisy, the gate keyword will hit but
  the verifier will is_signal=false on most.
* Conference / event press pages — episodic, low recall.
* Search-engine-result aggregators — content is duplicated across
  pages and inflates `MAX_ITEMS_PER_SOURCE_RUN`.

---

## 7. Operations cadence

| Cadence    | Action                                                              |
|------------|---------------------------------------------------------------------|
| Per source onboard | §5 checklist; commit the resulting JSON to a private repo or a sealed file outside the public OpenAI/git history. |
| Daily, week 1     | Watch backend log for `Detection finished … llm_calls=N gate_skips=N signals=N failures=N` per source — same line surfaces from Phase 4. |
| Weekly, week 1+   | Review false-positive rate per source via the existing `/feedback/stats/by-source` analytics endpoint. Sources whose `not_relevant + dismissed` rate exceeds 60% over 100 leads are candidates for is_active=false. |
| Monthly           | Re-run the §5 checklist on every active source — sites change, feeds break, selectors rot. |
| Ad-hoc            | When a tenant complains about lead noise, look at signal_feedback grouped by `signal_focus_tags` ∩ source.signal_focus_tags to find the offending source. |

---

## 8. Files this phase touches

* `docs/phase_12_production_source_pool_strategy.md` — this doc
* `backend/seed/source_pool.production.template.json` — eight
  category-aligned scaffolds; `is_active: false`, every URL is a
  literal `REPLACE_WITH_REAL_URL`. Production manifest
  (`source_pool.production.json`) is gitignored.
* `backend/README.md` — adds the operations workflow that points
  at this strategy doc.
* `.gitignore` — allow-list extended for the renamed template.

No backend or frontend code changes. No migration. The pool stays
empty until the platform admin runs the seed script with a real
manifest derived from this template.
