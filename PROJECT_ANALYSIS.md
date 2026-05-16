# SEO Suite v2.0.0 — Comprehensive Project Analysis

## Executive Summary

**SEO Suite** is a production-grade Python/Flask web application for comprehensive SEO auditing and Google indexing verification. It combines real-time browser automation (Playwright) with Google APIs (PageSpeed, Search Console) and third-party services (SerpAPI, DataForSEO, Moz) to provide a multi-phase SEO audit system. The project ships as a live dashboard with real-time progress streaming, HTML/Excel/CSV reporting, profiles, scheduling, and notifications.

---

## 1. Project Purpose & Architecture

### Core Vision
- **Indexing Verification**: Verify which URLs are indexed in Google using a real headless browser with stealth mode, proxy rotation, and manual crawling fallback
- **Comprehensive SEO Audit**: 4-phase audit system evaluating technical, performance, search console, and authority metrics  
- **Multi-tenant Operational Tool**: Live dashboard with cancel/pause/resume, profiles, bulk operations, and scheduled checks
- **Report Generation**: HTML, Excel, CSV, and PDF outputs with charts, trends, and comparisons

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Browser UI (Jinja2 HTML/JS + CSS Dark Mode)               │
│  ├─ Indexing Checker Panel                                 │
│  ├─ SEO Audit Runner                                       │
│  ├─ Reports Dashboard + Comparisons                        │
│  ├─ Profiles & Settings                                    │
│  └─ Quick Tools (SERP Preview, Redirects, etc.)           │
└────────────────────┬────────────────────────────────────────┘
                     │ JSON API + SSE Streaming
┌────────────────────▼────────────────────────────────────────┐
│  Flask Web Server (app/server.py)                           │
│  ├─ Session-based authentication                           │
│  ├─ 30+ REST/SSE routes                                    │
│  ├─ SSRF protection (validate_public_url)                 │
│  ├─ File upload handling                                   │
│  └─ Real-time event broadcasting to N subscribers          │
└────────────────────┬────────────────────────────────────────┘
                     │
      ┌──────────────┼──────────────┐
      │              │              │
      ▼              ▼              ▼
┌─────────────┐ ┌──────────────┐ ┌──────────────┐
│ Indexing    │ │ SEO Audit    │ │ Quick Tools  │
│ Checker     │ │ Orchestrator │ │ (Phase A)    │
│ (Playwright)│ │ (Phases 1-4) │ │              │
└──────────┬──┘ └──────┬───────┘ └──────┬───────┘
           │           │                │
      ┌────┴────┬──────┴────────┬───────┴─────┐
      │         │               │             │
      ▼         ▼               ▼             ▼
  Phase 1   Phase 2         Phase 3      Phase 4
  (Free)    (Google API)    (GSC API)    (3rd-party)
  ├─Robots  ├─PageSpeed    ├─Clicks    ├─Backlinks
  ├─HTTP    ├─Mobile       ├─Position  ├─DA (Moz)
  ├─Meta    ├─Crawlability ├─Queries   └─Rankings
  ├─H1-H3   └─TTFB         └─Coverage
  ├─Images
  ├─Links
  ├─Schema
  └─SSL
```

---

## 2. Key Modules & Responsibilities

### 2.1 Entry Point & Web Server

#### **main.py** — Application Launcher
```python
if __name__ == "__main__":
    host = os.environ.get("SEO_SUITE_HOST", "127.0.0.1")
    port = int(os.environ.get("SEO_SUITE_PORT", "8080"))
    app.run(host=host, port=port, debug=False, threaded=True)
```
- Minimal bootstrap entry point
- Binds to `localhost:8080` by default (SSRF-safe)
- Respects environment variable overrides for host/port

#### **app/server.py** — Flask Application (1200+ lines)
**Responsibilities**:
- HTTP request routing and response generation
- Real-time event streaming (SSE) for indexing and audit progress
- Authentication (session-based, optional via `SEO_SUITE_PASSWORD_HASH`)
- SSRF validation on all user-provided URLs
- File upload handling with sanitization
- Report CRUD operations (list, download, delete, compare)
- Settings/profiles management with atomic config updates
- Concurrency management (thread-safe queues, locks, semaphores)

**Key Route Groups**:
1. **Auth** (`/login`, `/logout`)
2. **Indexing** (`/api/index/run`, `/api/index/stream`, `/api/index/cancel`, `/api/index/pause`, `/api/index/retry`, `/api/index/partial_export`)
3. **Auditing** (`/api/audit/run`, `/api/audit/stream`, `/api/audit/cancel`, `/api/audit/pause`)
4. **Reports** (`/api/reports`, `/api/open/<filename>`, `/api/download/<filename>`, `/api/reports/delete`, `/api/compare`, `/api/reports/summary`, `/api/reports/preview`)
5. **Settings & Profiles** (`/api/settings`, `/api/profiles`)
6. **File Upload** (`/api/upload`)
7. **Use-Case Runner** (`/api/usecase/run`, `/api/usecase/run_bulk`)
8. **Quick Tools** (`/api/tools/serp_preview`, `/api/tools/redirect_chain`, etc.)

**Concurrency Model**:
- Indexing and audit runs spawn background threads
- SSE subscribers collect in per-run queues for real-time progress
- Global locks protect `_index_status`, `_audit_status` from concurrent writes
- Partial results capped at `MAX_AUDIT_RESULTS = 5000` to prevent OOM on huge sitemaps

**SSRF Protection**:
- All user URLs validated through `validate_public_url()` before processing
- Rejects localhost, RFC1918 private ranges, metadata service addresses
- Every redirect hop re-validated in `safe_requests_get()` and `safe_requests_head()`

---

### 2.2 Core Modules (core/)

#### **core/auth.py** — Session Authentication
- **Optional activation**: Only when `SEO_SUITE_PASSWORD_HASH` is set in environment
- **Session config**: HTTPONLY, SAMESITE=Lax, optional SECURE cookie
- **Credential validation**: Werkzeug password hashing (bcrypt-safe)
- **Decorator**: `@login_required` for routes; returns 401 JSON for API calls, redirects for browsers

#### **core/security.py** — SSRF & HTML Escaping
**Public API**:
- `esc()` — HTML-escape user data for safe report interpolation
- `is_safe_url(url)` → `(bool, reason)` — SSRF check
- `validate_public_url(url)` → `url | raises ValueError` — strict validator
- `filter_public_urls(urls)` → filtered list
- `safe_requests_get/head()` — requests wrappers that re-validate every redirect hop

**SSRF Blocklist**:
- Private IPs: RFC1918, link-local, loopback, multicast, reserved, unspecified
- Metadata: `169.254.169.254`, `metadata.google.internal`, `metadata`
- Hostnames: `localhost`, `*.localhost`

#### **core/checker.py** — Indexing Checker (Playwright)
**Key Functions**:
- `fetch_sitemap_urls(url, _depth, _seen)` — Recursive sitemap parsing with loop detection; handles XML parse failures gracefully
- `fetch_from_domain(domain)` — Auto-detect sitemap at common paths
- `crawl_site(start_url, max_pages, max_depth)` — BFS crawl with internal link following
- `load_from_csv_excel(path)` — CSV/XLSX URL extraction with SSRF filtering
- `execute_and_save(urls, headless, quiet, progress_cb)` — Main indexing orchestrator

**Indexing Workflow**:
1. Fetch URL list (sitemap, domain, CSV, pasted list, or multi-source)
2. Apply pattern filter (regex URL matching)
3. Spawn N parallel Playwright tabs (configurable, default 1)
4. For each URL: navigate with stealth mode, wait for indexing dialog, capture verdict
5. Vendor verdicts: **Indexed** | **Not Indexed** | **Error** | **Timeout** | **Crawl Blocked**
6. Save HTML report (sortable table with charts)
7. Generate comparison vs. previous run (URL-level score deltas)
8. Broadcast progress via SSE to all subscribers

**Browser Automation**:
- Uses Playwright headless Chromium with stealth plugin (reduces CAPTCHA blocking)
- Configurable timeout, delay, rate-limit breaks per `config.json`
- Proxy rotation support via `config.proxies`
- Logs to `data/progress/<hash>.json` for resume capability

#### **core/seo_audit.py** — Audit Orchestrator
**Key Definitions**:
- **USE_CASES**: 7 named runners (Crawlability, On-Page, Site Health, Performance, Search Console, Authority, Rankings)
- **TASKS**: 40+ granular checks across 4 phases
- **score_calc**: Weighted aggregate across pass/warning/fail counts

**Main Entry Point**: `audit_single_url(url, cfg, gsc_service, use_cases, tasks, keywords)`
**Output Structure**:
```python
{
    "url": str,
    "score": int (0-100),
    "issues": [{"label": str, "message": str}, ...],
    "warnings": [...],
    "results": [
        {
            "url": str,
            "tool": str,         # e.g., "robots", "pagespeed_mobile"
            "status": str,       # "pass", "warning", "fail", "error"
            "value": any,        # numeric score, string, or dict
            "message": str,
            "details": dict,
        },
        ...
    ],
    "counts": {
        "crawlability": {"pass": 5, "warning": 0, "fail": 0},
        "on_page": {...},
        ...
    }
}
```

#### **core/report_generator.py** — Report Output
- **HTML Reports**: Jinja2 template rendering with charts (Chart.js)
- **Excel Reports**: openpyxl with styled worksheets (Summary, Detailed, Issues)
- **CSV Export**: Tabular dump for spreadsheet import
- **Comparison**: DataFrame-based URL-level deltas

#### **core/sitemap_parser.py** — Sitemap Parsing
- Handles standard `sitemap.xml` and `sitemap_index.xml`
- Recursive fetching with depth limit (max 5) and cycle detection
- Fallback XML parsers: stdlib ET → lxml → regex regex extraction (resilience)

#### **core/notifier.py** — Email/Slack/Teams Alerts
- **Email**: SMTP with HTML body support
- **Slack**: Webhook POST with message formatting
- **Teams**: Webhook POST with adaptive card format
- Configurable per `config.json`; graceful failure if disabled

#### **core/version.py** — Single Source of Truth
```python
VERSION = "2.0.0"
CLI_BANNER = f"SEO Suite v{VERSION}"
```

---

### 2.3 Tools Modules (tools/)

#### **tools/phase1.py** — Free Technical/On-Page Checks (15 tools)

| # | Tool | Input | Output |
|---|------|-------|--------|
| 1 | Robots.txt Checker | URL | Allow/disallow rules parsed |
| 2 | HTTP Status | URL | Status code, redirects |
| 3 | Redirect Checker | URL | Chain of hops with latency |
| 4 | Canonical URL | URL | Canonical tag present/valid |
| 5 | Title Tag | URL | Length, presence, warnings |
| 6 | Meta Description | URL | Length, presence, warnings |
| 7 | H1-H3 Headings | URL | Count, structure validation |
| 8 | Image Alt Text | URL | % images with alt, list of missing |
| 9 | Word Count | URL | Total words, readability score |
| 10 | Broken Links | URL | 404s and redirect chains |
| 11 | Internal Links | URL | Count by type, depth analysis |
| 12 | XML Sitemap | URL | Validity, size, coverage |
| 13 | Schema Markup | URL | JSON-LD, microdata detection |
| 14 | Hreflang | URL | Language tag validation |
| 15 | TTFB | URL | Time to first byte (seconds) |

**Key Implementation Pattern**:
```python
def result(url, tool, status, value, message, details=None):
    return {"url": url, "tool": tool, "status": status,
            "value": value, "message": message, "details": details or {}}
```
- Caching: 30-min TTL for page fetches, 60-min for robots.txt
- Safe HTTP: All requests via `safe_requests_get()` with SSRF hop validation
- Parallel: ThreadPoolExecutor for multi-URL checks within a single tool

#### **tools/phase2.py** — Google PageSpeed + Mobile Checks

| # | Tool | API | Output |
|---|------|-----|--------|
| 16 | PageSpeed Mobile | PageSpeed Insights | Score (0-100) + Core Web Vitals |
| 17 | PageSpeed Desktop | PageSpeed Insights | Desktop score + metrics |
| 18 | Mobile-Desktop Gap | PageSpeed Insights | Comparative analysis |
| 19 | Crawlability (GSC API) | GSC URL Inspection | Google's indexation verdict |

**Metrics Extracted**:
- Performance score
- Largest Contentful Paint (LCP)
- Cumulative Layout Shift (CLS)
- First Input Delay (FID) / Interaction to Next Paint (INP)
- Total Blocking Time (TBT)
- First Contentful Paint (FCP)
- Speed Index

**Thresholds** (configurable in `config.json`):
```json
{
  "pagespeed_pass": 90,    // Green if ≥ 90
  "pagespeed_warn": 50,    // Yellow if ≥ 50
  "mobile_pass": 70,
  "mobile_warn": 50
}
```

#### **tools/phase3.py** — Google Search Console Analytics

| # | Tool | API | Output |
|---|------|-----|--------|
| 20 | Clicks & Impressions | GSC searchanalytics | CTR, position, trend |
| 21 | Average Position | GSC searchanalytics | Trending position over 90 days |
| 22 | Top Queries | GSC searchanalytics | Query list with clicks/impressions |
| 23 | Coverage Status | GSC coverage | Index vs. excluded/error pages |

**Data Window**: 90 days (configurable)

#### **tools/phase4.py** — Third-Party Authority APIs

| # | Tool | Provider Options | Output |
|---|------|------------------|--------|
| 25 | Backlink Count | DataForSEO (preferred) | Backlinks, referring domains, rank |
| 26 | Domain Authority | Moz (free tier) | DA/100, PA/100 scores |
| 27 | Keyword Rankings | SerpAPI or DataForSEO | Rank position per keyword, top 10/3 count |
| 28 | Competitor Comparison | SerpAPI SERP scraping | Competitor list for same keyword |

**API Graceful Degradation**:
- If no API keys configured → returns `"warning"` status with setup instructions
- Fast-fail on 429 (rate limit), with backoff on 5xx
- Supports parallel requests with ThreadPoolExecutor

#### **tools/quick_tools.py** — Lightweight Single-URL Tools (6 tools)

| Tool | Purpose |
|------|---------|
| SERP Snippet Preview | Title/meta/OG/Twitter preview with char count warnings |
| Redirect Chain | Trace all hops with status codes and latency |
| HTTP Headers | Extract cache, GZIP, security headers |
| Keyword Density | % frequency of target keyword in body |
| Code-to-Text Ratio | HTML vs. text bytes |
| GZIP & Cache Headers | Compression and caching directive validation |

**No API Dependencies**: All tools use requests + BeautifulSoup for local analysis.

#### **tools/generators.py** — Output Generation Tools

| Tool | Output |
|------|--------|
| robots.txt Generator | Template with allow/disallow rules |
| XML Sitemap Generator | `<urlset>` from URL list |
| Hreflang Tag Generator | HTML snippet for multi-language sites |
| Meta Tag Generator | Standard SEO meta tags |
| Schema Markup Generator | JSON-LD structured data templates |

#### **tools/keyword_research.py** — DataForSEO Keyword API

**Modes**:
- **auto**: Try related keywords → suggestions → ideas until useful coverage
- **related**: Similar keywords
- **suggestions**: Autocomplete suggestions
- **ideas**: Broad keyword ideas with search volume

**Output Structure**:
```python
{
    "keyword": str,
    "search_volume": int,
    "avg_monthly_searches": [{year, month, searchVolume}],
    "cpc": float,
    "difficulty": int,
    "intent": "informational|commercial|transactional|navigational",
}
```

#### **tools/schema_validator.py** — JSON-LD Validator
- Validates schema.org JSON-LD markup
- Checks for required properties per schema type
- Flags warnings for incomplete markup

---

## 3. Dependencies & Versions

### Core Framework
- **Flask** 3.1.3 — Web framework
- **Werkzeug** (shipped with Flask) — Password hashing, secure filename handling

### Browser Automation
- **Playwright** 1.59.0 — Chromium headless control
- **playwright-stealth** 1.0.6 — Anti-CAPTCHA obfuscation

### HTTP & Parsing
- **requests** 2.33.1 — Synchronous HTTP client
- **httpx** 0.27.2 (with http2) — Alt HTTP client with HTTP/2 support
- **beautifulsoup4** 4.14.3 — HTML parsing
- **lxml** 6.0.3 — Fast XML/HTML parsing
- **html5lib** 1.1 — HTML5 parser fallback

### Data & Reports
- **pandas** 2.2.3 — DataFrame operations
- **openpyxl** 3.1.5 — Excel generation with formatting
- **jinja2** (shipped with Flask) — Template rendering

### Google APIs
- **google-api-python-client** 2.195.0 — PageSpeed, Search Console
- **google-auth** 2.50.0 — OAuth2 authentication
- **google-auth-httplib2** 0.3.1 — Transport layer

### Third-Party Integrations
- **textstat** 0.7.3 — Readability metrics
- **python-whois** 0.9.4 — WHOIS data fetching
- **dnspython** 2.7.0 — DNS lookups (SPF, DMARC, MX)
- **tldextract** 5.1.3 — TLD parsing
- **cachetools** 5.5.2 — LRU/TTL caching
- **waybackpy** 3.0.6 — Wayback Machine API

### Task Scheduling
- **schedule** 1.2.2 — Simple task scheduling
- **APScheduler** 3.10.4 — Advanced scheduling

### CLI & Config
- **python-dotenv** 1.2.2 — `.env` file loading
- **colorama** 0.4.6 — Colored terminal output
- **tqdm** 4.67.3 — Progress bars

### Production Server
- **waitress** 3.0.2 — WSGI server (alternative to Flask dev server)

### Developer Tools
- **ruff** — Linting (100-char line length)
- **mypy** — Type checking (strict optional, ignore missing imports)
- **pytest** — Testing framework

**Python Version**: 3.10+ (requires match statements, positional-only params)

---

## 4. Data Flow: Input → Processing → Output

### 4.1 Indexing Checker Flow

```
User Input (Browser)
    │
    ├─ Input Type: Sitemap URL | Domain | CSV | Pasted List | Multi-Source
    ├─ Filter Pattern: (optional regex)
    ├─ Limit: 1-500 URLs
    ├─ Settings: Parallel tabs, headless, stealth mode
    │
    ▼
POST /api/index/run → HTTP 200 + {total, started}
    │
    ├─ Spawn Background Thread
    │   │
    │   ├─ Fetch URL List
    │   │   ├─ fetch_sitemap_urls()   → recursive XML parsing
    │   │   ├─ fetch_from_domain()    → auto-detect + fetch
    │   │   ├─ load_from_csv_excel()  → extract URLs
    │   │   ├─ _safe_public_url_list() → validate each URL
    │   │   └─ filter_urls(pattern)   → apply regex filter
    │   │
    │   ├─ Apply Limit + SSRF Check
    │   │   └─ validate_public_url() on each URL
    │   │
    │   ├─ Initialize Playwright
    │   │   ├─ sync_playwright()
    │   │   ├─ browser.new_context() × N (parallel_tabs)
    │   │   └─ stealth_sync() per page
    │   │
    │   ├─ For Each URL (parallel)
    │   │   ├─ page.goto(url, timeout=20s)
    │   │   ├─ Wait for Google indexing dialog / network idle
    │   │   ├─ Capture verdict text: "Indexed" | "Not Indexed" | etc.
    │   │   └─ progress_cb(num, total, url, status) → broadcast SSE
    │   │
    │   ├─ Aggregate Results
    │   │   ├─ Status counts (Indexed, Not Indexed, Error, Timeout)
    │   │   ├─ Calculate indexation rate %
    │   │   └─ Load previous run for comparison (if do_compare=True)
    │   │
    │   └─ Generate Reports
    │       ├─ HTML: sortable table, charts (Chart.js), filter controls
    │       ├─ CSV: rows with URL, status, date checked
    │       └─ (optional) Comparison: {url, prev_status, new_status, delta}
    │
    ├─ SSE Stream: subscribe_index_stream()
    │   └─ Receives events: {type: "progress", num, total, url, status}
    │                       {type: "done", report, error_count}
    │                       {type: "error", message}
    │
    ├─ User Controls (during run)
    │   ├─ Cancel    → set _index_cancel event → graceful shutdown
    │   ├─ Pause     → clear _index_paused event → block at cb()
    │   ├─ Resume    → set _index_paused event → unblock
    │   └─ Partial Export → snapshot _last_index_run dict → CSV
    │
    └─ Report Saved to data/reports/indexing_report_<timestamp>.[html|csv]

GET /api/reports
    └─ Returns list of all report files with metadata
```

**State Machine During Indexing**:
```
START
  ↓
[Running] ← (cancel button clicked) → [Cancelled] → Save Partial Report
  ↓ (pause button clicked)
[Paused] ← ← ← (resume button clicked)
  │        ↑
  └────────┘
  ↓ (finish)
[Complete] → Generate Full Report → Broadcast "done" event
```

---

### 4.2 SEO Audit Flow

```
User Input (Browser)
    │
    ├─ Input Type: Sitemap | Domain | Crawl | CSV | Pasted List
    ├─ Use Cases: [crawlability, on_page, site_health, performance, ...]
    ├─ Keywords: (for rank tracking)
    ├─ Limit: 1-500 URLs
    ├─ Workers: 1-8 (parallel audit threads)
    │
    ▼
POST /api/audit/run → HTTP 200 + {total, started, workers}
    │
    ├─ Spawn Background Thread
    │   │
    │   ├─ Fetch & Filter URLs (same as indexing)
    │   │
    │   ├─ (optional) GSC Data Fetch
    │   │   └─ build_gsc_service() → if GSC enabled
    │   │       └─ p3_site(gsc_service, site_url, urls[:5]) → site-level metrics
    │   │
    │   ├─ ThreadPoolExecutor(max_workers=N)
    │   │   │
    │   │   ├─ For Each URL (parallel)
    │   │   │   │
    │   │   │   └─ audit_single_url(url, cfg, gsc_service, use_cases, tasks, keywords)
    │   │   │       │
    │   │   │       ├─ Phase 1 Checks (free tools)
    │   │   │       │   ├─ fetch_page(url) → cache hit/miss
    │   │   │       │   ├─ parse robots.txt
    │   │   │       │   ├─ check HTTP status
    │   │   │       │   ├─ extract meta tags
    │   │   │       │   ├─ count images, headings, links
    │   │   │       │   ├─ validate schema.org
    │   │   │       │   └─ [15 total tools]
    │   │   │       │
    │   │   │       ├─ Phase 2 Checks (PageSpeed API)
    │   │   │       │   ├─ pagespeed_check(url, "mobile") → {score, LCP, CLS, ...}
    │   │   │       │   ├─ pagespeed_check(url, "desktop") → compare gap
    │   │   │       │   └─ (optional) GSC URL Inspection → crawlability
    │   │   │       │
    │   │   │       ├─ Phase 3 Checks (GSC API, if enabled)
    │   │   │       │   ├─ clicks_impressions(url, gsc_service) → CTR, position
    │   │   │       │   ├─ position_tracker(url) → 90-day trend
    │   │   │       │   ├─ top_queries(url) → keyword performance
    │   │   │       │   └─ coverage_status(url) → indexing state
    │   │   │       │
    │   │   │       └─ Phase 4 Checks (3rd-party APIs)
    │   │   │           ├─ backlink_check(url) → DataForSEO | Ahrefs
    │   │   │           ├─ domain_authority(url) → Moz API
    │   │   │           └─ keyword_rank_tracker(url, keywords) → SerpAPI | DataForSEO
    │   │   │
    │   │   ├─ Collect results → _audit_partial (bounded, live)
    │   │   │                 → _audit_full_results (complete set)
    │   │   │
    │   │   ├─ Broadcast progress: {type: "progress", num, total, url, score, results}
    │   │   │
    │   │   └─ (if cancel flag set) → gracefully exit loop
    │   │
    │   ├─ Aggregate Results
    │   │   ├─ Calculate avg score across all URLs
    │   │   ├─ Count total issues, warnings, passes
    │   │   └─ Identify most common failing tools
    │   │
    │   └─ Generate Multi-Format Reports
    │       ├─ HTML Report: generate_html_report()
    │       │   ├─ Jinja2 template rendering
    │       │   ├─ Per-URL summaries (score, pass/warn/fail counts)
    │       │   ├─ Detailed tool results (status, value, message, details)
    │       │   ├─ Chart.js visualization (score distribution, top issues)
    │       │   └─ Responsive dark-mode friendly styling
    │       │
    │       ├─ Excel Report: generate_excel_report()
    │       │   ├─ Worksheet 1: Summary (one row per URL)
    │       │   ├─ Worksheet 2: Detailed (one row per URL + tool combination)
    │       │   ├─ Conditional formatting (color-coded status)
    │       │   └─ Formula-based score totals
    │       │
    │       ├─ JSON Sidecar: {avg_score, total_issues, total_warnings, urls}
    │       │
    │       └─ Saved to data/reports/seo_audit_<timestamp>.[html|xlsx|json]
    │
    ├─ SSE Stream: subscribe_audit_stream()
    │   └─ Receives events: {type: "progress", num, total, url, score, issues, warnings, results, counts}
    │                       {type: "done", report, xlsx}
    │                       {type: "error", message}
    │
    ├─ User Controls (during run)
    │   ├─ Cancel
    │   ├─ Pause
    │   ├─ Resume
    │   └─ (no partial export for audits)
    │
    └─ (optional) Send Notification
        └─ notifier.notify_all(counts, total, html_path)
            ├─ Email: subject + HTML body with run summary
            ├─ Slack: {text: "Audit complete: X issues found"}
            └─ Teams: {text: "Audit complete: X issues found"}
```

**Per-Check Result Schema**:
```python
{
    "url": "https://example.com/page",
    "tool": "pagespeed_mobile",               # tool identifier
    "status": "pass" | "warning" | "fail" | "error",
    "value": 85,                              # numeric score or data
    "message": "Good performance: 85/100",
    "details": {
        "performance_score": 85,
        "lcp": {"value": "1.8 s", "score": 0.95},
        "cls": {"value": "0.05", "score": 1.0},
        "fid": {"value": "45 ms", "score": 0.50},
    }
}
```

**Score Calculation**:
```python
def calc_seo_score(results: list[dict]) -> int:
    """Weighted aggregate: pass=10pts, warning=5pts, fail=0pts, error=-5pts"""
    total, count = 0, len(results)
    for r in results:
        if r["status"] == "pass":      total += 10
        elif r["status"] == "warning": total += 5
        elif r["status"] == "fail":    total += 0
        elif r["status"] == "error":   total -= 5
    return max(0, min(100, round(total / count * 10))) if count else 0
```

---

### 4.3 Quick Tools Flow (Single URL Analysis)

```
User Input → /api/tools/<tool_name>
    │
    ├─ Input: URL + optional parameters
    ├─ Validate: _reject_unsafe(url) → SSRF check
    │
    ├─ Tool-Specific Processing
    │   │
    │   ├─ SERP Snippet Preview
    │   │   ├─ safe_requests_get(url)
    │   │   ├─ BeautifulSoup parse
    │   │   ├─ Extract title, meta desc, OG tags, Twitter card
    │   │   └─ Return {url, title, title_len, desc, desc_len, og, twitter, warnings}
    │   │
    │   ├─ Redirect Chain
    │   │   ├─ Manual hop-by-hop following (no auto-redirect)
    │   │   ├─ Measure latency per hop
    │   │   └─ Return [{url, status, latency, final_url}]
    │   │
    │   ├─ HTTP Headers
    │   │   ├─ safe_requests_head(url)
    │   │   ├─ Parse cache, GZIP, security headers
    │   │   └─ Return {cache_control, gzip, x-frame-options, etc.}
    │   │
    │   ├─ Keyword Density
    │   │   ├─ Fetch page, extract text
    │   │   ├─ Count keyword occurrences
    │   │   └─ Return {keyword, count, density_pct}
    │   │
    │   ├─ Code-to-Text Ratio
    │   │   ├─ Fetch raw HTML
    │   │   ├─ Strip tags, measure bytes
    │   │   └─ Return {html_bytes, text_bytes, ratio_pct}
    │   │
    │   └─ GZIP & Cache
    │       ├─ safe_requests_head()
    │       ├─ Parse cache-control, etag, gzip encoding
    │       └─ Return {gzip_enabled, cache_ttl, etag, varies, etc.}
    │
    └─ Response: {ok: true, ...tool_specific_data}  or  {ok: false, error: "..."}
```

---

### 4.4 Configuration & Secrets Flow

```
┌─ config.json (non-secret settings, committed)
│  ├─ parallel_tabs: 1
│  ├─ gsc.enabled, gsc.credentials_file
│  ├─ email.enabled, email.smtp_host, email.smtp_port, email.smtp_from, email.smtp_user
│  ├─ slack.enabled, slack.webhook_url
│  ├─ teams.enabled, teams.webhook_url
│  ├─ schedule.enabled, schedule.interval, schedule.time, schedule.sitemap_url, schedule.limit
│  ├─ priority.high_value_patterns, priority.low_value_patterns
│  ├─ track_keywords: []
│  ├─ timings: {sitemap_fetch_timeout_secs, browser_page_timeout_ms, rate_limit_break_*}
│  ├─ thresholds: {pagespeed_pass, pagespeed_warn, mobile_pass, ctr_warn_pct}
│  ├─ proxies: []
│  └─ (empty stubs for API keys)
│
└─ Environment Variables (secrets, never committed)
   ├─ PAGESPEED_API_KEY       → config.pagespeed_api_key
   ├─ SERPAPI_KEY             → config.serpapi_key
   ├─ MOZ_ACCESS_ID           → config.moz_access_id
   ├─ MOZ_SECRET_KEY          → config.moz_secret_key
   ├─ DATAFORSEO_LOGIN        → config.dataforseo_login
   ├─ DATAFORSEO_PASSWORD     → config.dataforseo_password
   │
   ├─ SEO_SUITE_HOST          → Flask bind address (default: 127.0.0.1)
   ├─ SEO_SUITE_PORT          → Flask port (default: 8080)
   ├─ SEO_SUITE_PASSWORD_HASH → enable auth (if set)
   ├─ SEO_SUITE_USERNAME      → auth username (default: admin)
   ├─ SEO_SUITE_SECRET        → Flask session secret (auto-generated if not set)
   ├─ SEO_SUITE_COOKIE_SECURE → require HTTPS cookies (default: 0)
   └─ CORS_ALLOWED_ORIGINS    → CORS whitelist (default: localhost:8080)

load_config() in core/checker.py:
    1. Load config.json
    2. Overlay all env vars matching _env_keys dict
    3. Return merged dict to app/server.py and tools
```

**Static vs. Dynamic Config**:
- **Static** (`config.json`): Loaded once at app startup
- **Dynamic** (`/api/settings POST`): Updated in-memory + persisted to disk
  - Only whitelisted keys allowed (_SETTINGS_ALLOWED_KEYS)
  - Update triggers reload of global CFG variable across all modules

---

## 5. File Organization

```
SEO Suite/
├── main.py                          ← Entry point
├── dashboard.py                     ← (legacy, use main.py instead)
├── config.json                      ← Configuration template
├── pyproject.toml                   ← Project metadata + tool config
├── requirements.txt                 ← Pinned dependencies
│
├── app/
│   ├── __init__.py                  ← create_app() factory
│   ├── server.py                    ← Flask app + 30+ routes
│   ├── routes/ (reserved for future blueprint splits)
│   ├── templates/
│   │   └── dashboard.html           ← Single-page app (HTML/JS)
│   └── static/
│       ├── css/
│       │   └── dashboard.css        ← Dark-mode responsive styling
│       └── js/
│           └── dashboard.js         ← UI logic, SSE streaming, AJAX
│
├── core/
│   ├── __init__.py
│   ├── auth.py                      ← Session authentication
│   ├── checker.py                   ← Indexing orchestrator (Playwright)
│   ├── security.py                  ← SSRF + HTML escaping
│   ├── seo_audit.py                 ← Audit orchestrator, USE_CASES registry
│   ├── report_generator.py          ← HTML/Excel/CSV/PDF report generation
│   ├── sitemap_parser.py            ← Recursive sitemap fetching
│   ├── notifier.py                  ← Email/Slack/Teams alerts
│   └── version.py                   ← VERSION constant
│
├── tools/
│   ├── __init__.py
│   ├── phase1.py                    ← 15 free technical checks
│   ├── phase2.py                    ← PageSpeed + mobile friendliness
│   ├── phase3.py                    ← GSC analytics (clicks, position, queries)
│   ├── phase4.py                    ← Third-party API checks (backlinks, DA, rankings)
│   ├── quick_tools.py               ← SERP preview, redirects, headers, etc.
│   ├── generators.py                ← Output generators (robots.txt, sitemap, etc.)
│   ├── keyword_research.py          ← DataForSEO keyword API wrapper
│   └── schema_validator.py          ← JSON-LD validation
│
├── tests/
│   ├── __init__.py
│   ├── test_checker.py
│   ├── test_keyword_research.py
│   ├── test_phase4.py
│   ├── test_quick_tools.py
│   ├── test_review_fixes.py
│   ├── test_security_fixes.py
│   └── test_server.py
│
└── data/ (runtime outputs, not committed)
    ├── history.json                 ← Trend data (indexed vs. not-indexed over time)
    ├── profiles.json                ← Saved audit configurations
    ├── progress/                    ← Mid-run state for resume capability
    │   └── <hash>.json
    ├── reports/                     ← Generated reports
    │   ├── indexing_report_<ts>.[html|csv]
    │   └── seo_audit_<ts>.[html|xlsx|json]
    └── uploads/                     ← User-uploaded CSV/XLSX files
        └── <ts>_<filename>
```

---

## 6. Key Implementation Highlights

### 6.1 SSRF Protection (Defense in Depth)

1. **Input Validation**: Every user-provided URL passes through `validate_public_url()`
   - Blocks localhost, RFC1918, link-local, metadata addresses
   - Resolves DNS and validates resolved IPs

2. **Redirect Validation**: `safe_requests_get/head()` re-validate every redirect hop
   - Prevents public URL → private URL bounces

3. **Config Allowlist**: POST `/api/settings` only accepts whitelisted keys
   - Prevents injection of arbitrary file paths or URLs

4. **Path Traversal Hardening**: All report downloads validated via `_safe_report_path()`
   - Regex matches known patterns
   - `Path.resolve()` + `relative_to()` check

5. **Upload Sanitization**: `secure_filename()` + temporary paths in `data/uploads/`

### 6.2 Concurrency Model

**Thread Safety**:
- Global locks protect shared state: `_lock`, `_index_cancel`, `_audit_cancel`
- Per-run queues: Each SSE client gets independent subscription queue
- Semaphore throttling: PDF generation capped at `_PDF_CONCURRENCY` (default 2)

**Progress Streaming**:
```python
_index_subscribers: list[queue.Queue]  # Each connected client
_index_queue = _BroadcastQueue(...)    # Adapter that puts to all subscribers

def _subscribe(subs):
    q = queue.Queue(maxsize=1000)
    with _sub_lock:
        subs.append(q)
    return q

@app.route("/api/index/stream")
def api_index_stream():
    sub = _subscribe(_index_subscribers)
    def gen():
        while True:
            msg = sub.get(timeout=30)
            yield f"data: {json.dumps(msg)}\n\n"
            if msg.get("type") in ("done", "error"): break
    return Response(gen(), mimetype="text/event-stream")
```

**Partial Results Capping**:
```python
MAX_AUDIT_RESULTS = 5000  # Prevent OOM on 10k-URL sitemaps
if len(_audit_partial) < MAX_AUDIT_RESULTS:
    _audit_partial.append({...})
```

### 6.3 Error Recovery & Resume

**Indexing Resume Capability**:
- During a run, progress saved to `data/progress/<hash>.json`
- If browser crashes or network fails, call `/api/index/retry` to re-run failed URLs
- `_last_index_run` dict tracks per-URL status → can export partial CSV

**Audit Cancellation**:
```python
_audit_cancel.clear()  # Start new audit
# ...
if _audit_cancel.is_set():
    for f in fut_to_url:
        f.cancel()  # Gracefully cancel pending futures
    break
```

### 6.4 Report Generation

**HTML Reports**: Jinja2 templating with Chart.js visualization
- Sortable tables (JavaScript-based)
- Bar/pie charts for score distribution
- Expandable detail rows

**Excel Reports**: openpyxl with styling
- `Summary` sheet: one row per URL with score, pass/warn/fail counts
- `Detailed` sheet: one row per URL + tool with full result object
- Conditional formatting: green (pass), yellow (warning), red (fail)

**Comparison**: DataFrame-based URL-level diffs
- Reads two XLSX files, extracts Summary sheet scores
- Calculates delta per URL, flags improved/declined
- Returns {url, a_score, b_score, delta, added, removed}

---

## 7. Security Considerations

### 7.1 What's Protected

✅ **SSRF Prevention**: `validate_public_url()` on all HTTP requests
✅ **HTML Escaping**: `esc()` function in report generation
✅ **Path Traversal**: `_safe_report_path()`, `_safe_upload_path()` hardening
✅ **Authentication**: Optional session-based login (Werkzeug password hash)
✅ **CORS**: Configurable allowed origins (default: localhost:8080)
✅ **Max Upload Size**: 10 MB cap via Flask config

### 7.2 Design Assumptions

⚠️ **No Multi-Tenant Auth**: Single account per deployment
⚠️ **Local-by-Default**: Binds to `127.0.0.1` (localhost only); requires explicit `SEO_SUITE_HOST=0.0.0.0` for LAN exposure
⚠️ **Trusts Environment Vars**: API keys exposed via env; assume secure deployment environment
⚠️ **No Request Signing**: SSE events not signed; assumes HTTPS on production
⚠️ **Audit Tool Results Unconstrained**: Phase 4 tools (Moz, SerpAPI) trusted; code injection not possible but DoS by huge API responses possible

### 7.3 Recommended Hardening for Production

1. Set `SEO_SUITE_PASSWORD_HASH` in environment
2. Generate strong `SEO_SUITE_SECRET` (32+ chars, random)
3. Enable `SEO_SUITE_COOKIE_SECURE=1` (requires HTTPS)
4. Restrict `CORS_ALLOWED_ORIGINS` to exact client domain
5. Run behind a reverse proxy (nginx, traefik) with rate limiting
6. Use Waitress or Gunicorn instead of Flask dev server
7. Validate input limits (sitemap size, audit URL count) at reverse proxy layer

---

## 8. Testing Strategy

### Test Files (tests/)

| File | Scope |
|------|-------|
| `test_checker.py` | Sitemap parsing, URL fetching, indexing logic |
| `test_keyword_research.py` | DataForSEO keyword API wrapper |
| `test_phase4.py` | Third-party API mocking (Moz, SerpAPI, DataForSEO) |
| `test_quick_tools.py` | SERP preview, redirect chain, headers parsing |
| `test_security_fixes.py` | SSRF validation, HTML escaping, path traversal |
| `test_review_fixes.py` | Regression tests for known bugs |
| `test_server.py` | Flask routes, auth, report CRUD, streaming |

**Pytest Config** (pyproject.toml):
```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = ["test_*.py"]
python_functions = ["test_*"]
addopts = "-v --tb=short"
```

---

## 9. Configuration & Environment Reference

### config.json (Template)

**Key Sections**:

```json
{
  "parallel_tabs": 1,                    // Playwright tabs for indexing (1-8 recommended)
  
  "gsc": {
    "enabled": false,                    // Enable Google Search Console API
    "credentials_file": "gsc_credentials.json"  // OAuth2 service account
  },
  
  "email": {
    "enabled": false,
    "smtp_host": "smtp.gmail.com",
    "smtp_port": 587,
    "smtp_from": "noreply@example.com",
    "smtp_user": "account@gmail.com",
    "smtp_pass": "",                     // Use env var instead
    "to": ["recipient@example.com"]
  },
  
  "slack": {
    "enabled": false,
    "webhook_url": "https://hooks.slack.com/services/..."
  },
  
  "teams": {
    "enabled": false,
    "webhook_url": "https://outlook.office.com/webhook/..."
  },
  
  "schedule": {
    "enabled": false,
    "interval": "daily",                 // "hourly" or "daily"
    "time": "08:00",                     // HH:MM in local time
    "sitemap_url": "https://example.com/sitemap.xml",
    "limit": 100                         // URLs to check per run
  },
  
  "priority": {
    "high_value_patterns": ["/category/", "/course/"],
    "low_value_patterns": ["/tag/", "/author/"]
  },
  
  "track_keywords": [],                  // Keywords to watch in GSC data
  
  "timings": {
    "sitemap_fetch_timeout_secs": 15,
    "crawl_request_timeout_secs": 8,
    "browser_page_timeout_ms": 20000,
    "captcha_wait_secs": 60,
    "rate_limit_break_min_secs": 15,
    "rate_limit_break_max_secs": 25,
    "rate_limit_break_every_n": 10,
    "delay_base_secs": 3.0,
    "delay_max_secs": 15.0,
    "webhook_timeout_secs": 10
  },
  
  "thresholds": {
    "pagespeed_pass": 90,
    "pagespeed_warn": 50,
    "mobile_pass": 70,
    "mobile_warn": 50,
    "ctr_min_impressions": 100,
    "ctr_warn_pct": 2.0,
    "rank_warn_position": 30
  },
  
  "proxies": []                          // List of proxy URLs for indexing
}
```

### Environment Variables (Secrets)

```bash
# API Keys (from config.json payespeed_api_key, etc.)
PAGESPEED_API_KEY=AIza...
SERPAPI_KEY=...
MOZ_ACCESS_ID=...
MOZ_SECRET_KEY=...
DATAFORSEO_LOGIN=...
DATAFORSEO_PASSWORD=...

# Auth
SEO_SUITE_PASSWORD_HASH=$(python -c "from werkzeug.security import generate_password_hash; print(generate_password_hash('your-password'))")
SEO_SUITE_USERNAME=admin
SEO_SUITE_SECRET=<random 32+ char string>
SEO_SUITE_COOKIE_SECURE=0              # Set to 1 for HTTPS production

# Server
SEO_SUITE_HOST=127.0.0.1               # Default; set to 0.0.0.0 for LAN
SEO_SUITE_PORT=8080
CORS_ALLOWED_ORIGINS=http://localhost:8080

# PDF Workers (if using PDF reports)
SEO_SUITE_PDF_WORKERS=2
```

---

## 10. Known Limitations & Future Improvements

### Limitations

1. **Single Account**: No user/project isolation; auth is binary (authed or not)
2. **In-Memory State**: No persistent job queue; restart loses in-flight runs
3. **No Rate Limiting**: No built-in rate limiting (rely on reverse proxy)
4. **API Soft Errors**: Third-party API failures don't abort audit; they return warnings
5. **Large Sitemaps**: 50k+ URL sitemaps untested; memory growth not profiled
6. **PDF Generation**: Spawns Playwright per request; slow compared to HTML/Excel

### Potential Improvements

1. **Task Queue**: Bull, Celery, or RQ for persistent job history
2. **Database**: Replace flat files (history.json, profiles.json) with PostgreSQL/SQLite
3. **Multi-Tenant Auth**: JWT tokens, per-user audit limits, audit history
4. **Caching Layer**: Redis for API response caching, session store
5. **Observability**: Prometheus metrics, structured logging (JSON), distributed tracing
6. **API Rate Limiting**: Sliding window per API key, exponential backoff
7. **Webhook Support**: Outgoing webhooks for audit completion events
8. **CLI Tool**: `seo-suite --config prod.json --run-audit https://example.com`
9. **Dashboard Analytics**: Audit history charts, API usage trends

---

## 11. Code Quality & Standards

### Linting & Formatting
- **Ruff** (100-char line length, selected rules E/W/F/I/UP/B/SIM)
- Exceptions: E501 (long lines), B007 (unused loop vars), SIM108 (ternary)

### Type Checking
- **Mypy** with strict optional, ignore missing imports
- Coverage: `core/`, `tools/`, `app/`
- Optional on imports: `return url | None` style

### Testing
- **Pytest** with `-v --tb=short` output
- Unit tests for security, phase tools, API edge cases
- Integration tests for auth, report generation

### Code Organization
- **Modules**: Single responsibility per file
- **Functions**: <100 lines typical, long functions in checker.py documented
- **Constants**: Uppercase (GREEN, RED, CFG, REPORTS_DIR)
- **Imports**: Organized (stdlib, third-party, local)

---

## 12. Summary of Data Structures

### Audit Result
```python
{
    "url": str,
    "tool": str,              # e.g., "robots", "pagespeed_mobile"
    "status": "pass" | "warning" | "fail" | "error",
    "value": Any,             # Score, count, or dict
    "message": str,           # Human-readable summary
    "details": dict,          # Tool-specific metadata
}
```

### Audit Aggregate
```python
{
    "url": str,
    "score": int (0-100),
    "issues": [{"label": str, "message": str}],
    "warnings": [...],
    "results": [audit_result, ...],
    "counts": {
        "crawlability": {"pass": int, "warning": int, "fail": int},
        "on_page": {...},
        ...
    }
}
```

### Indexing Status
```python
{
    "running": bool,
    "total": int,
    "done": int,
}
```

### Progress Event (SSE)
```python
{
    "type": "progress" | "done" | "error" | "cancelled" | "ping",
    "num": int,        # Current count (progress only)
    "total": int,      # Total count (progress only)
    "url": str,        # Current URL (progress only)
    "status": str,     # Verdict (indexing) or message (other)
    "report": str,     # File path (done only)
    "message": str,    # Error message (error only)
}
```

---

## Conclusion

**SEO Suite** is a production-grade, security-hardened SEO auditing platform combining Playwright automation, Google APIs, and third-party integrations into a cohesive real-time dashboard. The architecture emphasizes safety (SSRF protection, authentication), scalability (concurrent audit workers, bounded result sets), and observability (real-time progress streaming, detailed reports). While designed for single-account deployment, it serves as a solid foundation for multi-tenant SaaS or self-hosted enterprise use.

**Key Strengths**:
- Comprehensive SEO coverage (4 phases, 40+ checks)
- Real-time progress feedback (SSE streaming)
- Multiple output formats (HTML, Excel, CSV, PDF)
- Tight security posture (SSRF, auth, input validation)
- Graceful error handling & partial result recovery

**Architecture is ready for code review** with all entry points, data flows, and security boundaries documented above.
