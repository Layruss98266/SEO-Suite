# SEO Suite

![Python](https://img.shields.io/badge/python-3.11%2B-blue)
![Flask](https://img.shields.io/badge/flask-3.x-lightgrey)
![Tests](https://img.shields.io/badge/tests-238%20passing-brightgreen)

Self-hosted technical SEO platform. Audit sites, verify Google indexation, generate structured markup, and surface Search Console insights — all from your own machine.

> **No SaaS subscriptions. No data sent to third parties.**

---

## Quick Start

```bash
pip install -r requirements.txt
playwright install chromium
cp .env.example .env        # add your API keys
python main.py              # → http://localhost:8080
```

Create your admin account at `/signup` on first boot.

---

## Features

**Audit & Indexation**
- Indexing Checker — verify Google indexation via Search Console API or live Playwright browser; accepts sitemaps, domain crawl, CSV/XLSX, or pasted URLs
- SEO Audit — 8 use cases: Crawl Access · On-Page SEO · Site Health · Performance · Technical SEO (35-check composite) · Search Console · Authority · Rankings
- Live SSE streaming for both indexing and audits; pause / resume / cancel / retry; cross-run diff

**Tools**

SERP Preview · Redirect Chain · HTTP Headers · Keyword Density · Code:Text Ratio · GZIP & Cache · Link Health · robots.txt Tester · Hreflang Validator · Sitemap Audit · Performance Opportunities · Keyword Research

**Google Search Console**

GSC Opportunities · Position Tracker · CTR Analyzer · Coverage Errors · Sitemaps Status · AI Snippet Optimizer

**Generators**

Schema Markup (15 JSON-LD types) · JSON-LD Validator · robots.txt · XML Sitemap · Hreflang Tags · Meta Tags

**Indexing & Submission**

IndexNow (instant Bing / Yandex submission) · Bing Webmaster API (overview, inspect, submit)

**AI**

AI Assistant — Groq-powered audit explanation that converts error logs into actionable checklists  
AI Meta Drafter — generates 3 CTR-optimized title/description variants using live GSC queries as context

**Platform**
- Multi-user accounts · admin roles · TOTP 2FA with backup codes · session revocation
- argon2id password hashing · CSRF protection · SSRF guards · account lockout · rate limiting
- GDPR self-service data export and account deletion
- SMTP / Slack / Teams notifications · scheduled automated checks
- Prometheus metrics at `/metrics` · OpenAPI 3.1 + Swagger UI at `/docs`
- Reports: HTML · Excel · CSV · PDF with charts and per-URL scoring
- Dark mode · proxy support

---

## API Keys

All integrations are optional — features degrade gracefully when a key is absent.

| Integration | Env Variable | Required For |
|-------------|-------------|-------------|
| Google PageSpeed | `PAGESPEED_API_KEY` | Performance audit, Performance Opportunities |
| Google Search Console | _(JSON credentials file)_ | GSC audit, all GSC tools |
| Groq AI | `GROQ_API_KEY` | AI Assistant, AI Snippet Optimizer |
| SerpAPI | `SERPAPI_KEY` | Rankings phase |
| Moz | `MOZ_ACCESS_ID` + `MOZ_SECRET_KEY` | Domain Authority |
| DataForSEO | `DATAFORSEO_LOGIN` + `DATAFORSEO_PASSWORD` | Backlinks, Keyword Research |
| Bing Webmaster | `BING_WEBMASTER_API_KEY` | Bing tools, IndexNow |
| SMTP | `SMTP_HOST` · `SMTP_PORT` · `SMTP_USERNAME` · `SMTP_PASSWORD` | Email notifications, password reset |
| Slack | `SLACK_WEBHOOK_URL` | Slack notifications |
| Teams | `TEAMS_WEBHOOK_URL` | Teams notifications |
| Sentry | `SENTRY_DSN` | Error tracking |

Step-by-step setup for every integration: [`docs/SETUP_GUIDES.md`](docs/SETUP_GUIDES.md)

---

## Deployment

SEO Suite needs a persistent server — long-running jobs, SSE, Playwright, writable disk. **Vercel / Netlify are not supported.**

| Target | How |
|--------|-----|
| **Render** | Push to GitHub → New Blueprint → select repo (auto-deploys via `render.yaml`) |
| **Fly.io** | `fly launch --copy-config && fly volumes create seo_suite_data --size 1 && fly deploy` |
| **Docker** | `docker build -t seo-suite . && docker run -p 8080:8080 -v seo_suite_data:/app/data seo-suite` |
| **VPS** | `gunicorn --workers 1 --threads 8 --worker-class gthread --timeout 300 --bind 0.0.0.0:8080 app.server:app` |

**Three rules for any host:**
1. Run as **one process** (`--workers 1`) — SSE queues and run state live in memory
2. Mount a **persistent volume** at `SEO_SUITE_DATA_DIR` (default `./data`) for reports and the SQLite user store
3. Set `SEO_SUITE_SECRET` to a stable random hex string so logins survive restarts

Full guide: [`DEPLOYMENT.md`](DEPLOYMENT.md)

---

## Documentation

| | |
|-|-|
| [`docs/OPERATOR_CHECKLIST.md`](docs/OPERATOR_CHECKLIST.md) ⭐ | Production setup checklist — 21 items tagged must-do / recommended / optional. Start here before deploying. |
| [`docs/SETUP_GUIDES.md`](docs/SETUP_GUIDES.md) | Step-by-step setup for all 11 API integrations |
| [`docs/USECASE_GUIDES.md`](docs/USECASE_GUIDES.md) | Walkthroughs for all 7 audit use cases |
| [`DEPLOYMENT.md`](DEPLOYMENT.md) | Render, Fly.io, Docker, and VPS deployment guides |
| [`ARCHITECTURE.md`](ARCHITECTURE.md) | Request flow, security model, threading, data persistence, observability |
| [`PROJECT_LOG.md`](PROJECT_LOG.md) | Version history, all changes, open items, and feature roadmap |
| [Swagger UI](http://localhost:8080/docs) | Interactive REST API docs — available at `/docs` when the app is running |

---

## Project Structure

```
SEO Suite/
├── main.py                  ← entry point
├── app/
│   ├── server.py            ← Flask factory, blueprint wiring
│   ├── blueprints/          ← route handlers (audit, indexing, tools, auth, reports, site)
│   ├── templates/           ← Jinja2 templates (dashboard SPA + marketing site)
│   └── static/              ← CSS + JS
├── core/                    ← checker, audit orchestrator, auth, db, TOTP, notifier, reports
├── tools/                   ← SEO tool modules (phases 1–4, generators, quick tools, AI, Bing, IndexNow)
├── tests/                   ← pytest suite (238 tests)
└── data/                    ← runtime data, git-ignored
    ├── seo_suite.db         ← SQLite: users, sessions, login history, TOTP secrets
    ├── reports/             ← HTML / XLSX / CSV / JSON output
    └── app.log
```

---

## Development

```bash
python main.py                          # run locally at http://localhost:8080
pytest                                  # run all tests
pytest --cov app/ core/ tools/          # with coverage
ruff check . && ruff format .           # lint + format
mypy app/ core/                         # type checking
```

Key env vars: `SEO_SUITE_SECRET` (session signing), `SEO_SUITE_DATA_DIR` (default `./data`), `SEO_SUITE_COOKIE_SECURE=1` (HTTPS), `SEO_SUITE_LOG_JSON=1` (structured logs).
