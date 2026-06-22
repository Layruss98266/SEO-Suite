# SEO Suite — Agent Context

## Project Overview
Self-hosted, privacy-first technical SEO audit platform. Single-user or small-team deployment.
Python/Flask backend + plain HTML/CSS/JS SPA frontend. No React/Vue/Node in the main app.

## Stack
| Layer | Tech |
|---|---|
| Backend | Python 3.11+ · Flask · Gunicorn |
| Frontend | Vanilla JS SPA (`dashboard.js` ~2300 LOC) + `dashboard.css` |
| Database | SQLite (`core/db.py`) — users, sessions, login history |
| Auth | Argon2id passwords · TOTP 2FA · CSRF deny-by-default |
| Scheduler | APScheduler (in-process) |
| SEO tools | custom `tools/` + Playwright for JS-heavy checks |
| CI | GitHub Actions (`.github/workflows/ci.yml`) — SHA-pinned |
| Deploy | Docker → Render (free tier, see `render.yaml`) |

## Key Files
| File | Purpose |
|---|---|
| `app/server.py` | Flask app factory + blueprint registration |
| `app/middleware.py` | CSP headers, CSRF validation |
| `app/blueprints/audit.py` | Main audit start/stop/results endpoints |
| `app/blueprints/tools.py` | 40+ individual tool API routes |
| `app/blueprints/auth_views.py` | Login/signup/2FA/user management |
| `app/blueprints/misc.py` | `/app` SPA route, `/health`, `/api/csrf`, `/api/me` |
| `app/static/js/dashboard.js` | Full SPA JS (CSRF bootstrap, panel nav, all tool runners) |
| `app/templates/dashboard.html` | SPA shell — 3000+ line single HTML file |
| `core/auth.py` | Auth helpers, admin_required, cloud detection |
| `core/version.py` | Single source of truth for VERSION |
| `tools/` | Individual SEO check modules (page_type, blog_audit, etc.) |
| `AUDIT_LOG.md` | Running issue tracker — update when fixing items |

## How to Run
```bash
pip install -r requirements.txt
python app/server.py          # dev: port 8080
# or
gunicorn "app.server:create_app()"
```

## How to Test
```bash
pip install -r requirements-dev.txt
pytest tests/ -q
python -m playwright install chromium --with-deps  # first time only
```

## Env Vars
| Var | Purpose |
|---|---|
| `SEO_SUITE_SECRET` | Flask secret key (required in prod) |
| `SEO_SUITE_DATA_DIR` | Data directory (default `./data`) |
| `SEO_SUITE_USERNAME` | Env superadmin username |
| `SEO_SUITE_PASSWORD_HASH` | Argon2id hash for env superadmin |
| `SEO_SUITE_COOKIE_SECURE` | `1` for HTTPS-only cookies (Render) |
| `SEO_SUITE_LIMITER_URI` | Rate-limiter backend (default `memory://`) |
| `NO_AUTH` / `SEO_SUITE_NO_AUTH` | Disable auth — **blocked on cloud hosts** |
| `SEO_SUITE_ALLOW_NO_AUTH_CLOUD` | Override cloud NO_AUTH block (dangerous) |
| `SEO_SUITE_PUBLIC_DOCS` | `1` to expose `/openapi.yaml` + `/docs` publicly |

## Use Case Check Registry (v2.5.1)
| Use Case | Checks | Count |
|---|---|---|
| crawlability | robots, http_status, redirect, broken_links, internal_links, sitemap, canonical, meta_robots, hreflang, ttfb | 10 |
| on_page | title, meta_description, headings, image_alt, word_count, readability, schema, og_tags | 8 |
| site_health | ssl, domain_age, mixed_content, https_enforcement, security_headers, spf, dmarc, mx_records, favicon | 9 |
| performance | pagespeed_mobile, pagespeed_desktop, mobile, gsc_url_inspection, lcp, cls, fcp, inp | 8 (API required) |
| search_console | clicks_impressions, top_queries, position_tracker, ctr_analyzer, coverage_errors, sitemaps_status, manual_actions | 7 (GSC required) |
| authority | backlinks, domain_authority, page_authority, referring_domains, domain_rank, broken_backlinks, nofollow_ratio, spam_score | 8 |
| rankings | rank_tracker, serp_features, competitor, rank_change, traffic_share | 5 (SerpAPI required) |
| technical_seo | composite of crawlability + on_page + site_health | 27 |

**Classification rules:**
- Crawl/indexing directives (canonical, meta_robots, hreflang) → crawlability
- Server response time (ttfb) → crawlability (affects crawl budget)
- Brand/infrastructure assets (favicon) → site_health
- Content quality signals → on_page

## Architecture Notes
- **Panel nav**: `navTo(panelId)` in dashboard.js toggles `.panel` divs. No React router.
- **CSRF**: Deny-by-default. JS fetches `/api/csrf` on load, patches `window.fetch` to inject `X-CSRF-Token`. Exempt only: `/api/csrf`.
- **CSP**: `script-src 'self' 'unsafe-inline'` — required because ~1000 inline `onclick` handlers. TODO: migrate to addEventListener (S-NEW).
- **Audit flow**: POST `/api/audit/start` → SSE stream at `/api/audit/stream` → results at `/api/audit/full_results`.
- **Tool result shape**: `{ok, url, score, passes, warnings, fails, results[{tool, status, message, value, details}]}`.
- **Issue scoring**: `tools/issue_scoring.py` enriches audit results with `scored_issues` (priority-sorted).
- **Cache-busting**: `/app` route rewrites `dashboard.js?v=VERSION` — bump `core/version.py` on JS/CSS changes.
- **Auth on cloud**: `_on_cloud_host()` in `core/auth.py` detects Render/Fly/Railway/Heroku/GCloud/Azure. NO_AUTH=1 on cloud raises RuntimeError unless `SEO_SUITE_ALLOW_NO_AUTH_CLOUD=1`.

## Agent-Specific Notes
- **Never commit .env** — contains secrets.
- **AUDIT_LOG.md** — update status `[x]` when fixing items; update progress table.
- **VERSION** — bump in `core/version.py` whenever JS/CSS changes to bust browser cache.
- **dashboard.html** — 3000+ line file; avoid merge conflicts by editing one section at a time.
- **Test admin user** — username `admin`, password `V3rystrongRandom2026q9z` (local dev only, force-created via sqlite3 if needed).
- **Pre-push hook** — `.githooks/pre-push`. Install: `git config core.hooksPath .githooks`.
- **Render deployment** — auto-deploys from main when CI passes. CI must pass first.
- **`/api/me`** — returns `{ok, username, is_admin}` for logged-in users. SPA uses this to skip `/api/users` for non-admins.

## Known Gotchas
- `inline onclick` handlers in dashboard.html prevent tightening CSP `script-src` — tracked as S-NEW.
- Render free tier has no persistent disk — data (users, reports) resets on redeploy.
- APScheduler runs in-process — don't run multiple gunicorn workers (breaks schedule state).
- `playwright` requires `--no-sandbox` on Render (Linux container with restricted namespaces) — tracked as S15.
- Rate limiter uses `memory://` by default — per-worker on multi-instance deploys. Use Redis URI via `SEO_SUITE_LIMITER_URI` in production.
