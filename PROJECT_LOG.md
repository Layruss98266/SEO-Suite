# SEO Suite — Master Project Log

> **ACCOUNT-SWITCH PROOF. Read every section before touching any code.**
> Last updated: 2026-06-22 (Session 61). Current VERSION: **2.6.6**

---

## 60-Second Resume

```
1. cd "C:\Users\Surya L\Desktop\AI Agents\SEO Suite"
2. Verify version:  python -c "from core.version import VERSION; print(VERSION)"  → 2.6.6
3. Verify checks:   python -c "from core.seo_audit import TASKS; [print(k,len(v)) for k,v in TASKS.items()]"
   crawlability=12, on_page=11, site_health=12, performance=10, technical_seo=35
   search_console=7, authority=8, rankings=5
4. Run app:  python app/server.py  → http://localhost:8080 (port 8080, NOT 5000)
5. Auth:     NO_AUTH=1 python app/server.py  (local dev only — blocked on cloud hosts)
6. Tests:    pytest tests/ -q  →  578 passing
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

> v1.0 → v1.x → v2.0 → v2.1 → v2.2 → v2.3 → v2.4 → v2.5 → v2.5.1 → v2.6.0 → v2.6.1 → v2.6.2 → v2.6.3 → v2.6.4 → v2.6.5 → **v2.6.6** ← current

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

### PHASE 13 — PROJECT_LOG + Pre-push Hook ✅ COMPLETE (v2.6.1)

### PHASE 14 — Audit Findings Resolution ✅ COMPLETE (v2.6.2)

### PHASE 15 — Remaining Audit Items + Phase 0 Blockers ✅ COMPLETE (v2.6.3)
PROJECT_LOG.md created (this file). Pre-push hook strengthened: PROJECT_LOG update check, README version staleness, secrets scan, PROJECT_LOG existence check.

### PHASE 16 — S-NEW onclick Migration + Audit Correctness ✅ COMPLETE (current, v2.6.4)
Completed full inline onclick migration (355 → 0), phase1.py check correctness fixes, reports/tools hardening, and CSS brand token.

---

## What's Built & Verified

### Entry Points
| Command | What |
|---|---|
| `python app/server.py` | Dev server, port 8080 |
| `gunicorn --workers 1 --threads 8 --timeout 300 "app.server:create_app()"` | Production |
| `pytest tests/ -q` | 578 tests |
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
| `core/version.py` | Single source of truth: `VERSION = "2.6.6"` |
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

### 7. CSP `'unsafe-inline'` REMOVED from script-src — NEVER reintroduce inline handlers
As of v2.6.6, CSP is `script-src 'self'` (no `unsafe-inline`). **Any** inline event handler attribute will silently break in the browser with CSP violation. This includes ALL of:
- `onclick="…"`, `onchange="…"`, `oninput="…"`
- `onkeydown="…"`, `onkeyup="…"`, `onsubmit="…"`
- `onmouseover/out`, `onfocus/blur`, `onload`, `onerror`

Also blocked in JS-generated HTML strings — when `innerHTML = '...onclick="…"...'`, the runtime-inserted handler is **just as blocked** as a static one.

**Migration pattern:**
```html
<!-- ❌ Blocked -->
<button onclick="foo('bar')">x</button>
<input oninput="search(this.value)">
<input onchange="toggle(this.checked)" type="checkbox">
<img onerror="this.style.display='none'">

<!-- ✅ Use data-* delegation -->
<button data-action="foo" data-arg="bar">x</button>
<input data-input-action="search">
<input data-change-action="toggle" type="checkbox">
<img data-hide-on-error>
```

Three delegation listeners live in `app/static/js/dashboard.js` (search for `S-NEW`):
- `click` → reads `data-action` + `data-arg`/`data-arg2`
- `change` → reads `data-change-action` (passes `checked`/`value` automatically)
- `input` → reads `data-input-action` (passes `value`)
- `keydown` → reads `data-keydown-action` (special `enterRun` action with `data-arg=funcName`)
- Plus a global `error` listener that hides `<img data-hide-on-error>` on load failure

**Adding new buttons/forms:** add a case to the relevant `switch` in the delegation handler, NOT an inline handler.

**Property-assignment form is fine:** `el.onclick = fn` in JS is a property, not an HTML attribute — CSP allows it.

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

## Common Issues & Fixes

Things that have broken before and how to fix them. Read this before debugging "weird" issues.

### 1. "Use cases not clickable" / "Buttons do nothing" / CSP console errors
**Symptom:** Browser console shows `Executing inline event handler violates the following Content Security Policy directive 'script-src 'self''`.
**Cause:** New code introduced an inline `on<event>="…"` attribute. CSP is locked to `'self'` only since v2.6.5 (see Gotcha #7).
**Fix:**
1. Grep: `grep -rE "on(click|change|input|keydown|keyup|submit|focus|blur|error|load)=" app/templates app/static/js`
2. Convert each match to `data-action` / `data-change-action` / `data-input-action` / `data-keydown-action`
3. Add the corresponding case to the delegation `switch` in `dashboard.js`
4. **Both static HTML and JS-generated `innerHTML` strings must follow the rule.**

### 2. "Use cases grid empty" / "All buttons broken at once"
**Symptom:** Console shows `SyntaxError: Unexpected token '<<'` or any other parse error at top level of `dashboard.js`.
**Cause:** Stray git conflict marker (`<<<<<<<`, `=======`, `>>>>>>>`) left in the file after a merge.
**Fix:** `grep -n "<<<<<<\|======\|>>>>>>" app/static/js/dashboard.js` — remove every marker. Always run `node --check app/static/js/dashboard.js` after resolving JS merge conflicts.

### 3. "VERSION bump forgotten — users see stale UI"
**Symptom:** New JS/CSS deployed but users still see old behavior. Hard-refresh fixes it for one user.
**Cause:** `/app` route injects `dashboard.js?v=VERSION` and `dashboard.css?v=VERSION`. Without a bump, browsers use cached files.
**Fix:** Bump `core/version.py` in the SAME commit as any JS/CSS change. Pre-push hook checks this.

### 4. "Worktree agents made wrong edits / reverted recent work"
**Symptom:** Subagent dispatched with `isolation: "worktree"` writes files based on old code state, undoing recent fixes.
**Cause:** Worktree agents read `.agentmaster/codebase.xml` — a snapshot taken at session start, not live state.
**Fix:** Do not dispatch worktree agents for editing tasks after substantial commits this session. Use main working tree directly, or refresh repomix first: `/agent-master repomix refresh`.

### 5. "Tests pass locally, fail on Render / cloud host"
**Symptom:** App starts but every request returns 500 or "NO_AUTH refused on cloud".
**Cause:** `NO_AUTH=1` is blocked on cloud (Render/Fly/Railway/Heroku/GCloud/Azure detected via env signals).
**Fix:** Set up real admin user via `/signup` or `python -m core.db create_admin` before first request. Override only with `SEO_SUITE_ALLOW_NO_AUTH_CLOUD=1` (dangerous, never recommended for prod).

### 6. "Reports endpoint returns array, frontend expects object"
**Symptom:** Reports panel shows nothing or crashes with "d.length undefined".
**Cause:** `api_reports` and `api_history` return raw arrays. Adding `{"ok": true, ...}` wrapper breaks 6+ JS call sites.
**Fix:** ONLY add `ok` key to object-returning routes (`api_reports_delete`, `api_reports_delete_all`, `api_reports_summary` XLSX path). Array-returning routes stay as arrays.

### 7. "soup cache mutation breaks downstream checks"
**Symptom:** `word_count_check` or `readability_check` returns wrong/zero values intermittently.
**Cause:** Both functions modified the shared `soup` from `fetch_page()` cache via `decompose()`. Next check on same URL sees mutated DOM.
**Fix:** Always `copy.deepcopy(soup)` before mutating. Already fixed in v2.6.2 — keep this in mind for any new check that calls `soup.find(...).decompose()` or removes elements.

### 8. "auth_client fixture leaks state between tests"
**Symptom:** Random ~50 test failures with "Too many failed attempts" or "User exists".
**Cause:** `core.auth._USERS_DB` and `_failed_attempts` persist between tests when SQLite backend is used.
**Fix:** In `tests/conftest.py`, set `SEO_SUITE_USERS_BACKEND=json` and call `_failed_attempts.clear()` in fixtures. Already done in v2.6.2.

### 9. "Pre-push hook fails on commits with binary diffs"
**Symptom:** Pre-push secret-scan flags binary files as containing "AKIA…" tokens.
**Cause:** Hook greps file content without skipping binary.
**Fix:** Hook excludes `*.png|*.jpg|*.pdf|*.xlsx|*.db` via `--include` filter. Ensure `data/` is git-ignored.

### 10. "validate_public_url raises but check still hangs"
**Symptom:** Audit appears stuck on a URL for >2 minutes.
**Cause:** `fetch_page()` catches `RequestException` and `OSError` but NOT `ValueError`. A check calling `fetch_page` directly without wrapping `ValueError` produces an unhandled exception that the ThreadPoolExecutor swallows silently.
**Fix:** Pattern from `www_redirect_check`:
```python
try:
    resp, soup = fetch_page(url)
except ValueError:
    resp, soup = None, None
if resp is None or soup is None:
    return {...}
```

### 11. "Render free tier loses data after each deploy"
**Symptom:** All users + reports gone after redeploy.
**Cause:** Render free tier has no persistent disk. SQLite + reports live in `data/` which resets on every redeploy.
**Fix:** Either accept the demo-only nature OR mount a persistent volume at `SEO_SUITE_DATA_DIR=/var/data` (paid tier required).

### 12. "Schedule never fires"
**Symptom:** Cron schedule set in Settings UI but reports never auto-generate.
**Cause:** App uses single-worker gunicorn (`--workers 1`). If the worker restarts (deploy, OOM, idle scale-down on Render free), the in-memory scheduler resets.
**Fix:** For reliable scheduling, run an external cron hitting `/api/cron/run` with a shared secret. The Settings UI is best-effort only.

### 13. "Repomix snapshot is stale, agents read old code"
**Symptom:** Subagents quote code that has since been refactored or fixed.
**Cause:** `.agentmaster/codebase.xml` is created at session start and reused. After many commits, it's outdated.
**Fix:** Run `/agent-master repomix refresh` after substantial changes mid-session.

### 14. "Merge conflict in dashboard.html/.js after a long-running feature branch"
**Symptom:** Conflicts in 4+ files including dashboard, hard to resolve.
**Cause:** Both branches added inline-onclick that's now invalid (post v2.6.5 CSP lock).
**Fix:** Resolve conflicts → IMMEDIATELY grep for any remaining `on<event>=` in HTML+JS innerHTML → fix all → `node --check app/static/js/dashboard.js` → tests → commit.

---

## Open Items Backlog

### P1 — Critical / High Impact
| ID | Area | Item |
|---|---|---|
| P1 | Product | First-run onboarding wizard — new users see zero guidance, no domain → preset flow |
| P2 | Product | Client/project grouping in Reports panel — flat timestamp list, no domain label |
| P3 | Product | Cross-URL issue aggregation — no "37 pages missing H1" summary view |
| CT3 | Content | Trust signals on home page — no GitHub stars badge, no user count, no testimonials |
| S-NEW-CSP | Security | Remove `'unsafe-inline'` from script-src CSP — onclick migration complete (v2.6.4), just needs middleware.py update |

### P2 — Phase 0 Blockers ✅ ALL RESOLVED
| ID | Item | Status |
|---|---|---|
| PH0-1 | Sitemap SSRF fix — `sitemap_parser.py` bypasses safe wrapper | **FIXED** pre-v2.6.2 — `_validate_url` + `safe_requests_get` |
| PH0-2 | Schema validation SSRF fix — schema validator follows redirects unsafely | **FIXED** pre-v2.6.2 — `fetch_html` → `safe_requests_get` |
| PH0-3 | Path anchoring consistency — data dirs hardcoded, ignore `SEO_SUITE_DATA_DIR` | **FIXED** v2.6.3 — `checker.py` + `seo_audit.py` respect env var |
| PH0-4 | Numeric request validation — malformed payloads → 500s | **FIXED** pre-v2.6.2 — `_int` helper guards numeric fields |
| PH0-5 | Use-case sitemap fallback — no error on empty sitemap expansion | **FIXED** pre-v2.6.2 — `api_usecase_run` returns 400 |
| PH0-6 | robots.txt fetch bypasses SSRF wrapper | **FIXED** pre-v2.6.2 — `phase1.py` uses `safe_requests_get` |

### P3 — Code Quality (low urgency)
| ID | Item |
|---|---|
| C20 | `generate_html` 200-line f-string → Jinja2 template (`core/checker.py:30474`) — already uses Jinja2, N/A |
| C24 | Three URL-validation idioms — consolidate `_reject_unsafe`, `_require_public_url`, `is_safe_url` — already consolidated, N/A |
| C25 | `/api/reports/*` object-returning routes now have `ok` key — **FIXED** v2.6.4 (array routes kept as arrays to avoid JS breakage) |
| S15 | Playwright `--no-sandbox` on attacker HTML — **N/A** (SECURITY comment already in audit.py: "DO NOT add --no-sandbox") |
| U5 | `--brand:#6366F1` CSS token — **FIXED** v2.6.4 |

### P4 — Product Features (future)
| ID | Item |
|---|---|
| P4 | API docs + webhook output |
| P6 | Multiple schedule slots (one job per install currently) |
| P7 | Team/role management UI in Settings (backend exists) |
| P8 | GitHub/install link missing from marketing nav/footer |
| P9 | Screaming Frog CSV as URL source |
| CT11 | Tone consistency across marketing pages |

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
| 57 | 2026-06-22 | v2.6.1 | Comprehensive audit: 3 parallel agents → 66 test failures, 30+ phase1.py issues, 15+ generators.py issues, scoring/dispatch gaps. Findings in PROJECT_LOG Audit section. |
| 58 | 2026-06-22 | v2.6.2 | Fixed all audit findings P1–P5: soup deepcopy (CRITICAL), 66→0 test failures (auth lockout root cause = SQLite _failed_attempts persistence), phase1.py correctness (image_alt, ttfb, schema, content_freshness, robots), generators.py (PostalAddress, hreflang x-default header, sitemap ISO 8601), WEIGHTS+_SCORE_TABLE Batch I gaps, task ID collision gsc_crawl_inspection, schema_type allowlist. |
| 59 | 2026-06-22 | v2.6.3 | Remaining audit items + Phase 0 path anchoring: removed non-standard meta name="title", review schema deprecation warning, jobposting remote fields (jobLocationType + applicantLocationRequirements), product Offer url, robots.txt Sitemap URL validation, dead "h1" key from _SCORE_TABLE, _REQUIRES_MSG improvement, __all__ in seo_audit, SEO_SUITE_DATA_DIR respected in checker.py + seo_audit.py, body-size guard (200 KB) on 5 generator routes. |
| 60 | 2026-06-22 | v2.6.4 | S-NEW complete: all 355 inline onclick handlers migrated to data-action event delegation (scripts/migrate_onclick.py idempotent, 140+ delegation cases). phase1.py: 5xx retry, mixed-proto redirect detection, HTTP Link header canonical fallback, pagination param exclusion in url_structure, CJK-aware meta description pixel widths, hreflang lang_verification field. reports.py: ok key on 3 object-returning routes. tools.py: 200 KB body guard + 30/min rate limit via register(app,limiter). dashboard.css: --brand token. 578/578 tests. |
| 61 | 2026-06-22 | v2.6.5–6 | Full CSP lockdown — `script-src 'self'` (no unsafe-inline). Post-merge cleanup of remaining ~70 inline event handlers (onclick/onchange/oninput/onkeydown/onerror) that came back from Batch H merge or were in JS-generated innerHTML. New change/input/keydown delegation listeners. data-hide-on-error pattern for img fallback. Added "Common Issues & Fixes" section to PROJECT_LOG (14 entries) so future sessions can self-diagnose. Pushed to Render. |

---

## Audit Findings — 2026-06-22

> Produced by 3-agent parallel audit (Session 57). Sessions 58–59 resolved all CRITICAL + HIGH items and most MEDIUM/LOW.
> Remaining open items are marked **OPEN**; resolved items marked **FIXED**.

### Test Suite — 66 Failures

| Count | Root Cause | Files | Status |
|---|---|---|---|
| ~50 | `conftest.py` doesn't isolate `core.auth._USERS_DB`. Real user in `data/seo_suite.db` makes auth active. | `tests/conftest.py`, `core/auth.py` | **FIXED** v2.6.2 — `SEO_SUITE_USERS_BACKEND=json` + `_failed_attempts.clear()` in auth_client fixtures |
| 2 | Stale `/health` assertions — `version` field added but not asserted. | `tests/test_review_fixes.py:113,118` | **FIXED** v2.6.2 |
| 1 | CSP `unpkg.com` removed but test still asserts it. | `tests/test_openapi.py:44` | **FIXED** v2.6.2 |
| 10 | Batch I checks absent from `WEIGHTS` + `_SCORE_EXCLUDED`. | `core/seo_audit.py`, `tools/issue_scoring.py` | **FIXED** v2.6.2 |
| 3 | `/metrics` requires auth — same 401 root cause. | `tests/test_metrics.py` | **FIXED** v2.6.2 |

**Zero-coverage checks (all 10 Batch I — no tests exist):**
`viewport_check`, `lang_check`, `content_freshness_check`, `url_structure_check`, `canonical_loop_check`, `www_redirect_check`, `http2_check`, `render_blocking_check`, `image_optimization_check`, `dns_health_check`

**Other coverage gaps:**
- No test for `/health/ready` endpoint
- No test for `conftest.py` DB isolation itself
- `test_settings_security.py` — 4 more 401 failures (same root cause)

---

### phase1.py — Check Issues

#### CRITICAL — all fixed v2.6.2
| Check | Issue | Status |
|---|---|---|
| `word_count_check` | `tag.decompose()` on cached soup mutates shared `_page_cache` — corrupts DOM for all subsequent checks. | **FIXED** v2.6.2 — deepcopy before decompose |
| `readability_check` | Same `tag.decompose()` mutation on cached soup. | **FIXED** v2.6.2 — deepcopy before decompose |

#### HIGH — all fixed v2.6.2
| Check | Issue | Status |
|---|---|---|
| `robots_check` | 404 response fed into parser — returns pass on empty body. | **FIXED** v2.6.2 |
| `content_freshness_check` | Never compares extracted date to today — always passes. | **FIXED** v2.6.2 |
| `image_alt_check` | `alt=""` (decorative) treated as missing alt — false positive. | **FIXED** v2.6.2 |
| `ttfb_check` | `total_ms == ttfb_ms` — measuring full load twice instead of TTFB. | **FIXED** v2.6.2 |
| `schema_check` | OG `<meta property="og:*">` tags counted as structured data — inflates schema count. | **FIXED** v2.6.2 |

#### MEDIUM — OPEN (low urgency, no test failures)
| Check | Issue |
|---|---|
| `http_status_check` | No retry on transient 5xx — single failure marks site as broken. |
| `redirect_check` | Does not detect mixed HTTP/HTTPS mid-chain redirects. |
| `canonical_check` | Does not handle `rel=canonical` in HTTP headers — only `<link>` tag. |
| `heading_check` | Multiple H1 issues counted but not scored separately from missing H1. |
| `url_structure_check` | Dynamic param detection (`?id=`) flags clean paginated URLs. |
| `dns_health_check` | NS record check uses `socket.getaddrinfo` — doesn't distinguish NXDOMAIN from timeout. |

#### LOW — OPEN
| Check | Issue |
|---|---|
| `meta_description_check` | Pixel-width estimate uses fixed char width — inaccurate for CJK/wide chars. |
| `page_speed_check` | Falls back to timing `requests.get` when PageSpeed API absent — inaccurate proxy. |
| `hreflang_check` | Doesn't verify target URL language matches declared lang attribute. |

---

### generators.py — Issues

#### HIGH — all fixed v2.6.2
| Generator | Issue | Status |
|---|---|---|
| `event` schema | `location.address` plain string — should be `PostalAddress` object. | **FIXED** v2.6.2 |
| hreflang (HTTP header variant) | `x-default` missing from HTTP Link header output. | **FIXED** v2.6.2 |
| sitemap | `lastmod` not ISO 8601 validated — accepts any string. | **FIXED** v2.6.2 |

#### MEDIUM — all fixed v2.6.3
| Generator | Issue | Status |
|---|---|---|
| meta tags | `<meta name="title">` generated — non-standard, ignored by Google. | **FIXED** v2.6.3 |
| review schema | Standalone `Review` deprecated by Google Sept 2023 — no warning emitted. | **FIXED** v2.6.3 — deprecation warning added |
| jobposting schema | Missing `applicantLocationRequirements` + `jobLocationType` for remote jobs. | **FIXED** v2.6.3 |
| product schema | `Offer` object missing `url` field. | **FIXED** v2.6.3 |
| article schema | `author.url` not always populated. | **N/A** — field exists in template + builder; user omission, not a code bug |

#### LOW — all fixed v2.6.3
| Generator | Issue | Status |
|---|---|---|
| robots.txt | `Sitemap:` URL not validated as absolute `https://`. | **FIXED** v2.6.3 |
| hreflang (tag variant) | No BCP 47 validation on `hreflang` value. | **N/A** — `_LOCALE_RE` regex already validates |
| schema (all types) | `@context` hardcoded — no impact, intentional. | **WONTFIX** |

---

### issue_scoring.py — Gaps

**FIXED v2.6.2** — all 10 Batch I checks added to `_SCORE_TABLE` and `WEIGHTS`.

**FIXED v2.6.3** — dead `"h1"` key removed from `_SCORE_TABLE`.

---

### seo_audit.py — Dispatch Issues

| Severity | Issue | Status |
|---|---|---|
| HIGH | `WEIGHTS` missing 8 of 10 Batch I checks. | **FIXED** v2.6.2 |
| MEDIUM | `render_blocking` + `image_optimization` excluded from `technical_seo` expansion — no comment explaining why. | **FIXED** v2.6.2 — comment added |
| MEDIUM | Task ID `"crawlability"` shadows use-case key. | **FIXED** v2.6.2 — renamed `gsc_crawl_inspection` |
| MEDIUM | `_REQUIRES_MSG` misleading — implies render_blocking/image_optimization also need API key. | **FIXED** v2.6.3 — message clarified |
| LOW | No `__all__`. | **FIXED** v2.6.3 |

---

### tools.py (app routes) — Validation Gaps

| Severity | Issue | Status |
|---|---|---|
| HIGH | Generator routes: no body-size guard — oversized payloads reach generators unchecked. | **FIXED** v2.6.3 — 200 KB limit on 5 generator routes |
| MEDIUM | `schema_type` not validated against allowlist before dispatch. | **FIXED** v2.6.2 — allowlist check returns 400 |
| LOW | No per-endpoint rate limiting on generators beyond global limiter. | **OPEN** — low priority |

---

## Roadmap

### Next: Phase 1 features (Phase 0 blockers all resolved ✅, no paid API)
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

_Last updated: 2026-06-22 — Session 59 — v2.6.3_
