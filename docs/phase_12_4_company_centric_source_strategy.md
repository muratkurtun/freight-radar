# Phase 12.4 — Company-Centric Source Strategy

> **Status:** decision document, no code in this phase. The next code
> phase (12.5+) will implement whatever is approved here.
> **Audience:** platform admin and product owner choosing the second
> wave of sources after the chamber/union RSS approach failed in
> Phase 12.3.

---

## 1. What Phase 12.3 told us (empirical)

Active source: `TOBB - Duyurular RSS`. One full pipeline tick with a
test tenant whose targeting matched the source's tags:

| Metric           | Value |
|------------------|-------|
| matched_sources  | 1     |
| collected        | 25    |
| llm_calls        | 8     |
| signals          | **0** |
| failures         | 0     |
| item_errors      | 0     |

The pipeline is healthy end-to-end. Eight items passed the broad
keyword gate. The verifier returned `is_signal=false` on every one,
or returned a signal with `company_name=null` which the deterministic
guard in `signal_detector._normalize` then dropped.

Manual review of TOBB / İSO Duyurular / EkoTürk KOBİ feeds confirms
the same shape across all three:

- TOBB feeds — fee schedules, customs procedures, member-card
  updates, regulatory announcements
- İSO Duyurular — training, SKDM, support programmes, regulation
- EkoTürk KOBİ — finance, credit lines, education, sector overviews

These are **legitimate publications** for their audience. They are
not lead sources because they don't name a specific company doing
something operational — and that's exactly the field the
`company_name` guard in our pipeline blocks on.

**RSS-only as a TR strategy is not enough.** The TR business press
that does name companies in lead-shaped sentences mostly ships HTML
listing pages, not RSS. We knew this in Phase 12.2 (Dünya / Sanayi
Gazetesi / Makine Birlik all rejected as HTML-only). Phase 12.3
exhausted the easily-available RSS options. Time to expand the
collector surface.

---

## 2. Six decisions

### Q1. HTML listing collector gerekli mi?

**Yes. Reuse the existing surface, don't rebuild.**

`backend/app/collectors/company_website_collector.py` already does
HTML listing parsing with CSS-selector config (per its docstring:
*"Source.url is the listing page (/news, /press, /blog, ...);
Source.config keys: ..."*). The collector itself is generic — it
fetches a listing page, applies a configured selector, and emits
SourceItems.

What's missing is **semantic separation in the schema**: a
`news_html` source_type so analytics / UI / future per-type tuning
can distinguish a publication's listing page from a single-company
newsroom. Without that distinction, `/feedback/stats/by-source`
already exists, but `stats by source_type` mixes them.

**Recommendation for Phase 12.5 (code):**

1. Add `news_html` to the `SourceType` enum (new value, no schema
   migration on the table because `signal_type` and `source_type`
   are stored as strings; `enums.py` is the write-time authority).
2. Register an HTML listing collector in `collectors/registry.py`
   for `news_html`. Implementation can be a thin wrapper that
   reuses `company_website_collector` internally with its existing
   selector config.
3. `seed_source_pool.py` validator already routes via the
   `_VALID_SOURCE_TYPES` frozenset — adding `news_html` to the enum
   is the only change required there.
4. Frontend Source Pool admin UI already renders any value in the
   `source_type` column as a label; no UI work needed for the type
   to appear, but the chip color palette could grow a fourth shade
   in a follow-up polish.

**Out of scope for 12.4:** writing the collector. Decision-only doc.

### Q2. Company newsroom kaynakları nasıl modellenmeli?

**Keep `source_type=company_website` as-is. Tier the rows when
seeding so the operator focuses on high-cadence press pages first.**

Each company newsroom is one row. Tagging implications:

- `customer_type_tags` is the company's role in the supply chain
  (a Tier-1 manufacturer newsroom → `["manufacturer"]`, not the
  union of every type they might address)
- `sector_tags` is what the company actually makes (Arçelik →
  `["electronics"]`, not `["electronics", "industrial", "retail"]`
  even if their products span those segments)
- `region_tags` is where the company operates from (a TR-HQ
  manufacturer →`["turkey"]`; if they have meaningful EU operations
  reflected in their press, then `["turkey", "eu"]`)

Tier the candidate list by press cadence and company-name explicit-
ness:

| Tier | Description | Examples (kind, not URLs) |
|------|-------------|----------------------------|
| 1    | Listed companies with dedicated press / investor news pages, monthly+ cadence | Public industrial groups (Koç, Sabancı, Eczacıbaşı, Anadolu Grubu, Borusan) |
| 2    | Listed sector leaders with quarterly+ cadence | Arçelik, Vestel, Ford Otosan, Tofaş, Tüpraş, Petkim, Erdemir, Oyak |
| 3    | Mid-cap industrials with active press but irregular cadence | Sector-specific exporters / manufacturers (~50–100 candidates) |

Risks specific to this category:

- **Selector rot.** Each row has a hand-tuned CSS selector. Site
  redesigns silently break the row. Mitigation: monthly re-
  validation per the Phase 12 strategy doc §7 cadence.
- **Self-promotional content.** Tier-1 / Tier-2 companies sometimes
  publish CSR / sponsorship / award press that doesn't translate
  to lead signal. The verifier handles this (no operational hook →
  `is_signal=false`), but it inflates `llm_calls` per source.
  Acceptable cost for Tier 1 / 2; Tier 3 needs review before active.

**No schema change. No new code. Just selection discipline at seed
time.**

### Q3. Sector publication sayfaları nasıl parse edilmeli?

**Hybrid: feed-discovery first, HTML listing second.**

For each sector publication candidate:

1. **Feed-discovery (5 minutes per site, no code).** Try in order:
   - Inspect page source for
     `<link rel="alternate" type="application/rss+xml">`
   - Try common paths: `/feed`, `/feed/`, `/rss`, `/rss.xml`,
     `/atom.xml`, `/feeds/posts/default` (Blogger), `/index.rss`
   - For WordPress sites: `/feed/` is almost always there
   - For Drupal sites: `/rss.xml` or category-specific `/category/X/rss`
   - If a category-specific feed exists (e.g.
     `/kategori/ihracat/feed`), that's strictly better than the
     site-wide feed because tagging stays precise

2. **If no RSS exists → HTML listing path** (depends on Q1
   delivering the `news_html` collector type).

3. **Reject** if:
   - The site requires JavaScript to render the listing
   - There's a paywall / login wall
   - The site has aggressive bot detection (Cloudflare challenge,
     etc.)
   - The publication is opinion-heavy with low company-naming
     density (the `<3 company names per 10 items` test from Q5
     applies here too)

This sequencing is intentional: Phase 12.2 had three HTML-only
sector pub candidates (Sanayi Gazetesi, Dünya Gazetesi/ihracat,
Makine Birlik). All three may have undiscovered RSS feeds — operator
should check before requesting the HTML collector.

### Q4. İş ilanı kaynakları lead sinyali olarak nasıl ele alınmalı?

**Yes, treat them as Tier-1 leads. But pick boards where the
employer name is on the listing card, not behind a click.**

Lead semantics:

- A company posting "Export Manager" / "İhracat Müdürü" /
  "Logistics Coordinator" / "Lojistik Sorumlusu" is staffing for
  international operations.
- Hiring an export role is a public commitment to grow an
  international book — the strongest forward-looking lead signal we
  can get without an investment-incentive announcement.

Constraints:

- The existing `job_board` collector has CSS-selector config and
  iterates listing rows. Each row's company is the EMPLOYER, not
  "the job board". The collector must extract:
  - Employer name (the lead's `company_name`)
  - Role title
  - Posting date
  - Detail URL
- Recruitment-agency reposts hide the employer ("our client, a
  leading exporter...") — useless without the company name.
  Reject these boards or filter them at the row level.
- Anti-bot / login walls (LinkedIn, etc.) — reject; the collector
  is unauthenticated.

Candidate types (no URLs):

- TR-specific job boards with explicit employer names
- Niche logistics/export job boards (sector-specific recruitment
  sites)
- Company career pages (modeled as `company_website`, not
  `job_board`, when scraping the careers listing — selector
  flexibility lets either approach work, but `job_board` semantics
  are clearer for aggregator sites)

Activate strategy: **2 boards in the first wave**, monitor
`signals/llm_calls` ratio for 7 days before adding a third. The
Phase 12 strategy doc's job-board noise estimate (0.30–0.40) is
optimistic for any board where employer obfuscation is common.

### Q5. RSS kaynaklar hangi kriterle kalmalı, hangileri elenmeli?

**Acceptance test: open the last 10 items in a feed; count how many
name a specific company taking an operational action. <3 → reject.**

"Operational action" means:

- Opening / expanding a facility
- Entering a new market or country
- Signing a distributor / customer / supply deal
- Hiring for a named role
- Receiving an investment incentive certificate (with the company
  named in the press)
- Publishing capacity / production / export figures with company
  attribution

NOT operational actions:

- Sector-level commentary ("textile exports rose 12%")
- Regulatory announcements (TOBB Duyurular, customs procedure
  updates, fee schedules)
- Education / training programmes (chamber webinars)
- Macro-economic analysis
- Award ceremonies without an operational subtext

Apply the test to every active feed every 30 days. The
`/feedback/stats/by-source` endpoint already gives `not_relevant +
dismissed` rates per source — when a source's negative-feedback
rate exceeds 60% over its first 100 items, it's a confirmation
signal that the manual 10-item test would also fail.

**Action items for the current pool:**

| Source                     | Phase 12.3 status | 12.4 decision |
|----------------------------|-------------------|----------------|
| TOBB - Duyurular RSS       | active, signals=0 over 25 collected | Deactivate. Macro content, won't pass the 3-of-10 test. |
| TOBB - Haberleri RSS       | seeded, inactive  | Deactivate before it goes live. Same publisher pattern. |
| TOBB - Manşet Haberleri    | seeded, inactive  | Same — drop. |
| İSO - Haberler RSS         | seeded, inactive  | Hold. Apply 3-of-10 test before activating; if borderline, keep inactive. |
| İSO - Duyurular RSS        | seeded, inactive  | Drop — Phase 12.3 manual review confirmed macro content. |
| Sanayi Gazetesi (HTML)     | rejected          | Reconsider in Phase 12.5+ once HTML collector lands. |
| Dünya Gazetesi (HTML)      | rejected          | Same. |
| Makine Birlik (HTML)       | rejected          | Same. |
| EkoTürk KOBİ RSS           | seeded, inactive  | Drop. Finance/credit content. |
| Food Sektör RSS            | seeded, inactive  | Apply 3-of-10 test. Sector pubs vary widely; this one is the only sector-specific feed in the pool, worth one validation pass. |

### Q6. İlk 10 company-centric source candidate tipi ne olmalı?

Listed by category and tier. URLs are the operator's job in 12.6.

| # | Type                                             | Tier | source_type      | Wave |
|---|--------------------------------------------------|------|------------------|------|
| 1 | **Investment incentive registries** (Sanayi ve Teknoloji Bakanlığı yatırım teşvik belgesi list / weekly bulletin) | T1   | news / news_html | 1    |
| 2 | **Foreign-investment / expansion announcements** (Cumhurbaşkanlığı Yatırım Ofisi haberleri) | T1   | news / news_html | 1    |
| 3 | **KAP (Borsa İstanbul Public Disclosure Platform) industrial company filings** | T1   | news / news_html | 1    |
| 4 | **Tier-1 manufacturer newsrooms** — pick 3: Arçelik, Tüpraş, Ford Otosan (one electronics, one chemical, one automotive) | T1   | company_website  | 1    |
| 5 | **Sector publication with confirmed RSS or HTML access** — Dünya Gazetesi /ihracat (try `/ihracat/feed`, `/feed/?cat=...` first) | T2   | news / news_html | 2    |
| 6 | **Sector union spotlight feeds** — TİM member-company news, OAİB / İHKİB / İMMİB if any expose company-named press | T2   | news / news_html | 2    |
| 7 | **TR-specific job board** — explicit employer column, pick one (logistics + export role keywords) | T2   | job_board        | 2    |
| 8 | **Tier-2 manufacturer newsrooms** — pick 2: Vestel + a Tier-2 textile/food exporter | T2   | company_website  | 2    |
| 9 | **Trade fair exhibitor news** — Hannover Messe / CeBIT-equivalent press feeds covering TR exhibitors | T3   | news / news_html | 3    |
| 10| **Second job board** — sector-niche if Wave-2 board underperforms | T3   | job_board        | 3    |

Wave 1 (T1): expected to deliver the first signals because they're
either government-published (1, 2) or regulatory disclosure
(3) — both formats have company names mandated by the publisher's
own format. Tier-1 manufacturer newsrooms (4) round out the
distribution by company size.

Wave 2 (T2): adds operator-curated breadth across sectors and roles.

Wave 3 (T3): only after Wave 1 + 2 produce a signal flow we can
measure. Don't seed all 10 at once.

---

## 3. Phasing

| Phase  | Work                                                              |
|--------|-------------------------------------------------------------------|
| 12.4   | This decision doc (no code).                                      |
| 12.5   | Code: add `news_html` to SourceType enum, register HTML listing collector, extend seed_source_pool validator. Tests. |
| 12.6   | Operator curation: pick URLs for the 10 types in Q6 Wave 1 (3–4 candidates), validate via the existing validator script (RSS-or-HTML), confirm 3-of-10 acceptance test. Update production manifest, deactivate the Phase 12.3 sources per Q5. |
| 12.7   | Activate Wave 1 (3–4 sources), 24h soak, observe `signals` per source, then iterate Q6 Wave 2. |
| 12.8+  | Source-quality analytics automation (auto-deactivate sources whose negative-feedback rate exceeds 60% over 100 items). Already on the roadmap from Phase 9. |

The 12.5 code work has a contained blast radius:

- One enum value added (additive, no migration)
- One collector registered (additive, no migration)
- One validator value-set extended (additive, no schema change)
- Frontend renders the new label automatically

No frontend redesign. No backend behavior change for existing flows.

---

## 4. What NOT to do

- **Don't seed more chamber / union announcement feeds.** Phase
  12.3 produced 0 signals from 25 collected items across three
  such sources. The pattern is empirical, not anecdotal.
- **Don't seed SME finance / credit / training publications.**
  Same reason — content shape doesn't carry company-action
  semantics.
- **Don't try LinkedIn / paywalled / anti-bot sites.** The
  collectors are unauthenticated. Failed scrapes inflate
  `failures` counts and burn operator review time.
- **Don't widen the broad keyword gate** to compensate for source
  quality. The gate is doing its job (32% pass rate on TOBB —
  recall-first by design). The bottleneck is upstream of the
  gate: the source is publishing the wrong shape of content.
- **Don't activate all 10 candidates from Q6 at once.** Wave 1
  first (3–4 sources), measure, then expand. Phase 12 strategy
  doc §6 already mandates this; it's worth restating after the
  12.3 finding.

---

## 5. Open questions for the next phase

1. **HTML collector scope.** Does the new `news_html` type need
   pagination support (follow "next page" link N times) or is
   one listing page sufficient? Most sites' first page covers ≥10
   recent items, which is enough for the matching loop. Pagination
   = nice-to-have, deferred.
2. **Selector library.** Each `company_website` and `news_html`
   row needs a hand-tuned selector. A small library of common
   patterns (article cards, headline links, pagination) would speed
   up onboarding. Out of 12.4 scope; revisit if 12.6 onboarding is
   slow.
3. **Investment incentive registry format.** The Bakanlık
   typically publishes weekly Excel / PDF summaries. If those
   aren't available as RSS or scrapable HTML, this candidate moves
   to a separate ingestion path (file-import collector). Open until
   operator confirms format.
4. **KAP feed.** Borsa İstanbul publishes structured filings —
   format may justify a dedicated collector rather than HTML
   parsing. Defer until operator confirms availability.

---

## 6. Files this phase touches

- `docs/phase_12_4_company_centric_source_strategy.md` — this doc.

**Not touched:** backend / frontend code, migrations, manifests,
README. Phase 12.5 will commit code; Phase 12.6 will commit
documentation updates.
