# New Tools & Use Cases

## Purpose
Document high-value product and tooling ideas for SEO Suite based on the current implementation, visible dashboard surface, and existing backend routes.

This update is grounded in the repo's real feature set:
- use cases already exist for Crawl Access, On-Page SEO, Site Health, Performance, Search Console, Authority, and Rankings
- tools already exist for SERP Preview, Redirect Chain, HTTP Headers, Keyword Density, Code:Text Ratio, GZIP & Cache, Schema Validation, IndexNow Submit, Sitemap Audit, Bing Visibility, and several GSC-oriented tools
- generators already exist for Schema Markup, robots.txt, XML Sitemap, Hreflang Tags, and Meta Tags

## Current gaps and risk gates
Before adding new use cases, the highest value work is to harden and expose the existing partially built surfaces.

### Major blockers
- Schema validation currently exists as a hidden backend route and should not be promoted until redirect/SSRF safety is fully validated.
- robots.txt and sitemap fetch logic must be fully aligned with the SSRF-safe wrappers before adding crawl-heavy new tools.
- runtime path anchoring must remain consistent for reports, uploads, and generated files so new tools do not split data across directories.
- numeric request parsing must be made robust across all existing routes before adding more filter-driven or pagination-driven APIs.

## Recommended new use cases
These should be built on top of the existing dashboard categories and current route surface.

### 1. Bing Visibility Workspace
- Formalize the existing Bing panel into a workspace rather than a standalone tool.
- Include:
  - site-level Bing traffic overview
  - crawl stats and crawl error summary
  - submitted sitemap status and index rate
  - per-URL inspection for Bing index status / crawl verdict
  - one-click Bing submit / re-submit flow
- Why: the repo already has `tools/bing_webmaster.py` and dashboard entries for Bing and GSC tools, so this is a natural anchor use case.
- Groq can generate plain-language crawl and index health summaries for non-technical users.

### 2. Crawl Intelligence
- Expand the current Crawl Access use case with richer sitemap and robots intelligence.
- Include:
  - live `robots.txt` analysis plus overlap and block checks
  - sitemap discovery vs crawl discovery comparison
  - non-indexable sitemap entries and index rate alerts
  - mixed-content and HTTP/HTTPS coverage checks across discovered URLs
  - crawl issue triage from Bing and sitemap sources
  - Groq-generated remediation guidance that translates crawl findings into prioritized fixes
- Why: this builds on the existing crawlability use case and the current sitemap tool without introducing a completely new product surface.

### 3. Search Console Opportunity
- Turn the GSC data surface into a prioritized opportunity workspace.
- Include:
  - high-impression, low-CTR pages
  - pages with position drops or query trend deterioration
  - coverage issue impact scoring and indexing gap alerts
  - manual actions / URL inspection summaries for flagged pages
  - top queries per page and query cannibalization detection
  - device / search appearance segmentation for priority pages
  - action recommendations for titles, descriptions, internal linking, and consolidation
  - a “next best fix” view for page/query pairs
  - Groq-generated plain-English summaries of opportunities and prioritized next actions
- Why: Search Console is already a core workflow in the product; this use case should differentiate raw data from derived decisions and provide human-readable guidance.

### 4. Authority / Backlink Reclamation
- Convert the current authority/backlink checks into a more actionable link workflow.
- Include:
  - broken backlink discovery and reclamation candidates
  - competitor link gap and referring domain overlap
  - link quality segmentation (dofollow / nofollow / spam score)
  - backlink loss or gain alerts over time
- Why: the current Authority use case is structurally ready for this, and it closes the gap between backlink numbers and action.

### 5. Content + SERP Optimization
- Bridge existing Rankings and On-Page SEO workflows.
- Include:
  - title/description rewrite guidance from real page content
  - SERP feature targeting suggestions based on keyword intent
  - page fit scoring for target keyword groups
  - on-page content gap checks against competitors and SERP signals
  - Groq-assisted rewrite suggestions and SERP preview copy drafts
- Why: this connects audit insights to the content actions that matter most for ranking impact.

## Recommended new tools
These should be built as single-purpose diagnostics that can feed the broader use cases.

### 1. robots.txt Tester
- Validate a live `robots.txt` file for syntax, crawl access, sitemap declarations, and rule overlap.
- Complement the existing robots generator and the robots check in `tools/phase1.py`.

### 2. hreflang Validator
- Inspect live hreflang tags, alternate URLs, and x-default coverage.
- Detect duplicate language codes, relative URL mismatches, and canonical/hreflang conflicts.
- Why: the repo already performs hreflang checks in `tools/phase1.py`, so this becomes a usable standalone validator.

### 3. Rich Results / Structured Data Tester
- Extract JSON-LD from a live URL and validate it against known Schema.org types.
- Summarize issues in user-facing language and point to missing required fields.
- Use Groq to explain schema errors, suggest missing properties, and translate validation output into clear remediation steps.
- Why: `tools/schema_validator.py` already implements the backend fetch and validation logic; the missing piece is safe exposure and a clean UI.

### 4. URL Inspection / Live Index Status
- Combine Bing URL inspection and any GSC URL indexing state into one live diagnostic page.
- Surface index status, last crawl time, canonical status, mobile/crawl verdicts, and manual-action indicators.
- Why: a live per-URL inspection tool is a natural bridge between Bing Visibility and Search Console Opportunity.

### 5. Search Console Opportunity Analyzer
- Build a standalone tool that ranks pages and queries by impact rather than just showing raw GSC rows.
- Include CTR, position, query volume, device/geo segment splits, coverage errors, top queries per page, and prioritization logic.
- Add a separate “query cannibalization” panel and “position decay / trend” tracker.
- Use Groq to translate the opportunity set into concise recommendations, drag-and-drop priorities, and summary narratives for non-technical stakeholders.

### 6. Backlink Health / Broken Backlink Tool
- Surface broken backlinks and reclamation opportunities from the existing DataForSEO-backed backlink checks.
- Why: it's the most obvious extension of the current backlink/backlink count checks in `tools/phase4.py`.

### 7. Keyword Demand / Trend Comparison
- Add a higher-level research tool to compare query demand, seasonality, and term overlap.
- This should remain separate from Keyword Density and leverage the existing keyword research route.

## Recommended new generators
The generator surface should stay focused on authoring support and not be overloaded with diagnostics.

### 1. Enhanced Schema Markup Generator
- Keep generation separate from validation.
- Add a validation/tester step or a direct link to the schema validation tool.
- Include common rich result types and usage hints for each.

### 2. robots.txt Generator + Validator
- Generate valid robots rules and then optionally validate the deployed file.
- Why: closing the loop between authoring and checking is the highest value path.

### 3. XML Sitemap Generator + Index Audit
- Add sitemap index generation plus structural audit feedback.
- Include warnings for sitemap size limits, unsupported path patterns, and missing required sitemap entries.

### 4. Hreflang Tag Generator + Validator
- Generate HTML `<link rel="alternate">` markup and HTTP header alternatives.
- Add a validator for live page consistency and x-default coverage.

### 5. Meta Tags Generator + Draft Suggestions
- Generate title and description variants with target length guidance.
- Pair with the existing SERP preview and on-page toolset.

### 6. SEO Copy Brief Generator
- Build a page outline, heading structure, and keyword usage guidance for a topic.
- Why: this extends generators into content planning without making it the core audit surface.

## Implementation priorities
1. Harden existing partial surfaces first: Bing Visibility, Schema Validation, Sitemap Audit, IndexNow.
2. Fix request validation and safe fetch behavior before exposing new cross-domain or crawl-heavy tools.
3. Ship robots/hreflang/schema validation tools before adding more AI-driven generators.
4. Keep new tools deterministic and diagnostic, reserving AI for explanation, summarization, and draft guidance only.

## Groq AI integration guidance
- Apply Groq only after the deterministic data is computed; do not use it as the source of truth for metrics, coverage, or crawl status.
- Best use cases for Groq in this repo:
  - summarizing GSC opportunity findings into prioritized action briefs
  - explaining schema validation and structured data issues in plain English
  - drafting recommended title/description variants from page content
  - generating step-by-step guidance for crawl and backlink remediation
  - converting audit results, GSC reports, and tool outputs into executive-friendly summaries
  - creating contextual help text for new tools and generators on the dashboard
- Avoid using Groq to replace core checks such as robots.txt allow/block decisions, HTTP status, sitemap indexing counts, or backlink totals.

## Notes
- Preserve the distinction between:
  - Use cases: broad workflows and decision surfaces.
  - Tools: single-purpose diagnostics or actions.
  - Generators: markup/content builders.
- Do not merge Schema Markup generation with schema validation into one ambiguous panel.
- Do not place IndexNow under Generators; it belongs under Tools.
- Use the existing dashboard and route patterns in `app/static/js/dashboard.js` and `app/server.py` when adding items.
