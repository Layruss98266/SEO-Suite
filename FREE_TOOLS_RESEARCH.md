# Free Tools Research

## Purpose

This document tracks currently popular free SEO tools and free tiers that are relevant to SEO Suite planning.

Research rules used here:

- official sources only
- focus on free public tools, free protocols, or clearly documented free tiers
- map each tool back to the real SEO Suite surfaces already in the dashboard

Primary planning companion:

- [TOOL_ROADMAP.md](D:/Coding/SEO%20Suite/TOOL_ROADMAP.md)

## Current SEO Suite Surface To Compare Against

### Use cases already in product

- Crawl Access: [dashboard.html](D:/Coding/SEO%20Suite/app/templates/dashboard.html:129)
- On-Page SEO: [dashboard.html](D:/Coding/SEO%20Suite/app/templates/dashboard.html:133)
- Site Health: [dashboard.html](D:/Coding/SEO%20Suite/app/templates/dashboard.html:137)
- Performance: [dashboard.html](D:/Coding/SEO%20Suite/app/templates/dashboard.html:141)
- Search Console: [dashboard.html](D:/Coding/SEO%20Suite/app/templates/dashboard.html:145)
- Authority: [dashboard.html](D:/Coding/SEO%20Suite/app/templates/dashboard.html:149)
- Rankings: [dashboard.html](D:/Coding/SEO%20Suite/app/templates/dashboard.html:153)

### Tools already in product

- SERP Preview: [dashboard.html](D:/Coding/SEO%20Suite/app/templates/dashboard.html:190)
- Redirect Chain: [dashboard.html](D:/Coding/SEO%20Suite/app/templates/dashboard.html:194)
- HTTP Headers: [dashboard.html](D:/Coding/SEO%20Suite/app/templates/dashboard.html:198)
- Keyword Density: [dashboard.html](D:/Coding/SEO%20Suite/app/templates/dashboard.html:202)
- Code:Text Ratio: [dashboard.html](D:/Coding/SEO%20Suite/app/templates/dashboard.html:206)
- Hidden schema validation backend route: [server.py](D:/Coding/SEO%20Suite/app/server.py:1286)
- Keyword research backend route: [server.py](D:/Coding/SEO%20Suite/app/server.py:1301)

### Generators already in product

- Schema Markup: [dashboard.html](D:/Coding/SEO%20Suite/app/templates/dashboard.html:224)
- robots.txt: [dashboard.html](D:/Coding/SEO%20Suite/app/templates/dashboard.html:228)
- XML Sitemap: [dashboard.html](D:/Coding/SEO%20Suite/app/templates/dashboard.html:232)
- Hreflang Tags: [dashboard.html](D:/Coding/SEO%20Suite/app/templates/dashboard.html:236)
- Meta Tags: [dashboard.html](D:/Coding/SEO%20Suite/app/templates/dashboard.html:240)

### Auth surface already in product

- Login route: [server.py](D:/Coding/SEO%20Suite/app/server.py:254)
- Logout route: [server.py](D:/Coding/SEO%20Suite/app/server.py:273)

## Quick Summary

The strongest free-tool categories for SEO Suite right now are:

- Google-owned diagnostics and search data
- Bing Webmaster / IndexNow workflows
- Ahrefs free tools and free verified-site tier
- Semrush free public utilities
- Screaming Frog free crawl tier

Most important planning conclusion:

- the biggest near-term value is not “more generators”
- it is stronger use-case intelligence and stronger point tools built around the current surfaces
- the two most important strategic use cases to deepen are Search Console and Performance
- if AI is added, Groq is a strong candidate for fast explanation and drafting layers on top of existing SEO data

## Tool Catalog

### 1. Google Search Console

- Type:
  - free platform
- Official source:
  - https://developers.google.com/search/blog/2022/01/url-inspection-api
  - https://support.google.com/webmasters/answer/7552505
- Notable free capabilities:
  - URL Inspection data
  - indexing and crawl diagnostics
  - rich result reports
  - search performance
  - sitemap submission and monitoring
- Why it matters to SEO Suite:
  - Search Console already exists as a use case
  - the gap is better derived insight, not basic access
- Suggested SEO Suite mapping:
  - improve the existing Search Console use case
  - add a baseline GSC opportunity layer

### 2. Google Rich Results Test

- Type:
  - free public tool
- Official source:
  - https://search.google.com/test/rich-results
  - https://developers.google.com/search/docs/appearance/structured-data
- Notable free capabilities:
  - tests a live public page
  - identifies rich-result eligibility
  - previews how eligible rich results may appear
- Why it matters to SEO Suite:
  - you already have Schema Markup generation
  - you already have a hidden schema validation backend route
  - the missing piece is a visible, dedicated validation tool
- Suggested SEO Suite mapping:
  - first-class `Rich Results / Schema Validation` tool
  - keep it separate from the Schema Markup generator
- Roadmap caution:
  - expose only after the schema SSRF issue is fixed

### 3. Google Trends

- Type:
  - free public tool
- Official source:
  - https://support.google.com/trends/answer/6248105
  - https://support.google.com/trends/answer/4359550
- Notable free capabilities:
  - compare terms
  - regional interest
  - related searches
  - export and embed
- Why it matters to SEO Suite:
  - strong fit for keyword discovery and topical demand planning
  - complements Keyword Density and keyword research rather than replacing them
- Suggested SEO Suite mapping:
  - `Trend Explorer` in Tools near keyword-focused utilities

### 4. Bing Webmaster Tools

- Type:
  - free platform
- Official source:
  - https://www.bing.com/webmasters
  - https://blogs.bing.com/webmaster/June-2025/Start-Using-Bing-Webmaster-Tools-to-Improve-Your-Site-Visibility
  - https://blogs.bing.com/webmaster/september-2020/Introducing-the-Bing-Webmaster-Tools-URL-Inspection-Tool
- Notable free capabilities:
  - search performance reporting
  - URL Inspection
  - keyword research
  - backlink insights
  - site explorer
  - sitemap reporting
  - site scan
  - robots.txt tester
  - crawl control
- Why it matters to SEO Suite:
  - this is the biggest visibility-platform gap in the current use-case lineup
- Suggested SEO Suite mapping:
  - `Bing Visibility` use case
  - Bing settings block
- Roadmap caution:
  - best added after path consistency and request-validation cleanup

### 5. IndexNow

- Type:
  - free protocol / submission workflow
- Official source:
  - https://www.indexnow.org/index
  - https://www.indexnow.org/documentation
- Notable free capabilities:
  - instant notification for added, updated, or deleted URLs
  - single URL and batch URL submission
  - shared distribution across participating search engines
- Why it matters to SEO Suite:
  - ideal companion to the existing indexing checker
  - gives users an action after diagnosis
- Suggested SEO Suite mapping:
  - `IndexNow Submit` under Tools
  - optional batching from report deltas later
- Roadmap caution:
  - keep this under Tools, not Generators

### 6. Ahrefs Free Account

- Type:
  - free tier
- Official source:
  - https://ahrefs.com/free
- Notable free capabilities:
  - Site Explorer for verified websites
  - Site Audit for verified websites
  - Web Analytics
  - SEO Toolbar
  - AI Content Helper
  - free-forever limited access
- Explicit limits shown:
  - Site Audit: 5K crawl credits/month per project
  - Site Explorer: 1K backlinks and keywords visible at once
- Why it matters to SEO Suite:
  - strong benchmark for verified-site workflows and health-score style UX
  - useful reference for how to evolve Search Console, Authority, and report history views
- Suggested SEO Suite mapping:
  - better verified-site style dashboards
  - health score, crawl history, richer trend views

### 7. Ahrefs Free SEO Tools

- Type:
  - free public tool collection
- Official source:
  - https://ahrefs.com/free-seo-tools
  - https://ahrefs.com/seo-toolbar
- Notable free capabilities:
  - Keyword Generator
  - Keyword Difficulty Checker
  - Bing Keyword Tool
  - Backlink Checker
  - Broken Link Checker
  - Website Authority Checker
  - Traffic Checker
  - SERP Checker
  - Keyword Rank Checker
  - AI Visibility Checker
  - SEO Toolbar with redirect tracing, headers, on-page report, and SERP country switching
- Why it matters to SEO Suite:
  - confirms strong demand for lightweight point tools
  - validates your existing Tools surface direction
  - shows AI visibility and content-discovery demand are mainstream
- Suggested SEO Suite mapping:
  - expand point tools
  - add AI visibility later
  - keep generators separate from diagnostics

### 8. Ahrefs Content Gap

- Type:
  - popular feature, not fully free as a full-platform workflow
- Official source:
  - https://ahrefs.com/content-gap
- Notable capabilities:
  - finds keywords competitors rank for that you do not
  - supports multiple competitors
  - overlap-based filtering
- Why it matters to SEO Suite:
  - one of the clearest missing competitive-analysis workflows in the product
- Suggested SEO Suite mapping:
  - `Content Gap` under Rankings
  - or a later competitor-oriented tool/workspace

### 9. Ahrefs GSC Insights

- Type:
  - product feature
- Official source:
  - https://ahrefs.com/gsc-insights
- Notable capabilities:
  - multi-profile GSC view
  - more historical data
  - device splits
  - CTR vs position
  - anonymous query fill-in
  - decay detection
  - cannibalization clues
- Why it matters to SEO Suite:
  - strong benchmark for what users now expect from “Search Console insights”
- Suggested SEO Suite mapping:
  - improve derived GSC reporting, not just raw data retrieval
  - split planning into baseline vs enriched insight layers

### 10. Semrush Free Tools

- Type:
  - free public tool collection
- Official source:
  - https://www.semrush.com/free-tools
  - https://www.semrush.com/features/
- Notable free capabilities:
  - SEO Checker
  - Website Authority Checker
  - keyword tools
  - keyword search volume checker
  - keyword rank checker
  - traffic / competitor checks
  - AI visibility tooling
  - AI writing tools
- Why it matters to SEO Suite:
  - confirms demand for low-friction public-style utilities
  - supports the strategy of growing the Tools surface carefully
- Suggested SEO Suite mapping:
  - more single-page diagnostics
  - AI visibility reporting later

### 11. Screaming Frog SEO Spider Free Tier

- Type:
  - free desktop tier
- Official source:
  - https://www.screamingfrog.co.uk/seo-spider/
  - https://www.screamingfrog.co.uk/seo-spider/pricing/
  - https://www.screamingfrog.co.uk/seo-spider/user-guide/tabs/
- Notable free capabilities:
  - crawl up to 500 URLs for free
  - broken link and redirect discovery
  - title/meta analysis
  - robots and hreflang review
  - XML sitemap generation
- Notable paid/advanced benchmark features:
  - structured data validation
  - Search Console integration
  - PageSpeed integration
  - custom extraction
  - JS rendering
  - accessibility auditing
- Why it matters to SEO Suite:
  - best benchmark for crawl-centric sitemap and orphan-page reporting
  - especially relevant to Crawl Access, On-Page SEO, and XML Sitemap workflows
- Suggested SEO Suite mapping:
  - `Sitemap Audit`
  - orphan URL detection
  - URLs not in sitemap
  - non-indexable URLs in sitemap

## Best Free-Tool Opportunities By SEO Suite Surface

### Use cases

- On-Page SEO:
  - rich results visibility, schema feedback loops, and stronger snippet-quality guidance
- Site Health:
  - stronger security/header guidance and clearer technical trust summaries
- Performance:
  - better performance opportunity framing, issue grouping, and trend/history views
  - good candidate for Groq-generated fix briefs and stakeholder-friendly explanations
- Search Console:
  - baseline GSC opportunity layer
  - should be treated as a primary insight workspace, not just an API-backed report
  - good candidate for Groq-generated summaries of winners, losers, and next actions
- Crawl Access:
  - sitemap intelligence and safer `robots.txt` diagnostics
- Authority:
  - later bridge into reclamation and verified-site style backlink workflows
- Rankings:
  - future bridge toward content gap and richer keyword discovery
  - Groq can later help cluster keyword themes after the underlying data is collected
- New use case candidate:
  - Bing Visibility

### Tools

- Rich Results / Schema Validation UI
- IndexNow Submission Tool
- Trend Explorer
- SERP Preview:
  - consider richer social/mobile snippet comparison later
  - Groq can suggest alternate title and description variants
- Redirect Chain:
  - strong supporting tool for Crawl Access and Site Health
- HTTP Headers:
  - strong supporting tool for Site Health and Performance
- Keyword Research:
  - useful bridge into Rankings and Search Console opportunity workflows
  - Groq can later group keywords into content themes or draft angle suggestions

### Generators

- keep current generators focused on output creation
- pair Schema Markup with validation, but do not merge the two
- pair XML Sitemap generation with future Sitemap Audit, but do not collapse them into one panel
- add validator/tester companions only after the current fetch-safety blockers are fixed
- use generators to support Search Console and Performance outcomes:
  - Schema Markup supports richer snippets
  - Meta Tags supports CTR and snippet quality
  - XML Sitemap and robots.txt support crawl/indexing workflows
  - Groq can help draft Schema Markup field content and meta-tag copy, but should not replace deterministic validation

### Login and logout

- Login should evolve into a clearer “connected accounts” entry point for:
  - Google Search Console
  - Bing Webmaster Tools
  - Moz
  - DataForSEO
  - future providers
- Logout should remain simple, but auth state should become easier to understand for users managing multiple integrations

### Groq AI suggestion

- Official docs indicate Groq provides an OpenAI-compatible API and Responses API, which lowers integration friction for optional AI-assist features.
- Best fit in SEO Suite:
  - Search Console summaries
  - Performance remediation explanations
  - On-page rewrite suggestions
  - SERP and meta variant drafting
  - schema copy assistance
  - audit remediation summaries
- Avoid using Groq as the system of record for:
  - crawl results
  - status codes
  - sitemap inclusion
  - Search Console metrics
  - performance metrics

## Highest-Value Additions

1. Bing Visibility workspace
2. IndexNow submission tool
3. Rich Results / Schema Validation UI
4. Sitemap Audit
5. Trend Explorer
6. Baseline GSC opportunity layer
7. Performance opportunity layer
8. Content Gap

## Notes

- Before adding more fetch-heavy tools, fix the existing SSRF gaps in sitemap fetching and schema validation.
- The current hidden backend route for schema validation should be exposed only after the redirect-safety issue is fixed.
- Some popular “free tools” are free public tools, while others are free tiers with limits. Keep that distinction clear in product planning.
- The strongest free-tool expansion path for SEO Suite is across use cases and tools, not by adding more generators first.
- Search Console and Performance should be treated as the two most important ongoing improvement surfaces.
