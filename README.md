# SEO Suite v2.0.0

A comprehensive Python-based SEO audit tool with a live web dashboard.

This repository also includes planning and reference documents for product roadmap and cleanup work:
- `NEW_TOOLS_USECASES.md` — new tool and use case recommendations aligned to the current dashboard and backend routes.
- `REPO_REVIEW_AND_CLEANUP.md` — merged review findings, blockers, and cleanup recommendations for the active codebase.

## Features

- **Indexing Checker** — verify which URLs are indexed in Google using a real browser (Playwright); supports sitemap, domain crawl, CSV/XLSX upload, and pasted URL lists
- **SEO Audit** — 4-phase audit: Technical, Performance, Search Console, Authority & Rankings
- **Use Case Runner** — 7 targeted use cases: Crawl Access, On-Page SEO, Site Health, Performance, Search Console, Authority, Rankings
- **Live Progress** — real-time streaming dashboard for both indexing checks and audits
- **Live Reports Panel** — report counts and file list update automatically after each run; auto-refreshes every 10 s while the Reports panel is open
- **Reports** — HTML, Excel, CSV, and PDF output with charts; bulk delete and delete-all support
- **Profiles** — save and reload named audit configurations (use cases, keywords, URL limit)
- **File Upload** — upload a CSV or XLSX file containing URLs for indexing checks or audits
- **Trend tracking** — indexed vs not-indexed over time (chart)
- **Compare runs** — diff two audit XLSX reports to track score gains/losses per URL
- **Tool Suite** — standalone tools: SERP Preview, Redirect Chain, HTTP Headers, Keyword Density, Code:Text Ratio, GZIP & Cache
- **Generators** — Schema Markup, robots.txt, XML Sitemap, Hreflang Tags, Meta Tags
- **Cancel / Pause / Resume** — full control over any running indexing check
- **Retry errors** — re-run only the URLs that errored in the last indexing check
- **Parallel audit workers** — configurable number of concurrent URL audits (1–8)
- **Notifications** — Email (SMTP), Slack webhook, and Microsoft Teams webhook on run completion
- **Scheduling** — automated checks on a daily/hourly schedule via `config.json`
- **Proxy support** — pass a list of proxy URLs in `config.json`
- **Dark mode** — full dark theme with persistence
- **Website Navigation** — seamless glassmorphic shortcut button to return to the public website home page from the live dashboard
- **Interactive Setup Guides** — step-by-step setup guides for Groq API Key (AI Assistant) and IndexNow Host directly inside the dashboard Help modal
- **Security hardening** — HTTP security headers (CSP, X-Frame-Options, HSTS), CSRF protection on form endpoints, SSRF guards with DNS rebinding mitigation, account lockout after 10 failed logins, CSV formula injection sanitization on uploads, and rate limiting on auth/audit endpoints

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
playwright install chromium
```

### 2. Configure secrets

Copy `.env.example` to `.env` and fill in your API keys:

```bash
cp .env.example .env
```

Edit `.env`:
```
PAGESPEED_API_KEY=AIza...
SERPAPI_KEY=...

# Optional — notifications
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=you@gmail.com
SMTP_PASSWORD=...
EMAIL_FROM=you@gmail.com
EMAIL_TO=recipient@example.com

SLACK_WEBHOOK_URL=https://hooks.slack.com/...
TEAMS_WEBHOOK_URL=https://outlook.office.com/webhook/...
```

### 3. Configure settings

Edit `config.json` for non-secret settings. Key sections:

| Section | Purpose |
|---------|---------|
| `parallel_tabs` | Concurrent Playwright tabs for indexing (default 1) |
| `gsc` | Google Search Console — set `enabled: true` and point to credentials file |
| `email` / `slack` / `teams` | Notification channels |
| `schedule` | Automated checks — set `enabled: true`, `interval`, `time`, `sitemap_url`, `limit` |
| `priority` | High/low value URL patterns for sorting |
| `track_keywords` | Keywords to watch in GSC data |
| `timings` | Fine-tune timeouts, delays, and rate-limit breaks |
| `thresholds` | Pass/warn score cutoffs for PageSpeed, CTR, rankings |
| `proxies` | List of proxy URLs (e.g. `["http://proxy:8080"]`) |

### 4. Run

```bash
python main.py
```

Open [http://localhost:8080](http://localhost:8080) in your browser.

## Documentation
- `docs/SETUP_GUIDES.md`: step-by-step setup guides for all 11 API integrations (GSC, PageSpeed, Groq, SerpAPI, Moz, DataForSEO, Bing, SMTP, Slack, Teams, Sentry).
- `docs/USECASE_GUIDES.md`: detailed walkthroughs for all 7 audit use cases — what each one checks, what API keys it needs, how to interpret results, and common fixes.
- `DEPLOYMENT.md`: deployment guides for Render, Fly.io, Docker, and plain VPS.
- `NEW_TOOLS_USECASES.md`: product and tool roadmap guidance for the current repo surface.
- `REPO_REVIEW_AND_CLEANUP.md`: current review blockers, cleanup recommendations, and planning notes.
- `TOOL_ROADMAP.md`: overall project roadmap and implementation gate guidance.

## Folder Structure

```
SEO Suite/
├── main.py              ← entry point (run this)
├── config.json          ← non-secret settings
├── requirements.txt     ← pinned dependencies
├── pyproject.toml       ← project metadata & tool config (ruff, mypy, pytest)
├── .env                 ← secrets (never commit)
├── .env.example         ← template for .env
│
├── app/                 ← Flask application
│   ├── server.py        ← Flask web server + all API routes
│   ├── templates/
│   │   └── dashboard.html
│   └── static/
│       ├── css/dashboard.css
│       └── js/dashboard.js
│
├── core/                ← SEO engine modules
│   ├── checker.py       ← Google indexing checker (Playwright)
│   ├── seo_audit.py     ← SEO audit orchestrator
│   ├── auth.py          ← Multi-user session auth + account lockout
│   ├── security.py      ← SSRF protection, DNS rebinding guard, safe HTTP
│   ├── report_generator.py ← HTML / Excel / CSV report builder
│   ├── sitemap_parser.py   ← Sitemap fetching & parsing
│   ├── notifier.py         ← Email / Slack / Teams notifications
│   └── version.py          ← Version string
│
├── tools/               ← SEO audit phase modules
│   ├── phase1.py        ← Technical SEO (no API required)
│   ├── phase2.py        ← PageSpeed / Core Web Vitals
│   ├── phase3.py        ← Google Search Console
│   ├── phase4.py        ← Backlinks / Authority / Rankings
│   ├── generators.py    ← Schema, robots.txt, sitemap generators
│   └── quick_tools.py   ← SERP preview, headers, redirect chain, etc.
│
├── tests/               ← Test suite (pytest)
│
└── data/                ← Runtime data (git-ignored)
    ├── progress/        ← Resume state for interrupted checks
    ├── reports/         ← Generated HTML / JSON / Excel reports (audit)
    ├── uploads/         ← Temporary CSV/XLSX files uploaded via the dashboard
    ├── profiles.json    ← Saved audit profiles
    ├── history.json     ← Indexing run history (trend chart)
    └── app.log          ← Server error log
```

## API Keys

| Key | Where to get | Required for |
|-----|-------------|--------------|
| `PAGESPEED_API_KEY` | [Google Cloud Console](https://console.cloud.google.com) → PageSpeed Insights API | Performance phase |
| `SERPAPI_KEY` | [serpapi.com](https://serpapi.com) | Rankings phase |
| `MOZ_ACCESS_ID` / `MOZ_SECRET_KEY` | [moz.com](https://moz.com/products/api) | Domain Authority |
| `DATAFORSEO_LOGIN` / `DATAFORSEO_PASSWORD` | [dataforseo.com](https://dataforseo.com) | Backlinks / SERP |

All API keys are optional — phases that lack a key are skipped gracefully.

## Google Search Console

See [`docs/SETUP_GUIDES.md`](docs/SETUP_GUIDES.md#1-google-search-console-gsc) for the full step-by-step guide. Quick version:

1. Create a service account in [Google Cloud Console](https://console.cloud.google.com)
2. Enable the Search Console API
3. Download the credentials JSON → save as `gsc_credentials.json` in this folder
4. **Add the service account email as a user in Search Console** (required — GSC is property-based)
5. Enable GSC in the Settings tab of the dashboard

## REST API

The server exposes a JSON API on port 8080. Key endpoints:

| Method | Endpoint | Description |
|--------|---------|-------------|
| `POST` | `/api/index/run` | Start an indexing check |
| `GET` | `/api/index/stream` | SSE stream of indexing progress |
| `POST` | `/api/index/pause` | Pause a running check |
| `POST` | `/api/index/resume` | Resume a paused check |
| `POST` | `/api/index/cancel` | Cancel a running check |
| `POST` | `/api/index/retry` | Retry errored URLs from last run |
| `POST` | `/api/audit/run` | Start an SEO audit |
| `GET` | `/api/audit/stream` | SSE stream of audit progress |
| `POST` | `/api/audit/cancel` | Cancel a running audit |
| `GET` | `/api/reports` | List all reports (indexing + audit) |
| `GET` | `/api/reports/summary` | Summary stats for a report file |
| `GET` | `/api/reports/preview/<file>` | Rich preview data for the side drawer |
| `GET` | `/api/open/<file>` | Open HTML report inline |
| `GET` | `/api/download/<file>` | Download CSV or XLSX |
| `GET` | `/api/reports/pdf/<file>` | Export HTML report to PDF |
| `DELETE` | `/api/reports/delete/<file>` | Delete a report (all formats) |
| `POST` | `/api/reports/delete_bulk` | Delete multiple reports |
| `POST` | `/api/reports/delete_all` | Delete all reports (`confirm:"YES"` required) |
| `GET` | `/api/compare` | Diff two audit XLSX reports |
| `POST` | `/api/upload` | Upload a CSV/XLSX URL list |
| `GET/POST/DELETE` | `/api/profiles` | Manage saved audit profiles |
| `GET/POST` | `/api/settings` | Read / update `config.json` |
| `GET` | `/api/history` | Indexing run history |
| `GET` | `/api/use_cases` | Available audit use cases |
| `GET` | `/api/tasks` | Available audit tasks |
| `GET` | `/health` | Server health + running status |

## Development

### Lint & type-check

```bash
ruff check .          # fast linting
ruff format .         # auto-format
mypy app/ core/       # type checking
```

### Tests

```bash
pytest                        # run all tests
pytest -v                     # verbose
pytest --tb=short             # compact tracebacks
pytest tests/test_checker.py  # single file
```

### Screenshots

| Home Dashboard | Live Progress | Reports |
|---|---|---|
| _(screenshot)_ | _(screenshot)_ | _(screenshot)_ |
