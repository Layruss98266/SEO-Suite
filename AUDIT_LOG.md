# SEO Suite — Full Audit Log
**Date:** 2026-06-19  
**Audited by:** Claude Code (Opus 4.7) — whole-codebase review via repomix (129 files, 477k tokens)

---

## Priority Legend
- `[CRIT]` — Data loss / security breach / broken core feature
- `[HIGH]` — Significant impact, fix before next release
- `[MED]`  — Noticeable degradation or user friction
- `[LOW]`  — Polish / debt / minor inconsistency

**Status:** `[ ]` open · `[x]` fixed · `[-]` deferred

---

## 🔒 SECURITY

### S1 `[HIGH]` `[x]` XXE / OOB-fetch via lxml — 3 files
- `core/sitemap_parser.py` ~L80
- `core/checker.py`
- `tools/phase1.py`
- **Issue:** `lxml.etree.XMLParser(recover=True)` with default `resolve_entities=True` and `no_network` unset on user-fetched sitemap content. Allows XXE / out-of-band fetch via DOCTYPE.
- **Fix:** `XMLParser(recover=True, resolve_entities=False, no_network=True, huge_tree=False)` on all three sites.

### S2 `[HIGH]` `[ ]` CSRF allowlist is backwards
- `app/middleware.py` — `_CSRF_PROTECTED_PATHS` opt-in list covers only 5 paths
- **Issue:** Everything outside it (incl. `/api/users`, `/api/auth/totp/disable`, `/api/auth/me/delete`) bypasses CSRF. `SameSite=Lax` alone does not protect same-origin script-injected POSTs.
- **Fix:** Deny-by-default; explicitly exempt only declared public APIs.

### S3 `[HIGH]` `[x]` TOTP endpoint brute-forceable
- `app/blueprints/auth_views.py` `/login/totp` POST
- **Issue:** No rate limit, no lockout, `_record_failed_login` not called on bad TOTP. 10⁶ search space, unlimited attempts.
- **Fix:** `@limiter.limit("5 per minute")` + call `_record_failed_login` on TOTP failure.

### S4 `[HIGH]` `[x]` Admin user mgmt unthrottled
- `app/blueprints/auth_views.py` `/api/users` create + DELETE
- **Fix:** `limiter.limit("30 per minute")` applied programmatically to both `api_users_create` and `api_users_delete` view functions in `register()`. (DELETE was missed in the original batch — added in follow-up audit.)

### S5 `[MED]` `[ ]` CSP missing headers + unsafe-inline style-src
- `app/middleware.py`
- **Issue:** `'unsafe-inline'` in `style-src`; missing `Permissions-Policy`, `Cross-Origin-Opener-Policy`, `Cross-Origin-Resource-Policy`, `Cross-Origin-Embedder-Policy`.
- **Fix:** Remove `'unsafe-inline'` from style-src (use nonces); add restrictive COOP/CORP/COEP/Permissions-Policy headers.

### S6 `[MED]` `[x]` SMTP no timeout — stalls auth thread
- `core/notifier.py`
- **Fix:** `smtplib.SMTP(timeout=10)`

### S7 `[MED]` `[ ]` OpenAPI docs unauthenticated
- `app/blueprints/misc.py` `/openapi.yaml` + `/docs`
- **Fix:** Gate behind `@login_required` or env flag.

### S8 `[MED]` `[ ]` Signup auto-login without email verify
- `app/blueprints/auth_views.py` `/signup`
- **Issue:** Auto-logs-in new account, no CAPTCHA. Account farming vector on public deploys.

### S9 `[MED]` `[ ]` SEO_SUITE_NO_AUTH=1 silently disables auth in cloud
- `core/auth.py`
- **Fix:** Refuse to start when cloud env signal + `SEO_SUITE_NO_AUTH=1`.

### S10 `[MED]` `[ ]` Cloud detection incomplete
- `core/auth.py` — misses `RAILWAY_ENVIRONMENT`, `HEROKU_APP_NAME`, `DYNO`, `K_SERVICE`
- **Fix:** Mirror `_CLOUD_ENV_SIGNALS` list from `server.py`.

### S11 `[MED]` `[x]` CI actions still tag-pinned — L-9 regression
- `.github/workflows/ci.yml` — uses `@v4`, `@v5` tags, NOT 40-char SHA
- **Issue:** Commit `14d112b` claims L-9 hash-pinning is "complete" — it is not. Doc/commit drift.
- **Fix:** Re-pin every action to full SHA digest.

### S12 `[LOW]` `[x]` Dockerfile base image tag-pinned not digest
- **Fix:** Add `@sha256:…` to base image.
- **Resolved 2026-06-19:** `Dockerfile` now pins `mcr.microsoft.com/playwright/python:v1.48.0-jammy@sha256:b4bedaaee2a9d1ca83dc30ec8cae65105151dbe7ba41be0154cee6a6a7cdc669`. Refresh instructions documented in the Dockerfile header.

### S13 `[LOW]` `[ ]` flask-limiter memory:// is per-worker
- `app/server.py` — multi-worker deploy = independent rate-limit buckets per worker.
- **Fix:** Move to Redis storage URI or document the limitation.

### S14 `[LOW]` `[ ]` CSP sandbox defeats itself
- `app/blueprints/reports.py` — `sandbox allow-same-origin` defeats sandbox vs same origin.
- **Fix:** Drop `allow-same-origin` or serve from separate origin.

### S15 `[LOW]` `[ ]` Playwright --no-sandbox on attacker HTML
- `app/blueprints/reports.py` — `playwright.chromium.launch(--no-sandbox)` on potentially attacker-influenced HTML.
- **Fix:** Remove flag or use user namespace sandboxing.

### S16 `[LOW]` `[ ]` next param regex too permissive
- `app/blueprints/auth_views.py` — whitespace / unicode not stripped before regex validation.
- **Fix:** Tighten to `r"^/[A-Za-z0-9/_\-?=&%.+#]*$"` and strip/normalize first.

### S17 `[LOW]` `[x]` pip-audit continue-on-error — CVEs don't block
- `.github/workflows/ci.yml`
- **Fix:** Remove `continue-on-error` for direct-dep CVEs.

### S18 `[LOW]` `[ ]` STARTTLS silent cleartext fallback
- `core/notifier.py` — STARTTLS unconditional; falls back silently to cleartext if server rejects.
- **Fix:** Gate on config or fail hard.

### S19 `[LOW]` `[x]` _failed_attempts unbounded in-memory dict
- `core/auth.py` — spam unique usernames → unbounded memory growth.
- **Fix:** Use a TTL cache or cap max size.

### S20 `[LOW]` `[x]` login_history 500-row read no pagination
- `app/blueprints/auth_views.py` — admin can DoS DB by requesting max 500.
- **Fix:** Paginate with `?limit=50&offset=0` (limit clamped to [1,200]); response now `{rows,total,limit,offset}`. `core.db.get_login_history` accepts `offset`; added `core.db.count_login_history`.

---

## 🐛 CODE QUALITY

### C1 `[CRIT]` `[x]` ThreadPoolExecutor cancellation broken
- `app/blueprints/audit.py:2913`
- **Issue:** `f.cancel()` + `break` from `as_completed` doesn't stop in-flight futures. `ThreadPoolExecutor.__exit__` blocks until all submitted tasks finish; `cancel()` only works on not-yet-started tasks.
- **Fix:** `_ex.shutdown(wait=False, cancel_futures=True)` (Python 3.9+) + check cancel flag inside `_audit_one`.

### C2 `[CRIT]` `[x]` _index_status read without lock
- `app/blueprints/indexing.py:18162, 18144, 18171` + `audit.py:22803, 23075`
- **Issue:** Routes read `_index_status["running"]` without `_lock` while worker thread writes to it. Race condition.
- **Fix:** Wrap reads in `with _lock:` or snapshot before use.

### C3 `[HIGH]` `[x]` gsc_check_url leaks exception text to HTML
- `core/checker.py:30182`
- **Issue:** `f"GSC Error: {e}"` leaks cred path / quota details into report HTML.
- **Fix:** Generic `"GSC check failed"` + `logger.exception(e)`.

### C4 `[HIGH]` `[x]` Two CFG sources of truth
- `app.state.CFG` and `core.checker.CFG` manually synced in `settings.py:18451-18452`.
- **Fix:** Remove `_checker_mod.CFG` reference; always read from `app.state.CFG` directly.

### C5 `[HIGH]` `[x]` api_download loads entire file into memory
- `app/blueprints/reports.py:14860`
- **Issue:** `safe.read_bytes()` — multi-MB reports all in memory.
- **Fix:** Use `flask.send_file(safe, as_attachment=True)`.

### C6 `[HIGH]` `[x]` api_open silently rewrites file extension to .html
- `app/blueprints/reports.py:14844`
- **Issue:** `base = filename.rsplit(".", 1)[0] + ".html"` — any extension silently becomes `.html`.
- **Fix:** Reject if not `.html`; or document and make explicit.

### C7 `[HIGH]` `[x]` Sidecar JSON KeyError on missing "issues" key
- `app/blueprints/audit.py:22988`
- **Issue:** `sum(len(a["issues"]) ...)` → KeyError if partial audit lacks `issues`. Silently skipped by outer try/except.
- **Fix:** `a.get("issues", [])` (consistent with line 22787).

### C8 `[HIGH]` `[x]` CLI input() in Flask import path
- `core/checker.py:30055`
- **Issue:** `input()` prompt inside module imported by every Flask route. Dead + confusing in web context.
- **Fix:** Move CLI helpers to `core/cli.py`.

### C9 `[HIGH]` `[ ]` Partial CSV inconsistent column count
- `app/blueprints/indexing.py:18241`
- **Issue:** `/api/index/partial` exports 2 cols (URL, Status); worker CSV writes 7 cols. Same "export" button, different shapes.
- **Fix:** Standardise to 7-col format or make format explicit per export type.

### C10 `[HIGH]` `[ ]` gsc_check_url no rate-limit / backoff
- `core/checker.py`
- **Issue:** 500-URL run exhausts GSC quota (2000 req/day default) with no detection or abort.
- **Fix:** Exponential backoff on `quotaExceeded`; abort further GSC calls in that run.

### C11 `[MED]` `[ ]` audit.py run() 170-line nested god function
- `app/blueprints/audit.py:22844`
- **Fix:** Extract `_run_audit_thread(...)` to module level.

### C12 `[MED]` `[ ]` Phase 3 parallel result collection defeats parallelism
- `app/blueprints/audit.py:23198`
- **Issue:** `[f.result() for f in [ex.submit(fn) for fn in fns]]` — collects in submit order; slow first future blocks all.
- **Fix:** Use `executor.map()` or `as_completed`.

### C13 `[MED]` `[x]` save_progress called per-URL — O(N²) disk writes
- `core/checker.py:30774`
- **Issue:** Full JSON serialise + `os.replace` on every single URL. 500 URLs = ~500 full writes.
- **Fix:** Batch every N URLs (e.g. 10) or write only on completion.

### C14 `[MED]` `[ ]` Duplicate ThreadPoolExecutor boilerplate across phases
- `app/blueprints/audit.py:23115-23271`
- **Fix:** Extract `_run_fns_parallel(fns, max_workers)` helper.

### C15 `[MED]` `[ ]` _require_public_url walrus pattern repeated 10+ times
- `app/blueprints/tools.py:18887, 18910, 18931, 18968, 18994, 19096, 19099, 19121, 19143, 19165`
- **Fix:** Wrap into helper returning response or None.

### C16 `[MED]` `[x]` mkdir loop swallows OSError silently
- `app/state.py:29401`
- **Fix:** `logger.error(...)` on OSError before continuing.

### C17 `[MED]` `[x]` settings.py read_text() uses OS encoding
- `app/blueprints/settings.py:18458`
- **Issue:** Defaults to CP1252 on Windows while write-side uses UTF-8.
- **Fix:** `read_text(encoding="utf-8")`.

### C18 `[MED]` `[ ]` CSRF bypass for all JSON API POSTs
- `app/middleware.py:19444`
- **Issue:** `if request.is_json: return None` blanket exemption. SameSite=Lax alone insufficient.
- **Fix:** Require explicit `X-Requested-With` header check on state-changing endpoints.

### C19 `[LOW]` `[ ]` print() calls in library/Flask import path
- `core/checker.py` — multiple `print()` calls. Won't surface under gunicorn.
- **Fix:** Replace with `logger.debug()`.

### C20 `[LOW]` `[ ]` generate_html is a 200-line f-string
- `core/checker.py:30474`
- **Fix:** Move to Jinja2 template file.

### C21 `[LOW]` `[ ]` generate_schema 15-branch elif chain
- `tools/generators.py:34736`
- **Fix:** Refactor to `BUILDERS = {"article": _build_article, …}` registry.

### C22 `[LOW]` `[ ]` winsound beep in Flask import path
- `core/checker.py:29836`
- **Fix:** Move to `core/cli.py` behind `if __name__ == "__main__"` guard.

### C23 `[LOW]` `[ ]` i_counter dict-as-mutable-int hack
- `app/blueprints/audit.py:22941`
- **Fix:** `nonlocal` counter or `itertools.count()`.

### C24 `[LOW]` `[ ]` Three URL-validation idioms
- `_reject_unsafe()`, `_require_public_url()`, `is_safe_url()` — three different patterns for same thing.
- **Fix:** Consolidate to one.

### C25 `[LOW]` `[ ]` Error response shape inconsistent
- Most endpoints: `{"ok": false, "error": "…"}`. `/api/reports/*` returns `{"error": "…"}` (no `ok` key).
- **Fix:** Standardise to `{"ok": false, "error": "…"}` everywhere.

---

## 🎨 UI / UX

### U1 `[CRIT]` `[x]` 4 undefined CSS variables — silent rendering failures
- `app/static/css/dashboard.css` + `app/templates/dashboard.html`
- **Variables:** `--surface-1`, `--bg-2`, `--c-surface2`, `--c-border2`
- **Issue:** Used throughout but never defined in `:root` or `body.dark`. Silently inherit `initial` (transparent/0) in all themes.
- **Fix:** Define them in `:root` mapped to existing token equivalents.

### U2 `[HIGH]` `[ ]` 443 inline style= overrides in dashboard.html
- **Issue:** Bypass token system; don't respond to dark mode; major maintainability debt.
- **Fix:** Audit and extract the most frequent patterns into utility classes.

### U3 `[HIGH]` `[x]` No skip link — keyboard accessibility failure
- `app/templates/site/base.html` + `app/templates/dashboard.html`
- **Fix:** `<a class="skip-link" href="#main-content">Skip to content</a>` as first child of body.

### U4 `[HIGH]` `[ ]` Form span labels not associated to inputs
- `app/templates/dashboard.html`
- **Issue:** `<span class="label">` used everywhere instead of `<label for="id">`. Screen readers skip them.
- **Fix:** Convert to `<label for="...">` or add `aria-labelledby`.

### U5 `[MED]` `[ ]` Brand color hardcoded in two separate files
- `#6366f1` in both `app/static/css/site.css` and `app/static/css/dashboard.css`
- **Fix:** Single `tokens.css` imported by both, or ensure both files reference the same CSS var.

### U6 `[MED]` `[x]` Mobile bottom nav dead link
- `app/templates/dashboard.html` — `navTo('use-cases')` references non-existent panel. All use-case panels are under `sbg-usecases`.
- **Fix:** Correct `navTo()` call to match actual panel id.

### U7 `[MED]` `[x]` Modal missing ARIA roles
- `app/templates/dashboard.html`
- **Issue:** No `role="dialog"`, `aria-modal="true"` on modals. Close buttons lack `aria-label="Close"`.
- **Fix:** Add ARIA attributes to all modal instances.

### U8 `[MED]` `[x]` features.html no H2 groupings — flat 17-card grid
- `app/templates/site/features.html`
- **Issue:** 17 cards in undifferentiated flat grid. No semantic structure. No scanning hierarchy.
- **Fix:** Group into 4–5 categories with H2 section headers.

### U9 `[LOW]` `[x]` Duplicate CSS tokens
- `dashboard.css` — `--c-blue` defined twice, `.c-purple` defined twice with different values.
- **Fix:** Deduplicate.

### U10 `[LOW]` `[x]` active-tab-btn class undefined
- Referenced in `dashboard.html` with no CSS definition.
- **Fix:** Define in `dashboard.css` or remove from HTML.

### U11 `[LOW]` `[ ]` Command palette hidden on mobile
- `.tb-search` hidden at 720px — only Ctrl+K remains (keyboard-only on desktop).
- **Fix:** Add search icon tap-target on mobile that opens the palette.

### U12 `[LOW]` `[ ]` Sidebar collapse state not persisted
- `app/static/js/dashboard.js` — no localStorage read/write for sidebar collapse state.
- **Fix:** Save to localStorage on toggle; restore on load.

---

## 📝 CONTENT

### CT1 `[HIGH]` `[x]` H1 fails 5-second test
- `app/templates/site/home.html`
- **Current:** `"Technical SEO, engineered for precision."`
- **Fix:** `"Run technical SEO audits free. No SaaS fees, no data leaks."` or benefit-led alternative.

### CT2 `[HIGH]` `[x]` Clichés throughout marketing copy
- `home.html`, `features.html`, `pricing.html`, `about.html`
- **Issue:** "powerful" (×3), "comprehensive", "seamless", "all-in-one", "completely bypass"
- **Fix:** Replace with specifics — counts, timings, real differentiators.

### CT3 `[HIGH]` `[ ]` Zero trust signals on home page
- **Issue:** No testimonials, no GitHub star badge, no user count, no logos, no case studies.
- **Fix:** Minimum: GitHub stars badge in nav + one real quote on hero.

### CT4 `[HIGH]` `[x]` Competing ghost CTAs at bottom of home
- `app/templates/site/home.html`
- **Issue:** "Open the dashboard" + "Create account" both styled `btn-ghost` identically.
- **Fix:** One primary (`btn-primary`) + one secondary (`btn-ghost`).

### CT5 `[MED]` `[x]` Pricing tier 2 label confusing
- `app/templates/site/pricing.html`
- **Current:** "Bring your own keys / API / usage" — no price shown.
- **Fix:** "API-Connected" + "~$0–$10/mo depending on API tier"

### CT6 `[MED]` `[x]` All pages share same meta description
- `app/templates/site/base.html` — no `{% block description %}` overrides on any page.
- **Fix:** Add per-page descriptions to home, features, pricing, about.

### CT7 `[MED]` `[ ]` Missing critical pages
- `/docs` — no setup instructions linked from marketing site (largest conversion gap)
- `/privacy` — no privacy policy (legal risk)
- `/terms` — no terms of service
- `/changelog` — expected by open-source evaluators
- **Fix:** At minimum stub /privacy, /terms, and add GitHub docs link to pricing + footer.

### CT8 `[MED]` `[ ]` Blog zero original content
- `app/templates/site/blog.html` — 5 outbound links only. Zero organic SEO value.
- **Fix:** Write 2 pillar posts: "free Screaming Frog alternative" + "self-hosted SEO tool guide"

### CT9 `[MED]` `[x]` Site SEO — missing canonical, OG tags, structured data
- No `<link rel="canonical">`, no OG/Twitter card meta, no structured data in `base.html`.
- **Fix:** Add canonical + OG meta block to `base.html`; add `{% block og_* %}` overrides per page.

### CT10 `[LOW]` `[x]` Dashboard microcopy issues
- `↩ Logout` → `Sign out`
- `"Welcome to SEO Suite"` → time-aware greeting or remove
- `"0 selected"` → `"Select at least one use case to continue"`
- `"Waiting to start…"` when idle → `"Ready — start a check above"`
- Help button `?` → add `aria-label="Help"`

### CT11 `[LOW]` `[ ]` Tone inconsistency across marketing pages
- Home: warm/benefit-led. Features: spec-sheet. About: preachy manifesto. Contact: abandoned.
- **Fix:** Apply home page voice to all pages. Features: benefit first, spec second.

---

## 👤 PERSONA GAPS (Product / UX)

### P1 `[HIGH]` `[ ]` No onboarding / first-run wizard (Sarah, Liam)
- Dashboard drops new users with zero guidance. "Pick a use case" with no explanation.
- **Fix:** First-run banner in `#panel-home .home-hero-card` — enter domain → preset → plain-English results.

### P2 `[HIGH]` `[ ]` No client/project grouping in Reports (Marcus, Anika)
- Flat timestamp-sorted list, no domain/client label, no filter tab.
- **Fix:** Add "Project" label field to audit form; filter tab in Reports panel.

### P3 `[HIGH]` `[ ]` No cross-URL issue aggregation in audit results (Priya, Anika)
- Only per-URL view. No "37 pages missing H1" summary.
- **Fix:** Add "Issues Summary" tab to audit done-bar — aggregated by check type + affected URL count.

### P4 `[MED]` `[ ]` No API docs or webhook output (Liam)
- REST API endpoints exist (`/api/audit/start`, `/api/index/partial`) but undocumented.
- **Fix:** "API Reference" tab in Help modal + webhook URL field in Settings.

### P5 `[MED]` `[x]` URL limit resets to 10 every run (Anika)
- `saveProfile` / `loadProfile` don't persist `aud-limit` or `aud-workers`.
- **Fix:** Include in profile save/load.

### P6 `[MED]` `[ ]` Single-schedule limit (Anika, Marcus)
- Only one scheduled job slot, one sitemap URL, daily/weekly only.
- **Fix:** Schedule list (array), one entry per domain.

### P7 `[MED]` `[ ]` Team/role management invisible in dashboard (Anika)
- Multi-user + roles exist in backend but no UI in Settings.
- **Fix:** "Team" section in Settings showing users, roles, revoke button.

### P8 `[LOW]` `[ ]` No GitHub/install link on marketing site (Liam)
- No repo link in nav, footer, or pricing card.
- **Fix:** GitHub icon in nav + `pip install` one-liner on pricing self-hosted card.

### P9 `[LOW]` `[ ]` Screaming Frog CSV not accepted as URL source (Priya)
- Input types: Sitemap, Domain, Crawl, CSV, Paste — no SF CSV import.
- **Fix:** Add SF CSV as URL source option with column-mapping step.

---

## ✅ CLEAN (nothing to fix)
- SQL injection (parameterized everywhere)
- Command injection (no shell=True / os.system)
- Pickle / yaml.load deserialization
- eval / exec on user input
- Hardcoded production secrets
- Open redirect
- Weak password hashing (argon2id)
- JWT alg=none
- CORS wildcard + credentials
- Debug mode in production
- dashboard.html repomix security flag (false positive — password placeholders + CSRF meta tag)

---

## Fix Progress Summary
| Category | Total | Fixed | Remaining |
|----------|-------|-------|-----------|
| Security | 21 | 7 | 14 |
| Code Quality | 26 | 13 | 13 |
| UI/UX | 12 | 8 | 4 |
| Content | 11 | 7 | 4 |
| Persona/Product | 9 | 1 | 8 |
| UI/UX + NEW | 15 | 11 | 4 |
| **Total** | **83** | **40** | **43** |

### U-NEW2 `[LOW]` `[x]` Nav logo shows "v?" — version missing from /health
- `app/blueprints/misc.py` `/health` endpoint
- **Issue:** `GET /health` returned `{"status":"ok"}` with no `version` field. `dashboard.js` reads `d.version` from this endpoint; missing field fell back to `"v?"` permanently in the nav logo and sidebar.
- **Fix:** Added `"version": VERSION` to `/health` response.
- **Commit:** `506941d`

### C-NEW1 `[HIGH]` `[x]` generate_sitemap crashes on plain-string URL entries
- `tools/generators.py` `generate_sitemap()` ~L765
- **Issue:** `AttributeError: 'str' object has no attribute 'get'` when the `urls` list contains plain strings instead of dicts. `entry.get("url")` fails on a str.
- **Fix:** Added `if isinstance(entry, str): entry = {"url": entry}` guard before the `.get()` call.
- **Commit:** `7593a1f`

### U-NEW3 `[MED]` `[x]` UC runner silent bail on empty input / no use case
- `app/static/js/dashboard.js` `runUseCase()`
- **Issue:** Clicking Run without selecting a use case (or with empty URL/file) fired a 3-second toast then returned silently — left spinner running, button disabled, no visible feedback. User perception: app broken.
- **Fix:** Render persistent inline `✖` error in `#uc-error`, clear spinner, re-enable button.
- **Commit:** `accbf65`

### C-NEW2 `[CRIT]` `[x]` CSP script-src 'self' broke every dashboard button
- `app/middleware.py` security headers
- **Issue:** Hardening batch removed `'unsafe-inline'` from `script-src` on the assumption that "all scripts are external", but the dashboard wires ~1000+ buttons via inline `onclick="..."` attributes. Browsers blocked every handler ("Executing inline event handler violates CSP"). **The entire dashboard was non-functional.**
- **Fix:** Re-added `'unsafe-inline'` to `script-src` (pre-hardening state). TODO to migrate to `addEventListener` + nonces tracked as S-NEW.
- **Commit:** `ac0ab70`

### S-NEW `[MED]` `[ ]` Migrate inline onclick handlers to addEventListener
- `app/templates/dashboard.html` (~1000+ inline `onclick="..."` attributes)
- **Issue:** Inline handlers force CSP to keep `'unsafe-inline'` in `script-src`, defeating its primary XSS protection.
- **Fix:** Refactor handlers into `dashboard.js` with `addEventListener`, then tighten CSP back to `'self'` (or nonces).
- **Effort:** Multi-day refactor; tracked for a future release.

### U-NEW4 `[MED]` `[x]` Browser cached dashboard.js across releases
- `app/blueprints/misc.py` `/app` route
- **Issue:** `dashboard.html` linked `dashboard.js` and `dashboard.css` with no cache-buster. Flask default static cache is 12h, so JS fixes never reached users without a hard reload.
- **Fix:** `/app` handler rewrites both asset URLs to append `?v=<VERSION>`. Bumping `core.version.VERSION` invalidates the cache for every visitor.
- **Commit:** `0e64cbb`

---

_Last updated: 2026-06-19 — commit `ac0ab70` (37/79 + 4 new = 40 fixed; 1 new open S-NEW)_
