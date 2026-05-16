# Tool Roadmap

## Goal

Turn SEO Suite from a strong in-house audit dashboard into a safer, more complete daily-use SEO workspace.

This roadmap is intentionally fix-first:

- critical security and runtime-consistency issues come before new fetch-heavy features
- roadmap items are tied to the real product surface already exposed in the dashboard
- every feature is grouped by delivery gate, auth model, and implementation dependency

Primary planning inputs:

- [REPO_REVIEW_AND_CLEANUP.md](D:/Coding/SEO%20Suite/REPO_REVIEW_AND_CLEANUP.md)
- [FREE_TOOLS_RESEARCH.md](D:/Coding/SEO%20Suite/FREE_TOOLS_RESEARCH.md)
- [dashboard.html](D:/Coding/SEO%20Suite/app/templates/dashboard.html:123)
- [dashboard.html](D:/Coding/SEO%20Suite/app/templates/dashboard.html:190)
- [dashboard.html](D:/Coding/SEO%20Suite/app/templates/dashboard.html:224)
- [server.py](D:/Coding/SEO%20Suite/app/server.py:1286)

## What Already Exists

SEO Suite already has meaningful product surface area. The roadmap should extend this, not ignore it.

### Existing use cases

- Crawl Access: [dashboard.html](D:/Coding/SEO%20Suite/app/templates/dashboard.html:129)
- On-Page SEO: [dashboard.html](D:/Coding/SEO%20Suite/app/templates/dashboard.html:133)
- Site Health: [dashboard.html](D:/Coding/SEO%20Suite/app/templates/dashboard.html:137)
- Performance: [dashboard.html](D:/Coding/SEO%20Suite/app/templates/dashboard.html:141)
- Search Console: [dashboard.html](D:/Coding/SEO%20Suite/app/templates/dashboard.html:145)
- Authority: [dashboard.html](D:/Coding/SEO%20Suite/app/templates/dashboard.html:149)
- Rankings: [dashboard.html](D:/Coding/SEO%20Suite/app/templates/dashboard.html:153)

### Existing tools

- SERP Preview: [dashboard.html](D:/Coding/SEO%20Suite/app/templates/dashboard.html:190)
- Redirect Chain: [dashboard.html](D:/Coding/SEO%20Suite/app/templates/dashboard.html:194)
- HTTP Headers: [dashboard.html](D:/Coding/SEO%20Suite/app/templates/dashboard.html:198)
- Keyword Density: [dashboard.html](D:/Coding/SEO%20Suite/app/templates/dashboard.html:202)
- Code:Text Ratio: [dashboard.html](D:/Coding/SEO%20Suite/app/templates/dashboard.html:206)
- GZIP & Cache is routed as `/api/tools/compression`: [server.py](D:/Coding/SEO%20Suite/app/server.py:1274)
- Keyword Research route already exists: [server.py](D:/Coding/SEO%20Suite/app/server.py:1301)
- Hidden schema validation backend route already exists: [server.py](D:/Coding/SEO%20Suite/app/server.py:1286)

### Existing generators

- Schema Markup: [dashboard.html](D:/Coding/SEO%20Suite/app/templates/dashboard.html:224)
- robots.txt: [dashboard.html](D:/Coding/SEO%20Suite/app/templates/dashboard.html:228)
- XML Sitemap: [dashboard.html](D:/Coding/SEO%20Suite/app/templates/dashboard.html:232)
- Hreflang Tags: [dashboard.html](D:/Coding/SEO%20Suite/app/templates/dashboard.html:236)
- Meta Tags: [dashboard.html](D:/Coding/SEO%20Suite/app/templates/dashboard.html:240)

### Existing platform patterns to reuse

- Use-case metadata and task definitions: [dashboard.js](D:/Coding/SEO%20Suite/app/static/js/dashboard.js:26)
- Tool fetch/render patterns: [dashboard.js](D:/Coding/SEO%20Suite/app/static/js/dashboard.js:3000)
- Generator fetch/render patterns: [dashboard.js](D:/Coding/SEO%20Suite/app/static/js/dashboard.js:4012)
- Tool routes: [server.py](D:/Coding/SEO%20Suite/app/server.py:1218)

### Existing auth surface

- Login route: [server.py](D:/Coding/SEO%20Suite/app/server.py:254)
- Logout route: [server.py](D:/Coding/SEO%20Suite/app/server.py:273)
- Auth guard already wraps most app routes via `@login_required`: [server.py](D:/Coding/SEO%20Suite/app/server.py:247)

## Implementation Gate

These blockers should be treated as delivery gates, not optional cleanup.

### 1. Sitemap SSRF path

- Why it blocks roadmap work:
  - user-controlled sitemap fetching still bypasses the hardened request layer
  - any sitemap-heavy feature inherits this risk
- Affects:
  - Sitemap Audit
  - Crawl Access improvements
  - Bing Visibility features that compare submitted vs discovered sitemaps
  - any future sitemap ingestion utility
- Source:
  - [REPO_REVIEW_AND_CLEANUP.md](D:/Coding/SEO%20Suite/REPO_REVIEW_AND_CLEANUP.md)

### 2. Schema validation SSRF path

- Why it blocks roadmap work:
  - the hidden schema validation route follows redirects unsafely
  - a first-class Rich Results / Schema Validation UI should not be exposed before this is fixed
- Affects:
  - Rich Results / Schema Validation UI
  - any future “validate live URL” structured-data tool
- Source:
  - [REPO_REVIEW_AND_CLEANUP.md](D:/Coding/SEO%20Suite/REPO_REVIEW_AND_CLEANUP.md)

### 3. Cwd-relative path drift

- Why it blocks roadmap work:
  - runtime data can split across directories when the app is launched outside repo root
  - new report-producing or upload-producing tools become harder to trust and support
- Affects:
  - Bing Visibility workspace
  - IndexNow logs
  - report persistence for new tools
  - profile/settings consistency across new integrations
- Source:
  - [CODE_ERRORS.md](D:/Coding/SEO%20Suite/CODE_ERRORS.md)

### 4. Unguarded numeric request parsing

- Why it blocks roadmap work:
  - malformed client payloads still become 500s in several routes
  - adding new tools without fixing the validation pattern spreads the same failure mode
- Affects:
  - Bing Visibility workspace
  - Trend Explorer
  - keyword and report filters
  - any paginated or threshold-driven tool endpoint
- Source:
  - [CODE_ERRORS.md](D:/Coding/SEO%20Suite/CODE_ERRORS.md)

### 5. Use-case sitemap fallback bug

- Why it blocks roadmap work:
  - sitemap-mode use cases can audit the sitemap XML itself when expansion fails
  - this makes sitemap-driven reporting misleading
- Affects:
  - Crawl Access
  - future Sitemap Audit summaries
  - any roadmap work that promotes sitemap mode more heavily
- Source:
  - [CODE_ERRORS.md](D:/Coding/SEO%20Suite/CODE_ERRORS.md)

### 6. `robots.txt` fetch path bypasses safe wrappers

- Why it blocks roadmap work:
  - `robots.txt` checks still fetch through an internal library path instead of the SSRF-safe wrapper
  - crawlability features should not expand while this path remains inconsistent
- Affects:
  - Crawl Access
  - robots-focused tools
  - Bing-inspired crawl access diagnostics
- Source:
  - [CODE_ERRORS.md](D:/Coding/SEO%20Suite/CODE_ERRORS.md)

### Blocker summary by roadmap area

- Rich Results / Schema Validation UI is blocked by the schema SSRF issue.
- Sitemap Audit is blocked by the sitemap SSRF issue and path consistency issue.
- Bing Visibility is partially blocked by path consistency and request-validation cleanup.
- IndexNow is partially blocked by path consistency and request-validation cleanup.
- Trend Explorer is lower-risk and less coupled to crawl safety, but it should still wait for the general request-validation cleanup.

## Current Surface Improvement Plan

Before adding brand-new categories, improve the surfaces that already exist.

### Use cases

- Crawl Access:
  - upgrade sitemap handling from simple validation to true sitemap intelligence
  - harden `robots.txt` and sitemap fetch safety first
  - tighten task logic so crawlability tasks clearly separate access checks from discovery checks
- On-Page SEO:
  - keep extending derived insight, not just field extraction
  - likely future overlap with rich results visibility and generator feedback
  - good candidate for Groq-assisted rewrite suggestions once issues are detected
  - task logic should distinguish pure extraction checks from content-quality guidance
- Site Health:
  - good candidate for later enrichment from backlink reclamation and deeper header/security surfacing
  - task logic should better expose security-header and DNS trust checks as separate user-facing concepts
- Performance:
  - make this a stronger first-class workspace, not just a standalone technical check
  - prioritize better PageSpeed insight framing, trend/history, and clearer action grouping
  - connect Performance findings to Meta Tags, SERP Preview, and report summaries where useful
  - strong candidate for Groq-generated issue clustering and developer-friendly fix briefs
  - current task logic should better separate lab metrics, mobile-gap analysis, and GSC inspection concepts
- Search Console:
  - this should become one of the product's core anchor workflows
  - prioritize opportunity views, decay detection, CTR improvement suggestions, and richer page/query rollups
  - avoid duplicating raw GSC screens; focus on derived decisions and prioritization
  - strong candidate for Groq-generated plain-English summaries and action plans built from deterministic GSC data
  - current task logic is too thin and should expand beyond just clicks/impressions and top queries
- Authority:
  - strongest improvement path is backlink reclamation and richer action workflows
  - task logic should separate backlink volume, quality, authority, and loss/reclamation states
- Rankings:
  - strongest improvement path is content gap and competitor comparison
  - Groq can later help summarize competitor differences after the data layer exists
  - task logic should split position tracking, SERP feature capture, and competitor comparison into separate checks

### Tools

- SERP Preview:
  - keep as lightweight point tool
  - possible future enhancement is richer OG/Twitter validation or mobile result preview
  - Groq can suggest alternative title and description variants after the preview is rendered
- Redirect Chain:
  - already a useful benchmark for future crawl/accessibility-style quick tools
  - strong candidate for tighter connection to Crawl Access and Site Health summaries
- HTTP Headers:
  - can later absorb more SEO/security guidance without changing its placement
  - especially useful as a bridge between Site Health and Performance findings
- Keyword Density:
  - keep simple; complement it with Trend Explorer instead of overloading it
  - avoid forcing AI into this tool unless it is used only for optional content suggestions
- Code:Text Ratio:
  - stable utility, low roadmap pressure
- GZIP & Cache:
  - useful existing technical tool and a good pattern for additional single-purpose diagnostics
  - should stay closely tied to Performance messaging
- Hidden schema validation:
  - highest-leverage near-term tool exposure after blocker fixes
  - Groq can later explain validation issues in simpler terms after deterministic validation runs
- Keyword Research route:
  - existing backend asset that can later support richer rankings/discovery surfaces
  - should eventually connect more clearly to Search Console and Rankings workflows
  - Groq can later cluster keyword themes and suggest content angles from existing keyword outputs

### Generators

- Schema Markup:
  - should stay separate from validation
  - pair with a dedicated Rich Results / Schema Validation tool instead of merging concepts
  - Groq can assist with field drafting, FAQ or HowTo copy, and content scaffolding
- robots.txt:
  - already strong generator; later add validator or tester only after fetch safety work
- XML Sitemap:
  - generator exists, but the real gap is sitemap auditing and sitemap intelligence
- Hreflang Tags:
  - generator is in place; future validator could be a later phase item
- Meta Tags:
  - already aligned with SERP preview and on-page guidance
  - Groq is a good fit for title and description rewrite suggestions with tone, length, and CTR constraints

### Login and logout

- Login:
  - treat this as a real product surface, not just infrastructure
  - add roadmap attention to setup clarity for GSC, Bing, Moz, DataForSEO, and future provider-backed features
  - long-term opportunity is a cleaner “connected accounts” experience rather than only raw config fields
- Logout:
  - should remain simple and explicit
  - future account/session UX should include safe logout, visible auth status, and clearer post-logout routing

### Groq AI implementation guidance

- Use Groq where fast AI summarization, drafting, clustering, or explanation adds value on top of deterministic SEO data.
- Do not use Groq as the source of truth for:
  - HTTP status
  - sitemap inclusion
  - Search Console metrics
  - PageSpeed metrics
  - backlink counts
- Best-fit pattern:
  - compute facts first with normal tool logic
  - pass the structured results to Groq for summarization, prioritization, drafting, or human-friendly explanation
- Integration note:
  - Groq documents an OpenAI-compatible API at `https://api.groq.com/openai/v1`
- Best first uses:
  - Search Console insight summaries
  - Performance fix-priority explanations
  - meta title and description rewrite suggestions
  - schema and content copy assistance
  - crawl and audit remediation summaries

### Task logic improvement suggestions

- Keep task IDs aligned to actual backend tool outputs and avoid labels that blur multiple concepts.
- Review the current task matrix in:
  - [dashboard.js](D:/Coding/SEO%20Suite/app/static/js/dashboard.js:26)
  - [core/seo_audit.py](D:/Coding/SEO%20Suite/core/seo_audit.py:63)
- Current high-value logic improvements:
  - rename or split Performance task `crawlability` because the label `GSC URL inspection` does not match the task ID clearly enough
  - split Search Console into more than two tasks:
    - clicks and impressions
    - top queries
    - page opportunities
    - coverage or inspection status
    - decay detection
  - split Rankings into:
    - rank tracking
    - SERP features
    - competitor comparison
  - split Authority into:
    - backlink totals
    - domain authority
    - referring domains
    - broken backlink or reclamation signals
  - consider whether `ttfb` belongs in On-Page SEO or should be surfaced primarily through Performance
  - reduce overlap between Crawl Access `sitemap` validation and future Sitemap Audit by making one lightweight and the other report-oriented
  - make task prerequisites explicit in UI logic so users know which checks are skipped without keys or credentials
- Preferred direction:
  - lightweight task lists for default runs
  - richer sub-views and grouped outputs for advanced users

## Phase 0 - Must Fix First

These are roadmap items because they unblock safe delivery of later features.

### Sitemap SSRF fix

- Why:
  - fetch-heavy sitemap features are not safe until this is closed
- Depends on:
  - existing security helpers in `core/security.py`
- Add to:
  - sitemap fetching paths in indexing and audit flows
- Backend shape:
  - route sitemap loads through safe wrappers and validate redirect hops
- Frontend shape:
  - none required unless error messaging changes
- Outputs:
  - safer sitemap ingestion
  - clearer user-facing errors
- API / auth / cost:
  - no external cost
- Priority:
  - P0

### Schema validation SSRF fix

- Why:
  - do not expose the hidden schema validator until live URL fetches are safe
- Depends on:
  - `safe_requests_get()` adoption in schema validation
- Add to:
  - `tools/schema_validator.py`
  - `/api/tools/schema_validate`
- Backend shape:
  - safe redirect-aware fetch path
- Frontend shape:
  - none yet; this is a prerequisite for the later UI
- Outputs:
  - safe live-URL structured-data validation
- API / auth / cost:
  - no external cost
- Priority:
  - P0

### Path anchoring consistency

- Why:
  - new tools should not write reports, uploads, or profiles into split directories
- Depends on:
  - a single canonical project-root path strategy
- Add to:
  - `app/server.py`
  - `core/checker.py`
  - `core/seo_audit.py`
- Backend shape:
  - central path helper and consistent `DATA_DIR` usage
- Frontend shape:
  - none
- Outputs:
  - reliable report discovery
  - stable uploads/profiles/settings persistence
- API / auth / cost:
  - no external cost
- Priority:
  - P0

### Numeric request validation

- Why:
  - new tool endpoints should not inherit avoidable 500s
- Depends on:
  - shared coercion and bounds helpers
- Add to:
  - current and future JSON route handlers
- Backend shape:
  - reusable parsing helpers with consistent 400 responses
- Frontend shape:
  - cleaner validation feedback
- Outputs:
  - safer request handling
  - better error consistency
- API / auth / cost:
  - no external cost
- Priority:
  - P0

### Use-case sitemap fallback fix

- Why:
  - sitemap mode should fail clearly instead of auditing the XML itself
- Depends on:
  - corrected sitemap expansion behavior
- Add to:
  - `/api/usecase/run`
- Backend shape:
  - explicit 400 when sitemap expansion yields zero valid URLs
- Frontend shape:
  - clearer error states in use-case runner
- Outputs:
  - trustworthy sitemap-mode results
- API / auth / cost:
  - no external cost
- Priority:
  - P0

### `robots.txt` safe-fetch fix

- Why:
  - crawlability checks should use the same SSRF-safe fetch standards as the rest of the app
- Depends on:
  - safe request wrappers
- Add to:
  - `tools/phase1.py`
- Backend shape:
  - fetch then parse, rather than library-managed network fetch
- Frontend shape:
  - none
- Outputs:
  - safer crawlability checks
- API / auth / cost:
  - no external cost
- Priority:
  - P0

## Phase 1 - No Paid API Tools After Blockers

These can be built without paid APIs once the safety gates above are closed.

### Rich Results / Schema Validation UI

- Why:
  - the backend route already exists, and structured-data validation is a visible gap in the current Tools surface
- Depends on:
  - schema SSRF fix
- Add to:
  - Tools section in [dashboard.html](D:/Coding/SEO%20Suite/app/templates/dashboard.html:190)
  - keep Schema Markup Generator separate in [dashboard.html](D:/Coding/SEO%20Suite/app/templates/dashboard.html:224)
- Backend shape:
  - reuse `/api/tools/schema_validate`
  - optionally support live URL and pasted JSON-LD as separate modes
- Frontend shape:
  - new Tools panel
  - validation form, result summary, issue list, supported rich-result type guidance
- Outputs:
  - validate live URL
  - validate pasted JSON-LD
  - show supported rich-result types
  - show eligibility vs generic schema validity
- API / auth / cost:
  - no paid API
- Priority:
  - P1

### Sitemap Audit

- Why:
  - this is the clearest use-case upgrade for Crawl Access and the biggest sitemap intelligence gap versus crawler-style tools
- Depends on:
  - sitemap SSRF fix
  - path anchoring consistency
- Add to:
  - Crawl Access surface in [dashboard.html](D:/Coding/SEO%20Suite/app/templates/dashboard.html:129)
  - use-case/task definitions in [dashboard.js](D:/Coding/SEO%20Suite/app/static/js/dashboard.js:26)
  - reports/compare surfaces in [dashboard.html](D:/Coding/SEO%20Suite/app/templates/dashboard.html:684)
- Backend shape:
  - prefer dedicated `tools/sitemap_audit.py`
  - avoid overloading `tools/phase1.py` with another broad responsibility
- Frontend shape:
  - either a new Crawl Access task family or a dedicated report-style tool panel
- Outputs:
  - in sitemap / not in sitemap
  - orphan URL candidates
  - non-indexable sitemap entries
  - duplicate sitemap entries
  - oversized sitemap warnings
- API / auth / cost:
  - no paid API
- Priority:
  - P1

### Trend Explorer

- Why:
  - this expands discovery workflows without requiring paid keyword providers in the baseline plan
- Depends on:
  - numeric request validation cleanup
- Add to:
  - Tools section near keyword tools in [dashboard.html](D:/Coding/SEO%20Suite/app/templates/dashboard.html:190)
- Backend shape:
  - dedicated `tools/trends.py` or equivalent adapter
  - keep it separate from keyword density and rankings
- Frontend shape:
  - new tool panel for term comparison and regional breakdowns
- Outputs:
  - compare terms
  - related queries
  - regional interest
  - rising queries
- API / auth / cost:
  - no paid API in the baseline plan
- Priority:
  - P2

## Phase 2 - Authenticated Free-Platform Integrations

These do not require paid vendor data, but they do depend on user-owned accounts, verification, or protocol setup.

### Bing Visibility Workspace

- Why:
  - Bing Webmaster Tools is the biggest platform gap in the current use-case lineup
- Depends on:
  - path anchoring fix
  - numeric request validation
  - schema SSRF fix is recommended background hardening, but not a strict blocker
- Add to:
  - new use case beside Search Console / Authority / Rankings in [dashboard.html](D:/Coding/SEO%20Suite/app/templates/dashboard.html:145)
  - new settings block near current API setup in [dashboard.html](D:/Coding/SEO%20Suite/app/templates/dashboard.html:846)
- Backend shape:
  - `tools/bing_webmaster.py`
  - routes under `/api/usecase/bing/*` or `/api/tools/bing/*`
- Frontend shape:
  - dedicated use-case workspace with setup state, property selection, and report panels
- Outputs:
  - URL inspection
  - search performance
  - sitemap status
  - site scan summary
  - backlink insights
- API / auth / cost:
  - free platform auth, no paid API
- Priority:
  - P1

### IndexNow Submission Tool

- Why:
  - this gives the product an immediate “take action” workflow after indexing diagnosis
- Depends on:
  - path anchoring fix
  - request validation cleanup
- Add to:
  - Tools section, not Generators: [dashboard.html](D:/Coding/SEO%20Suite/app/templates/dashboard.html:190)
  - settings/setup help near platform/API configuration: [dashboard.html](D:/Coding/SEO%20Suite/app/templates/dashboard.html:817)
- Backend shape:
  - `tools/indexnow.py`
  - routes under `/api/tools/indexnow_submit`
- Frontend shape:
  - action-oriented tool panel with setup guide, single URL submit, batch submit, and result log
- Outputs:
  - single URL submit
  - batch submit
  - submission result log
  - key verification guidance
- API / auth / cost:
  - free protocol, ownership/key setup required
- Priority:
  - P1

### Baseline GSC Opportunity Layer

- Why:
  - Search Console already exists as a use case, but users now expect more derived insight from that data
  - this should be one of the product's highest-priority experience upgrades
- Depends on:
  - existing GSC connection flow
  - numeric request validation cleanup
- Add to:
  - Search Console use case in [dashboard.html](D:/Coding/SEO%20Suite/app/templates/dashboard.html:145)
  - explanatory/help copy in [dashboard.js](D:/Coding/SEO%20Suite/app/static/js/dashboard.js:2201)
- Backend shape:
  - derived-insight layer on top of the existing GSC integration
- Frontend shape:
  - extra tabs/cards for opportunity views rather than a separate product area
- Outputs:
  - high impressions / low CTR
  - decay detection
  - device splits
  - simple cannibalization clues
  - clearer page-level prioritization for content refresh work
  - optional Groq-generated summaries of why a page is underperforming and what to test next
- API / auth / cost:
  - authenticated Google Search Console access
  - no paid API required for baseline
  - optional Groq API for AI summaries
- Priority:
  - P2

### Performance Opportunity Layer

- Why:
  - Performance is already a visible use case and should become a stronger decision surface, not just a diagnostic output
  - users need prioritization across Core Web Vitals, blocking assets, and page groups
- Depends on:
  - existing PageSpeed integration
  - numeric request validation cleanup
- Add to:
  - Performance use case in [dashboard.html](D:/Coding/SEO%20Suite/app/templates/dashboard.html:141)
  - performance settings/help area in [dashboard.html](D:/Coding/SEO%20Suite/app/templates/dashboard.html:869)
- Backend shape:
  - derived-insight layer on top of existing performance checks
  - aggregate repeated issues across page sets rather than only per-URL output
- Frontend shape:
  - issue clusters, opportunity cards, and trend/history summaries inside the Performance workspace
- Outputs:
  - Core Web Vitals risk grouping
  - repeated asset bottlenecks
  - page templates with recurring performance issues
  - fix-priority buckets for dev teams
  - optional Groq-generated remediation briefs for non-technical stakeholders or developers
- API / auth / cost:
  - existing PageSpeed/API setup
  - no separate paid vendor needed beyond the current performance dependency
  - optional Groq API for explanation and prioritization text
- Priority:
  - P2

### Groq AI Assistance Layer

- Why:
  - Groq is best used as a fast explanation and drafting layer on top of existing SEO facts, not as a replacement for crawler or API logic
- Depends on:
  - stable structured outputs from current use cases, tools, and generators
  - provider selection and prompt guardrails
- Add to:
  - Search Console
  - Performance
  - On-Page SEO
  - SERP Preview
  - Meta Tags
  - Schema Markup
  - future Sitemap Audit reports
- Backend shape:
  - optional provider adapter such as `tools/ai_assist.py`
  - prompt from normalized report JSON, not raw scraped HTML where avoidable
- Frontend shape:
  - opt-in `Explain with AI`, `Draft Fixes`, or `Generate Variants` actions
- Outputs:
  - explain findings in plain English
  - summarize top issues
  - draft remediation steps
  - generate metadata or schema copy variants
  - cluster keyword and page themes
- API / auth / cost:
  - optional Groq API integration
  - use OpenAI-compatible base URL if chosen
- Priority:
  - P2

## Phase 3 - Paid / Metered Data Features

These depend on external vendor data, metered providers, or enrichment layers that are not purely free-platform integrations.

### Content Gap / Competitor Gap

- Why:
  - this is the strongest competitive-analysis gap in the current Rankings surface
- Depends on:
  - rankings/provider data integration
- Add to:
  - Rankings use case in [dashboard.html](D:/Coding/SEO%20Suite/app/templates/dashboard.html:153)
  - or a dedicated competitor tool under [dashboard.html](D:/Coding/SEO%20Suite/app/templates/dashboard.html:190)
- Backend shape:
  - provider-backed keyword overlap and opportunity pipeline
- Frontend shape:
  - competitor inputs, overlap tables, opportunity filters, export/report view
- Outputs:
  - keywords competitors rank for that you do not
  - overlap counts
  - opportunity prioritization
- API / auth / cost:
  - usually paid provider required
- Priority:
  - P2

### Backlink Reclamation

- Why:
  - Authority already exposes backlink-adjacent value, but not the action workflow users need next
- Depends on:
  - backlink provider data
- Add to:
  - Authority use case in [dashboard.html](D:/Coding/SEO%20Suite/app/templates/dashboard.html:149)
- Backend shape:
  - backlink inventory plus broken-target and redirect recommendation logic
- Frontend shape:
  - action table with lost value, source domain, and recommended fix
- Outputs:
  - broken incoming links
  - referring domains
  - recommended redirect targets
- API / auth / cost:
  - usually paid provider required
- Priority:
  - P3

### AI Visibility / Citation Tracking

- Why:
  - AI visibility is now a mainstream SEO platform category and a likely future expectation
- Depends on:
  - provider selection
- Add to:
  - new use case near Rankings in [dashboard.html](D:/Coding/SEO%20Suite/app/templates/dashboard.html:153)
  - report/history surfaces in [dashboard.html](D:/Coding/SEO%20Suite/app/templates/dashboard.html:684)
- Backend shape:
  - provider adapter plus normalized citation/mention history model
- Frontend shape:
  - workspace for cited URLs, sources, trends, and share-of-voice style reporting
- Outputs:
  - cited URLs
  - mention frequency
  - source breakdown
  - trend over time
- API / auth / cost:
  - usually paid provider required
- Priority:
  - P3

### Paid-Enriched GSC Opportunity Layer

- Why:
  - the next step after baseline GSC insights is enrichment beyond what native GSC alone exposes
- Depends on:
  - baseline GSC opportunity layer
  - enrichment provider or approved vendor strategy
- Add to:
  - Search Console use case in [dashboard.html](D:/Coding/SEO%20Suite/app/templates/dashboard.html:145)
- Backend shape:
  - enrichment pipeline layered on top of authenticated GSC data
- Frontend shape:
  - premium insight cards or advanced comparison/report panels
- Outputs:
  - anonymized query recovery
  - extended history
  - competitive overlay / enrichment
- API / auth / cost:
  - paid or metered enrichment usually required
- Priority:
  - P3

## Build Order

Use this order unless a later dependency changes materially.

1. Phase 0 blockers
2. Rich Results / Schema Validation UI
3. Sitemap Audit
4. Bing Visibility Workspace
5. IndexNow Submission Tool
6. Trend Explorer
7. Baseline GSC Opportunity Layer
8. Performance Opportunity Layer
9. Groq AI Assistance Layer
10. Content Gap / Competitor Gap
11. Backlink Reclamation
12. AI Visibility / Citation Tracking
13. Paid-Enriched GSC Opportunity Layer

Why this order:

- it closes known security and runtime issues first
- it exposes already-partially-built capability next
- it then strengthens the two most important strategic workspaces: Search Console and Performance
- it adds AI only after the underlying data surfaces are trustworthy
- it then adds free and high-leverage tools
- it leaves provider-dependent work for later

## Do Not Start Before

- fix the SSRF-safe sitemap fetch path
- fix schema validation redirect safety
- normalize path anchoring to project root
- harden numeric request parsing
- add route-level tests for every new tool
- ensure every user-facing tool has both backend and dashboard wiring

## Notes For Future Updates

- Keep use cases, tools, and generators distinct in planning:
  - use cases are report-oriented workflows
  - tools are single-purpose diagnostics or actions
  - generators are output builders
- Keep Search Console and Performance as top-level strategic surfaces:
  - many future insights should enrich these workspaces rather than becoming disconnected standalone pages
- Use Groq as an explanation layer, not a measurement layer.
- Do not merge Schema Markup generation and schema validation into one ambiguous panel.
- Do not place IndexNow under Generators; it belongs under Tools.
- Treat login/logout and connected-account setup as part of the product experience for authenticated integrations.
- When updating this roadmap, cross-check the current sidebar inventory first so planning stays anchored to the shipped product.
