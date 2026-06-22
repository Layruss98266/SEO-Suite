# SEO Suite — Master Project Log

> **ACCOUNT-SWITCH PROOF. Read every section before touching any code.**
> Last updated: 2026-06-22 (Session ~55+). Current VERSION: **2.6.1**

---

## 60-Second Resume

```
1. cd "C:\Users\Surya L\Desktop\AI Agents\SEO Suite"
2. Verify version:  python -c "from core.version import VERSION; print(VERSION)"  → 2.6.1
3. Verify checks:   python -c "from core.seo_audit import TASKS; [print(k,len(v)) for k,v in TASKS.items()]"
   crawlability=12, on_page=11, site_health=12, performance=10, technical_seo=35
   search_console=7, authority=8, rankings=5
4. Run app:  python app/server.py  → http://localhost:8080 (port 8080, NOT 5000)
5. Auth:     NO_AUTH=1 python app/server.py  (local dev only — blocked on cloud hosts)
6. Tests:    pytest tests/ -q  →  238 passing
7. Git push: git config core.hooksPath .githooks  (install pre-push hook once)
8. VERSION file: core/version.py — bump it whenever JS/CSS changes (cache-busting)
9. All HTML-fetching checks in tools/phase1.py use fetch_page() — 30-min shared cache
10. dashboard.js?v=VERSION is rewritten in /app route — bump VERSION to bust browser cache
```

**Do NOT:**
- Run `python main.py` as entry point — correct entry is `python app/server.py`
- Forget `import re` is at module level in phase1.py (moved there in Batch I — don't add local import re again)
- Use `safe_requests_get()` directly in new check functions — use `fetch_page(url)` instead (returns `(resp, soup)` tuple, caches, SSRF-safe)
- Return `"pass"` when `fetch_page()` returns `(None, None)` — that's a network failure; return `"error"`
- Add checks to `TOOLS` registry in phase1.py without also adding to `TASKS` dict in `core/seo_audit.py`, `TASK_DEFS` in `dashboard.js`, and `UC_INFO` in `dashboard.js` — all four must stay in sync
- Change VERSION without updating `PROJECT_LOG.md` version history section
- Use `--workers` > 1 with gunicorn — SSE queues and audit run state are in-process memory
- Commit `.env` — pre-push hook will block it. Check `.gitignore`
- Use `git push --force` — never, on any branch
- Add `Co-Authored-By: Claude` trailer to commits — user wants clean attribution
- Set `NO_AUTH=1` on Render/Fly/Railway/Heroku — `core/auth.py` detects cloud hosts and raises `RuntimeError`
- Write `dashboard.html` inline `onclick` handlers for new features — existing ones are legacy; new wiring goes in `dashboard.js` with `addEventListener`
- Hardcode absolute paths — use relative paths or `DATA_DIR` env var

---

## Current State

### Check Registry (live — verified against `TASKS` in `core/seo_audit.py`)

| Use Case | Checks | Count | API Needed? |
|---|---|---|---|
| crawlability | robots, http_status, redirect, broken_links, internal_links, sitemap, canonical, meta_robots, hreflang, ttfb, url_structure, canonical_loop | 12 | No |
| on_page | title, meta_description, headings, image_alt, word_count, readability, schema, og_tags, viewport, lang_attr, content_freshness | 11 | No |
| site_health | ssl, domain_age, mixed_content, https_enforcement, security_headers, spf, dmarc, mx_records, favicon, dns_health, www_redirect, http2 | 12 | No |
| performance | render_blocking, image_optimization (no API) · pagespeed_mobile, pagespeed_desktop, mobile, gsc_url_inspection, lcp, cls, fcp, inp (API-gated) | 10 | PageSpeed API for 8 |
| technical_seo | composite: crawlability(12) + on_page(11) + site_health(12) | 35 | No |
| search_console | clicks_impressions, top_queries, position_tracker, ctr_analyzer, coverage_errors, sitemaps_status, manual_actions | 7 | GSC creds |
| authority | backlinks, domain_authority, page_authority, referring_domains, domain_rank, broken_backlinks, nofollow_ratio, spam_score | 8 | Moz + DataForSEO |
| rankings | rank_tracker, serp_features, competitor, rank_change, traffic_share | 5 | SerpAPI |

**Classification rules (for future checks):**
- Crawl/indexing directives (canonical, meta_robots, hreflang, url_structure, canonical_loop) → crawlability
- Server response time (ttfb) → crawlability (crawl budget signal)
- Brand/infrastructure assets (favicon, dns, ssl, http2) → site_health
- Content quality + rendering signals → on_page
- Lab/field performance metrics → performance

### phase1.py Check Functions (27 total, all in TOOLS registry)

```
robots_check, http_status_check, redirect_check, canonical_check,
title_check, meta_description_check, heading_check, image_alt_check,
word_count_check, broken_link_check, internal_links_check, schema_check,
hreflang_check, ttfb_check, readability_check, domain_age_check,
ssl_check, dns_health_check, viewport_check, lang_check,
content_freshness_check, url_structure_check, canonical_loop_check,
www_redirect_check, http2_check, render_blocking_check, image_optimization_check
```

---

## Order of Execution (Phases)

> v1.0 → v1.x → v2.0 → v2.1 → v2.2 → v2.3 → v2.4 → v2.5 → v2.5.1 → v2.6.0 → **v2.6.1** ← current

### PHASE 1 — Initial Build ✅ COMPLETE (v1.0)
Flask app, blueprint split, SQLite auth, Playwright, SSE streaming, Docker/Render/Fly deploy, `/metrics` endpoint, OpenAPI spec, initial SEO audit checks.

### PHASE 2 — Auth Hardening ✅ COMPLETE (v1.x)
Argon2id passwords, anti-enumeration, account lockout, HIBP breach check, TOTP 2FA with backup codes, server-side sessions with revocation, GDPR export/delete, password reset flows, login notifications.

### PHASE 3 — Marketing Site ✅ COMPLETE (v2.0)
Public marketing pages (`/`, `/features`, `/pricing`, `/about`, `/blog`), app moved behind `/app`, humanized copy, em-dash sweep, IndexNow guide, Groq setup guide.

### PHASE 4 — Security Audit (30-issue batch) ✅ COMPLETE (v2.1)
Fixed 19/21 security items from full-codebase audit:
S1 XXE/OOB-fetch via lxml, S2 CSRF deny-by-default, S3 TOTP brute-force, S4 admin throttle, S5 CSP/COOP/CORP headers, S6 SMTP timeout, S7 OpenAPI gated, S8 signup auto-login, S9 NO_AUTH blocked on cloud, S10 cloud detection, S11/S12 CI + Docker SHA pinning, S13 configurable limiter backend, S14 CSP sandbox, S16 next-param regex, S17 pip-audit, S19 failed_attempts TTL cap, S20 login history pagination.

Remaining open: S15 (Playwright --no-sandbox), S-NEW (inline onclick → addEventListener).

### PHASE 5 — Code Quality Refactors ✅ COMPLETE (v2.2)
Fixed 18/26 code quality items. Key fixes: C1 executor cancellation, C2 index_status race condition, C3-C8 various high-priority bugs, C11 god function extraction, C14 shared phase runner, C15 require_public_url decorator, C19/C22 print/winsound in Flask path, C23 itertools.count, C25 api_error helper. CSRF bypass (C18) fixed. Jinja2 HTML report template. 

Remaining open: C20 (generate_html f-string), C24 (3 URL-validation idioms), C25 partial (reports/* missing ok key).

### PHASE 6 — UI/UX + Content ✅ COMPLETE (v2.1.x)
All 12 UI/UX items fixed (U1-U12): undefined CSS vars, skip link, label[for], modal ARIA, sidebar localStorage, mobile bottom nav, cache-busting dashboard.js, /health version field.

9/11 content items fixed: H1 rewrite, per-page meta descriptions, privacy/terms/changelog stubs, blog pillar posts, CTA hierarchy, OG tags, features page groupings.

Remaining open: CT3 (trust signals — GitHub stars, user count), CT11 (tone consistency across pages).

### PHASE 7 — Specialist Audit Modules ✅ COMPLETE (v2.3)
`tools/page_type.py` — auto-detects course/blog/product/generic.
`tools/course_audit.py` — 8-section course page audit (schema, CTAs, instructor, pricing, FAQ, trust).
`tools/blog_audit.py` — author, date, schema, OG, reading time.
`tools/duplicate_detector.py` — cross-URL duplicate content via SimHash.
`tools/issue_scoring.py` — impact × effort scoring; `scored_issues` field in audit results.
All wired into dashboard (4 new tool panels).

### PHASE 8 — CI + Mobile + /api/me ✅ COMPLETE (v2.4)
CI SHA pinning corrected (39-char truncated → verified 40-char). `/api/me` added — SPA skips `/api/users` for non-admins (eliminates 403 console noise). `.tool-row` CSS added. Pre-push hook created at `.githooks/pre-push`.

### PHASE 9 — Technical SEO Use Case ✅ COMPLETE (v2.5)
New use case `technical_seo` = crawlability(10) + on_page(8) + site_health(9) = 27 checks. Mobile search tap-target. C25 partial fix. AUDIT_LOG stale items corrected.

### PHASE 10 — Check Reclassification ✅ COMPLETE (v2.5.1)
Moved checks to correct use cases: hreflang + ttfb → crawlability; favicon → site_health; canonical + meta_robots removed from on_page (kept in crawlability). Fixed: technical_seo badge showing 0 (UC_INFO entry missing). Updated "27 checks" string in USE_CASES + UC_DEFS.

### PHASE 11 — Batch I: 10 New Checks ✅ COMPLETE (v2.6.0)
Added viewport, lang_attr, content_freshness, url_structure, canonical_loop, dns_health (wired), www_redirect, http2, render_blocking, image_optimization. All 9 HTML-fetching checks use `fetch_page()` shared cache. New counts: crawlability=12, on_page=11, site_health=12, performance=10, technical_seo=35.

### PHASE 12 — Batch I Quality Fixes ✅ COMPLETE (v2.6.1)
5 fixes: render_blocking separate JS/CSS thresholds, image_optimization smart content-image filter + fetchpriority, www_redirect NXDOMAIN returns pass, canonical_loop missing canonical returns warning, all checks use shared fetch_page cache.

### PHASE 13 — PROJECT_LOG + Pre-push Hook ✅ COMPLETE (current)
PROJECT_LOG.md created (this file). Pre-push hook strengthened: PROJECT_LOG update check, README version staleness, secrets scan, PROJECT_LOG existence check.

---

## What's Built & Verified

### Entry Points
| Command | What |
|---|---|
| `python app/server.py` | Dev server, port 8080 |
| `gunicorn --workers 1 --threads 8 --timeout 300 "app.server:create_app()"` | Production |
| `pytest tests/ -q` | 238 tests |
| `ruff check . && ruff format .` | Lint + format |

### Blueprint Routes
| Blueprint | File | Key Routes |
|---|---|---|
| audit | `app/blueprints/audit.py` | `/api/audit/start`, `/api/audit/stream` (SSE), `/api/audit/full_results`, `/api/audit/cancel` |
| indexing | `app/blueprints/indexing.py` | `/api/index/run`, `/api/index/stream`, `/api/index/partial` |
| tools | `app/blueprints/tools.py` | 40+ `/api/tools/*` individual tool routes |
| auth_views | `app/blueprints/auth_views.py` | `/login`, `/signup`, `/logout`, `/login/totp`, `/api/users`, `/api/me` |
| misc | `app/blueprints/misc.py` | `/app` (SPA), `/health`, `/api/csrf`, `/metrics` |
| reports | `app/blueprints/reports.py` | `/api/reports/*` — list, download, delete |
| settings | `app/blueprints/settings.py` | `/api/settings` GET/POST |
| runners | `app/blueprints/runners.py` | `/api/usecase/run` |
| site | `app/blueprints/site.py` | `/`, `/features`, `/pricing`, `/about`, `/blog`, `/privacy`, `/terms` |

### Core Modules
| File | Purpose |
|---|---|
| `core/seo_audit.py` | `TASKS` dict (authoritative check registry), `USE_CASES` dict, `audit_single_url()` dispatch |
| `core/checker.py` | Main audit orchestrator — runs phases, saves progress, GSC integration |
| `core/auth.py` | `login_required`, `admin_required`, cloud detection, `_failed_attempts` TTL cache |
| `core/db.py` | SQLite helpers — users, sessions, login history, TOTP |
| `core/version.py` | Single source of truth: `VERSION = "2.6.1"` |
| `core/notifier.py` | SMTP/Slack/Teams notifications |
| `app/middleware.py` | CSP headers, CSRF deny-by-default |
| `app/state.py` | `CFG` dict, `_check_public_url()`, `require_public_url` decorator |

### Tools Modules
| File | What |
|---|---|
| `tools/phase1.py` | 27 no-API audit checks + `fetch_page()` cache + `TOOLS` registry |
| `tools/phase2.py` | PageSpeed API, GSC URL inspection, CWV (LCP/CLS/FCP/INP) |
| `tools/phase3.py` | Authority checks (Moz, DataForSEO) |
| `tools/phase4.py` | Rankings (SerpAPI) |
| `tools/generators.py` | Schema (15 JSON-LD types), robots.txt, XML sitemap, hreflang, meta tags |
| `tools/quick_tools.py` | SERP preview, redirect chain, HTTP headers, keyword density, code:text ratio, GZIP+cache |
| `tools/ai_assist.py` | Groq-powered audit explanation, AI meta drafter |
| `tools/page_type.py` | Auto-detect course/blog/product/generic |
| `tools/course_audit.py` | 8-section course page audit |
| `tools/blog_audit.py` | Author, date, schema, OG, reading time |
| `tools/duplicate_detector.py` | Cross-URL duplicate content (SimHash) |
| `tools/issue_scoring.py` | Impact × effort scoring — adds `scored_issues` to audit results |
| `tools/sitemap_audit.py` | Sitemap audit (in/out, orphans, oversized) |
| `tools/schema_validator.py` | JSON-LD validator (SSRF fix pending before UI exposure) |
| `tools/bing_webmaster.py` | Bing Webmaster API integration |
| `tools/indexnow.py` | IndexNow submission |
| `tools/keyword_research.py` | Keyword research (DataForSEO) |
| `tools/_common.py` | `safe_error()`, `xml_text()`, shared helpers |
| `tools/_phase_runner.py` | `run_fns_parallel()`, `run_phase()` — shared ThreadPoolExecutor helpers |

### Frontend (dashboard.js key structures)
| Structure | Purpose | Update When |
|---|---|---|
| `UC_DEFS[]` | Nav sidebar entries, use case descriptions | Adding/renaming use cases |
| `TASK_DEFS{}` | Task lists per use case | Adding/removing checks |
| `UC_INFO{}` | Badge check counts + learn panel text + tips | Check counts change |
| `VERSION` check | `/app` route injects `dashboard.js?v=VERSION` | Every VERSION bump |

### Data & Config
| Path | What |
|---|---|
| `data/seo_suite.db` | SQLite: users, sessions, login history, TOTP secrets (git-ignored) |
| `data/reports/` | HTML/XLSX/CSV/JSON audit outputs (git-ignored) |
| `data/app.log` | Runtime logs (git-ignored) |
| `.env` | API keys + secrets (NEVER commit) |
| `render.yaml` | Render blueprint (free tier) |
| `Dockerfile` | SHA-pinned `mcr.microsoft.com/playwright/python:v1.48.0-jammy` |
| `.github/workflows/ci.yml` | SHA-pinned actions: checkout, setup-python, upload-artifact |

---

## Critical Gotchas

### 1. `fetch_page()` vs `safe_requests_get()` — use fetch_page for all HTML checks
`fetch_page(url)` in phase1.py: calls `validate_public_url`, caches 30 min, returns `(resp, soup)`. Returns `(None, None)` on network failure (not on `ValueError` from SSRF guard — that raises). New checks must call `fetch_page`, check `if resp is None or soup is None → return error`, never bypass.

### 2. `validate_public_url()` raises `ValueError` — does NOT return None
SSRF guard raises `ValueError("Could not resolve URL host: ...")` for bad domains. `fetch_page` catches `RequestException, OSError` but NOT `ValueError`. If your function wraps `fetch_page`, catch `ValueError` separately — see `www_redirect_check` for the correct pattern.

### 3. All four registries must stay in sync
Adding a check: update `TOOLS` list in `tools/phase1.py` + `TASKS` dict in `core/seo_audit.py` + `TASK_DEFS` in `dashboard.js` + `UC_INFO` checks array in `dashboard.js`. Forget one → badge count wrong or check never runs.

### 4. VERSION bump required for every JS/CSS change
`/app` route rewrites `dashboard.js?v=VERSION` and `dashboard.css?v=VERSION`. Change any JS/CSS without bumping VERSION → users get stale cached files until hard reload. Bump in `core/version.py` and update PROJECT_LOG version history.

### 5. One gunicorn worker only
`--workers 1` is NOT optional. SSE audit streams, cancellation flags, and run state are all in-process memory. Multiple workers = state split across processes = broken cancel, broken SSE, broken audit progress.

### 6. `NO_AUTH=1` blocked on cloud
`core/auth.py` → `_on_cloud_host()` detects Render/Fly/Railway/Heroku/GCloud/Azure. `NO_AUTH=1` on any cloud host raises `RuntimeError` at startup. Override requires `SEO_SUITE_ALLOW_NO_AUTH_CLOUD=1` (dangerous). Only use `NO_AUTH=1` for local dev.

### 7. CSP keeps `'unsafe-inline'` in script-src intentionally
Dashboard has ~1000 inline `onclick="..."` attributes. Removing `'unsafe-inline'` broke every button (C-NEW2). Tracked as S-NEW. Do not remove it until all inline handlers are migrated to `addEventListener`.

### 8. technical_seo is a composite use case
`audit_single_url()` in `core/seo_audit.py` expands `technical_seo` in the `active` set to `{crawlability, on_page, site_health}` before dispatching checks. It never dispatches `technical_seo` directly. TASKS entry for it is `crawlability + on_page + site_health` keys (35 total).

### 9. Import `re` is at module level in phase1.py
`import re` is between the `logging` and `threading` imports at line ~22. `image_optimization_check` uses `re.compile(r"image/(webp|avif)")` for BeautifulSoup source detection. Do not add `import re` locally inside a function — it already exists.

### 10. CI SHA pins must be exactly 40 hex chars, lowercase
Prior incident: 39-char truncated SHAs and uppercase letters broke CI on every push. Verify any new action SHAs via GitHub API before committing. See commit `bde9d97` for the correct format.

### 11. Data directory must be persistent on cloud
Render free tier has no persistent disk — SQLite user store and all reports reset on every redeploy. Mount a persistent volume at `SEO_SUITE_DATA_DIR` for any production deploy. Free tier is demo/test only.

### 12. `www_redirect_check` NXDOMAIN pattern — fetch then check separately
`fetch_page(alt_url)` raises `ValueError` for non-existent www variants (SSRF guard hits DNS lookup). Pattern: wrap only the `fetch_page` call in try/except, set `resp = None` on any exception, then check `if resp is None → return pass`. See lines 1355-1380 in phase1.py.

---

## Open Items Backlog

### P1 — Critical / High Impact
| ID | Area | Item |
|---|---|---|
| P1 | Product | First-run onboarding wizard — new users see zero guidance, no domain → preset flow |
| P2 | Product | Client/project grouping in Reports panel — flat timestamp list, no domain label |
| P3 | Product | Cross-URL issue aggregation — no "37 pages missing H1" summary view |
| CT3 | Content | Trust signals on home page — no GitHub stars badge, no user count, no testimonials |
| S-NEW | Security | Migrate ~1000 inline `onclick` handlers to `addEventListener` — unblocks CSP tightening |

### P2 — Phase 0 Blockers (must fix before new feature work)
| ID | Item | Blocks |
|---|---|---|
| PH0-1 | Sitemap SSRF fix — `sitemap_parser.py` bypasses safe wrapper | Sitemap Audit feature |
| PH0-2 | Schema validation SSRF fix — hidden schema validator follows redirects unsafely | Rich Results UI |
| PH0-3 | Path anchoring consistency — runtime data splits dirs when app launched outside repo root | All new report tools |
| PH0-4 | Numeric request validation — malformed payloads → 500s in several routes | Any new tool endpoint |
| PH0-5 | Use-case sitemap fallback — sitemap mode audits the XML when expansion fails | Sitemap-mode audits |
| PH0-6 | robots.txt fetch bypasses SSRF wrapper | Crawlability feature work |

### P3 — Code Quality (low urgency)
| ID | Item |
|---|---|
| C20 | `generate_html` 200-line f-string → Jinja2 template (`core/checker.py:30474`) |
| C24 | Three URL-validation idioms — consolidate `_reject_unsafe`, `_require_public_url`, `is_safe_url` |
| C25 | `/api/reports/*` responses missing `ok` key |
| S15 | Playwright `--no-sandbox` on attacker HTML (`app/blueprints/reports.py`) |

### P4 — Product Features (future)
| ID | Item |
|---|---|
| P4 | API docs + webhook output |
| P6 | Multiple schedule slots (one job per install currently) |
| P7 | Team/role management UI in Settings (backend exists) |
| P8 | GitHub/install link missing from marketing nav/footer |
| P9 | Screaming Frog CSV as URL source |
| CT11 | Tone consistency across marketing pages |
| U5 | Brand color `#6366f1` hardcoded in both CSS files — need single token |

---

## Session History

| Session | Date | Version | Key Work |
|---|---|---|---|
| 1 | early 2026 | v1.0 | Initial commit — Flask app, SSE streaming, 7 audit use cases, phase1-4 tools, Docker, Render |
| 2–5 | early 2026 | v1.x | Auth: argon2id, TOTP 2FA, server sessions, GDPR export/delete, login history |
| 6–8 | early 2026 | v1.x | Blueprint split, `/metrics`, OpenAPI spec, observability, 238 tests |
| 9–12 | 2026-05-26 | v1.x | Security hardening batch: 30 issues fixed (M-2/4/11/12, L-3/4/9 + more) |
| 13–15 | early 2026 | v2.0 | Marketing site: public pages, blog, humanized copy, em-dash sweep |
| 16–20 | 2026-06-14 | v2.0 | Tools & generators hardening: safe_error, xml_text, size-capped fetch_html, SSRF in schema_validator |
| 21–25 | 2026-06-14 | v2.0 | Phase-A quick tools, link health, crawl intelligence, hreflang validator, robots.txt tester |
| 26–28 | 2026-06-18 | v2.0 | Merged features: blog, humanized copy, multi-user auth, TOTP, GDPR |
| 29–32 | 2026-06-18 | v2.1 | Full-codebase audit (129 files, 91 issues logged). Batch 1: 16 items fixed |
| 33–36 | 2026-06-19 | v2.1 | Security batch S1-S20 (19/21 fixed). UI/UX batch U1-U12 (all fixed). Content CT1-CT11 (9/11 fixed) |
| 37–40 | 2026-06-19 | v2.2 | Code quality batch C1-C25 (18/26 fixed): god function, phase runner, api_error, itertools.count, Jinja2 report, SCHEMA_BUILDERS |
| 41–44 | 2026-06-19 | v2.3 | Specialist modules: page_type, course_audit, blog_audit, duplicate_detector, issue_scoring. Dashboard wiring for all 4. |
| 45–48 | 2026-06-20 | v2.4 | Batch G: CI SHA pinning corrected, /api/me endpoint, .tool-row CSS, pre-push hook |
| 49–51 | 2026-06-20 | v2.5 | Batch H: technical_seo use case (27 checks), mobile search tap-target, C25 partial |
| 52 | 2026-06-21 | v2.5.1 | Check reclassification: hreflang+ttfb → crawlability, favicon → site_health, canonical+meta_robots removed from on_page. Fixed technical_seo badge (0 → correct). Updated USE_CASES "27 checks" string. |
| 53–54 | 2026-06-22 | v2.6.0 | Batch I: 10 new checks (viewport, lang_attr, content_freshness, url_structure, canonical_loop, dns_health, www_redirect, http2, render_blocking, image_optimization). technical_seo now 35 checks. |
| 55 | 2026-06-22 | v2.6.1 | 5 quality fixes: render_blocking thresholds, image_optimization smart filter, www_redirect NXDOMAIN→pass, canonical_loop missing canonical→warning, shared fetch_page cache for all HTML checks. |
| 56 | 2026-06-22 | v2.6.1 | PROJECT_LOG.md rebuilt (account-switch proof), pre-push hook strengthened (5 new checks), README updated (8 use cases, PROJECT_LOG in docs table). |

---

## Roadmap

### Next: Phase 0 Blockers (before any new features)
1. Sitemap SSRF fix
2. Schema validation SSRF fix
3. Path anchoring consistency
4. Numeric request validation
5. Use-case sitemap fallback fix
6. robots.txt safe-fetch fix

### Phase 1 (after blockers, no paid API)
Rich Results / Schema Validation UI → Sitemap Audit → Bing Visibility Workspace → IndexNow Submission Tool → Trend Explorer

### Phase 2 (authenticated free-platform)
Baseline GSC Opportunity Layer → Performance Opportunity Layer → Groq AI Assistance Layer (explain findings, draft fixes, meta variants)

### Phase 3 (paid/metered)
Content Gap / Competitor Gap → Backlink Reclamation → AI Visibility / Citation Tracking → Paid-enriched GSC

Full detail: `TOOL_ROADMAP.md`

---

## Env Vars Quick Reference

| Var | Required | Purpose |
|---|---|---|
| `SEO_SUITE_SECRET` | Prod | Flask session signing key |
| `SEO_SUITE_DATA_DIR` | Optional | Data dir (default `./data`) |
| `SEO_SUITE_COOKIE_SECURE` | Prod | `1` for HTTPS-only cookies |
| `SEO_SUITE_LIMITER_URI` | Prod | Rate limiter backend (default `memory://`, use Redis URI for multi-instance) |
| `NO_AUTH` / `SEO_SUITE_NO_AUTH` | Dev only | Disable auth — blocked on cloud |
| `PAGESPEED_API_KEY` | Optional | Performance audit, PageSpeed |
| `GROQ_API_KEY` | Optional | AI assistant, meta drafter |
| `SERPAPI_KEY` | Optional | Rankings phase |
| `MOZ_ACCESS_ID` + `MOZ_SECRET_KEY` | Optional | Domain Authority |
| `DATAFORSEO_LOGIN` + `DATAFORSEO_PASSWORD` | Optional | Backlinks, keyword research |
| `BING_WEBMASTER_API_KEY` | Optional | Bing tools, IndexNow |
| `SMTP_HOST/PORT/USERNAME/PASSWORD` | Optional | Email notifications, password reset |
| `SLACK_WEBHOOK_URL` | Optional | Slack notifications |
| `SENTRY_DSN` | Optional | Error tracking |

---

_Last updated: 2026-06-22 — Session 56 — v2.6.1_
