# New Tools & Use Cases

## Purpose
Document high-value product and tooling ideas for SEO Suite that map to the repo's actual implementation and visible dashboard surface.

This update is grounded in the repo's current code and user-facing routes:
- use cases already exist for Crawl Access, On-Page SEO, Site Health, Performance, Search Console, Authority, and Rankings
- existing tools include SERP Preview, Redirect Chain, HTTP Headers, Keyword Density, Code:Text Ratio, GZIP & Cache, Schema Validation, IndexNow Submit, Sitemap Audit, Bing Visibility, and GSC analytics helpers
- existing generators include Schema Markup, robots.txt, XML Sitemap, Hreflang Tags, and Meta Tags
- architecture and stack guidance also reflects the hidden `.agentmaster/codebase.xml` / `GITHUB_REFERENCE.md` research on Flask/async, task queues, browser automation, and crawler UI patterns

## Technical stack alignment
This plan also assumes the current SEO Suite architecture is best served by:
- preserving the Flask-based UI while moving crawl-heavy work into background workers or async-friendly routes
- using task queue / progress persistence patterns rather than synchronous blocking crawls, as suggested by the hidden tech-stack research
- aligning browser automation/scrape logic with Playwright/SeleniumBase-style best practices instead of ad hoc page fetches
- keeping AI as an explanation layer on top of deterministic checks, not as the primary source of truth for crawl, index, or schema verdicts

## Current gaps and risk gates
Before building new products, harden the existing partially built surfaces and preserve safety.

### Major blockers
- Schema validation is exposed through a hidden backend route and must not be promoted until redirect/SSRF safety is proven.
- robots.txt and sitemap fetch logic need to be aligned with the SSRF-safe wrappers in `core/security.py` before adding crawl-heavy tools.
- runtime path anchoring needs to be consistent for reports, uploads, generated files, and history so new tools do not split data across directories.
- numeric request parsing must be made robust in `app/server.py` (and the blueprints under `app/blueprints/`), especially for filter-driven and pagination-driven APIs. The shared `_int(...)` helper lives in `app/state.py`.

## Recommended new use cases
These workflows should layer on top of the current dashboard categories and existing backend modules.

### 1. Bing Visibility Workspace
What to build:
- a workspace that consolidates Bing traffic, crawl health, sitemap status, and URL inspection.
- an overview panel for site-level impressions, clicks, and crawl stats.
- a submitted sitemap status section with index coverage, duplicate/invalid sitemap warnings, and submit/re-submit buttons.
- a per-URL inspection panel with Bing index status, last crawl, canonical verdict, and crawl verdict detail.
- one-click Bing submit/re-submit flow for selected pages or sitemap groups.

Why now:
- the repo already contains `tools/bing_webmaster.py` and monitored Bing/GSC dashboard entries.
- this use case turns existing Bing diagnostics into a coherent decision surface.

Implementation notes:
- reuse the existing Bing credentials model and safe request patterns.
- keep the UI focused on actionable signals, not raw data rows.
- add Groq summaries that translate crawl and index health into plain-language recommendations for non-technical users.

### 2. Crawl Intelligence
What to build:
- a richer Crawl Access workspace that unifies robots.txt, sitemap analysis, and crawl discovery.
- live `robots.txt` analysis with block/allow decisions, directive overlap, and sitemap declarations.
- sitemap discovery vs crawl discovery comparison with missing pages, unknown URLs, and non-indexable entries.
- index rate alerts, unsupported URL pattern warnings, and HTTP/HTTPS coverage reports.
- a crawl issue triage panel that merges Bing crawl data, sitemap health, and robots findings.

Why now:
- the repo already has sitemap audit capabilities and robots checks in `tools/phase1.py`.
- this strengthens the existing crawlability workflow without adding a completely new surface.

Implementation notes:
- implement robots validation as a dedicated tool first, then promote it into the Crawl Intelligence workspace.
- treat mixed-content and protocol coverage as diagnostic alerts rather than hard failures.
- use Groq to convert crawl findings into prioritized remediation steps, not to replace the raw crawl data.

### 3. Search Console Opportunity
What to build:
- an opportunity workspace that prioritizes GSC findings instead of just showing rows of clicks and impressions.
- highlight high-impression, low-CTR pages; pages with position drops; queries with volume and decay; and coverage-impact pages.
- surface indexing gaps, coverage issue severity, manual actions, and URL inspection summaries for flagged pages.
- provide device / search appearance segmentation for priority pages.
- include “next best fix” recommendations for titles, descriptions, internal links, and content consolidation.

Why now:
- Search Console is already a core product surface in the repo.
- this use case moves the app from data reporting into decision support.

Implementation notes:
- build the opportunity analyzer as a separate tool that ranks pages/queries by impact.
- add query cannibalization detection using top query overlap and page intent drift.
- use Groq only for executive summaries and remediation copy, not for the underlying ranking or trend calculations.

### 4. Authority / Backlink Reclamation
What to build:
- a backlink workflow that exposes reclamation candidates, lost links, and competitor overlap.
- broken backlink discovery, lost backlink alerts, and referral domain overlap reports.
- link quality segmentation for dofollow/nofollow, domain authority proxies, and spam risk.
- tie backlink findings to action items like outreach prioritization and content refresh.

Why now:
- the current Authority use case is already present and can become more actionable with existing backlink data.
- it closes the gap between backlink counts and real outreach work.

Implementation notes:
- reuse existing backlink checks in `tools/phase4.py` and surface them with stronger failure categories.
- avoid overloading the workspace with raw link tables; focus on high-value reclamation candidates.
- add trend alerts for lost or gained backlinks over time.

### 5. Content + SERP Optimization
What to build:
- a workflow that bridges Rankings and On-Page SEO with content action guidance.
- title/description rewrite guidance based on actual page content and target keywords.
- SERP feature targeting suggestions based on keyword intent and current SERP layout.
- page fit scoring for target keyword groups and content gap checks against competitor snippets.
- Groq-assisted rewrite suggestions and SERP preview copy drafts for headlines, meta descriptions, and feature snippets.

Why now:
- this connects audit insights to the content improvements that drive ranking impact.
- it leverages existing SERP preview, on-page, and keyword research features.

Implementation notes:
- keep the scoring deterministic and use Groq only for wording and recommendation summaries.
- link each suggested update back to the page and the query or keyword set it supports.
- surface performance and crawl risks alongside content recommendations.

## Recommended new tools
Build these as focused diagnostics that feed the broader workflows above.

### 1. robots.txt Tester
What to build:
- a tool that validates a live `robots.txt` file for syntax, crawl access, sitemap declarations, and rule overlap.
- report conflicting rules, unreachable host directives, and unsupported path patterns.

Why now:
- it complements the existing robots generator and the robots/access checks in `tools/phase1.py`.

Implementation notes:
- expose it as a standalone diagnostics tool before embedding it in Crawl Intelligence.
- use deterministic allow/block logic; reserve Groq for explanatory summaries only.

### 2. hreflang Validator
What to build:
- a live validator for hreflang tags, alternate URLs, and x-default coverage.
- detect duplicate language codes, relative URL mismatches, canonical/hreflang conflicts, and missing alternates.

Why now:
- the repo already performs hreflang checks in `tools/phase1.py`.

Implementation notes:
- make the output actionable with specific fix recommendations for each invalid URL pair.
- include plain-language diagnostics for common hreflang pitfalls.

### 3. Rich Results / Structured Data Tester
What to build:
- a tool that extracts JSON-LD from a live page, validates it against Schema.org types, and checks required properties.
- surface missing required fields, invalid property values, duplicate schema declarations, and schema type mismatches.

Why now:
- `tools/schema_validator.py` already contains the backend fetch and validation logic.

Implementation notes:
- keep the tool behind safe SSRF/redirect handling until the route is hardened.
- use Groq to explain schema errors and suggest missing properties, but do not use it to infer the schema from scratch.

### 4. URL Inspection / Live Index Status
What to build:
- a live diagnostic tool that combines Bing URL inspection with any available GSC indexing state.
- surface index status, last crawl time, canonical status, mobile/crawl verdicts, and manual-action indicators.

Why now:
- this is the natural intersection of Bing Visibility and Search Console Opportunity.

Implementation notes:
- keep the tool focused on one URL at a time and one truth-source at a time.
- use the existing Bing and GSC service connectors without inventing new index-status inference.

### 5. Search Console Opportunity Analyzer
What to build:
- a standalone analyzer that ranks pages and queries by impact instead of simply displaying raw GSC rows.
- include CTR, average position, query volume, device/geo splits, coverage errors, and query cannibalization score.

Why now:
- it transforms Search Console data into action recommendations.

Implementation notes:
- surface recommended fixes for page/query pairs and track the priority of each recommendation.
- use Groq to convert the opportunity set into concise narratives for stakeholders.

### 6. Backlink Health / Broken Backlink Tool
What to build:
- a backlink health dashboard that surfaces broken backlinks and reclamation opportunities.
- highlight inbound links with 4xx/5xx targets, redirects, or missing pages.

Why now:
- it extends the existing backlink checks in `tools/phase4.py` into a more useful workflow.

Implementation notes:
- avoid presenting raw backlink tables unless they are filtered to high-value recoveries.
- include a simple action list: reclaim, redirect, update, or remove.

### 7. Keyword Demand / Trend Comparison
What to build:
- a query demand tool that compares keyword volume, seasonality, and overlap across target terms.
- keep it separate from Keyword Density and leverage the existing keyword research route.

Why now:
- it provides a higher-level research layer that the current keyword tools do not address.

Implementation notes:
- pair the tool with keyword intent categories and trend movement indicators.
- avoid using Groq for the base demand/volume calculations.

## Recommended new generators
Keep generators focused on authoring support and close the loop to validation.

### 1. Enhanced Schema Markup Generator
What to build:
- a generator for common rich result types with usage hints, required fields, and sample JSON-LD.
- include a built-in link to the schema validation tester.

Why now:
- generation should remain separate from validation while still supporting a fast authoring workflow.

### 2. robots.txt Generator + Validator
What to build:
- generate robots directives and optionally validate the deployed file against the live site.
- include recommended default rules for sitemap discovery and common crawler support.

Why now:
- closing the authoring/checking loop is the highest-value path for robots configuration.

### 3. XML Sitemap Generator + Index Audit
What to build:
- generate an XML sitemap and audit it for size limits, unsupported URL patterns, missing required entries, and discovery issues.
- include a sitemap index generation option for larger sites.

Why now:
- this pairs naturally with the existing sitemap audit tool and future Bing/Sitemap work.

### 4. Hreflang Tag Generator + Validator
What to build:
- generate HTML `<link rel="alternate">` markup and HTTP header alternatives for multilingual/canonical setups.
- validate page consistency and x-default coverage as part of the workflow.

Why now:
- the generator and validator are complementary and can be surfaced together cleanly.

### 5. Meta Tags Generator + Draft Suggestions
What to build:
- generate title and description variants with length guidance and keyword fit scoring.
- pair generated drafts with the existing SERP preview tool.

Why now:
- it strengthens the content optimization workflow without adding unnecessary diagnostic noise.

### 6. SEO Copy Brief Generator
What to build:
- generate a page outline, heading structure, target keyword list, and basic keyword usage guidance.
- keep it clearly authored as a content planning helper, not an audit tool.

Why now:
- it extends the generator surface into content planning while preserving the audit/tool distinction.

## Implementation priorities
1. Harden existing partial surfaces first: Bing Visibility, Schema Validation, Sitemap Audit, IndexNow.
2. Fix request validation and safe fetch behavior before exposing new cross-domain or crawl-heavy tools.
3. Ship robots, hreflang, and schema validation tools before adding more AI-driven generators.
4. Keep new tools deterministic and diagnostic, reserving AI for explanation, summarization, and draft guidance only.

## Groq AI integration guidance
- Apply Groq only after deterministic results are available; do not use it as the source of truth for metrics, coverage, crawl status, or indexing state.
- Best use cases for Groq in this repo:
  - summarizing GSC opportunity findings into prioritized action briefs
  - explaining schema validation and structured data issues clearly
  - drafting recommended title/description variants from page content
  - generating remediation steps for crawl, sitemap, and backlink issues
  - converting audit results and tool outputs into executive-friendly summaries
  - creating contextual help text for new tools and generators in the dashboard
- Avoid using Groq to replace core checks such as robots.txt allow/block decisions, HTTP status, sitemap indexing counts, backlink totals, or URL inspection verdicts.

## Notes
- Preserve the distinction between:
  - Use cases: broad workflows and decision surfaces.
  - Tools: single-purpose diagnostics or actions.
  - Generators: markup/content builders.
- Do not merge Schema Markup generation with schema validation into one ambiguous panel.
- Do not place IndexNow under Generators; it belongs under Tools.
- Use the existing dashboard and route patterns in `app/static/js/dashboard.js`, `app/server.py`, and the blueprint modules under `app/blueprints/` when adding items. New route groups should be added as blueprints (see `app/blueprints/site.py` for the minimal pattern, `app/blueprints/auth_views.py` for one with rate-limited endpoints).
