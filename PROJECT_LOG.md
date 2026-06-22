# SEO Suite — Project Log

> Living document. Update in the same commit as any VERSION bump, new feature, or structural change.
> Pre-push hook enforces this: it warns if `PROJECT_LOG.md` was not touched in a push that changed `core/version.py`, `tools/phase1.py`, or `core/seo_audit.py`.

---

## Project Snapshot

| Item | Value |
|---|---|
| **Current version** | 2.6.1 |
| **Stack** | Python 3.11 · Flask 3.x · SQLite · Vanilla JS SPA |
| **Total audit checks** | 35 (no-API) + 8 API-gated performance + 7 GSC + 5 rankings + 8 authority |
| **Use cases** | 8 (crawlability, on_page, site_health, performance, search_console, authority, rankings, technical_seo) |
| **Test count** | 238 passing |
| **Deploy targets** | Render (auto) · Fly.io · Docker · VPS (gunicorn) |
| **Auth** | Argon2id · TOTP 2FA · CSRF deny-by-default · rate limiting · account lockout |
| **Privacy** | Self-hosted, no third-party data leaks — all checks run from the user's server |

---

## Version History

### v2.6.1 — 2026-06-22
**5 quality fixes to Batch I checks**

| Fix | Detail |
|---|---|
| `render_blocking` thresholds | Separate JS (>0=warn, >2=fail) vs CSS (>6=warn, >12=fail). Previous single threshold caused false fails on CSS-heavy sites. |
| `image_optimization` smart filter | Skip `data:` URI inline images and `aria-hidden="true"` decorative images before scoring. Add `fetchpriority=high` absence warning for LCP candidates. |
| `www_redirect` NXDOMAIN | `validate_public_url` raises `ValueError` for non-existent hosts. Catch it in the fetch block so non-resolvable www variants return `[pass]` (no duplicate risk) instead of `[error]`. |
| `canonical_loop` no-canonical | When no canonical tag exists on first hop, return `[warning]` (add self-referencing canonical) instead of `[pass]`. |
| Shared `fetch_page()` cache | All 9 new HTML-fetching checks now use the existing 30-min in-memory cache instead of making separate HTTP requests per check. |

**Files:** `tools/phase1.py`, `core/version.py`

---

### v2.6.0 — 2026-06-22
**Batch I: 10 new checks across 4 use cases**

New checks added to `tools/phase1.py` and wired into `core/seo_audit.py` + `dashboard.js`:

| Check | Use Case | What it checks |
|---|---|---|
| `viewport_check` | on_page | `<meta name="viewport">` presence and `width=device-width` |
| `lang_check` | on_page | `lang` attribute on `<html>` element |
| `content_freshness_check` | on_page | `Last-Modified` header + `article:modified_time`, `<time datetime>` in-page signals |
| `url_structure_check` | crawlability | URL length, uppercase chars, session params, slug underscores, long numeric IDs |
| `canonical_loop_check` | crawlability | Traces canonical chain up to 5 hops; detects loops, multi-hop chains, missing canonicals |
| `dns_health_check` | site_health | Was already implemented; now wired into the dispatch block |
| `www_redirect_check` | site_health | Tests www ↔ non-www; detects duplicate content or missing redirect consolidation |
| `http2_check` | site_health | Uses httpx to detect HTTP/2 or HTTP/3 support |
| `render_blocking_check` | performance | Counts blocking `<script>` (no async/defer) and `<link rel=stylesheet>` in `<head>` |
| `image_optimization_check` | performance | Lazy loading ratio, WebP/AVIF usage, missing width/height (CLS risk) |

**Check counts after:** crawlability=12, on_page=11, site_health=12, performance=10, technical_seo=35

**Files:** `tools/phase1.py`, `core/seo_audit.py`, `app/static/js/dashboard.js`, `agents.md`, `AUDIT_LOG.md`

---

### v2.5.1 — 2026-06-21
**Check reclassification + project sync**

Moved checks to semantically correct use cases:
- `hreflang` + `ttfb` → crawlability (from on_page) — both are crawl/indexing signals
- `canonical` + `meta_robots` → removed from on_page (kept only in crawlability)
- `favicon` → site_health (from on_page) — infrastructure asset, not content

Fixed: technical_seo badge showing 0 checks — UC_INFO entry was missing from dashboard.js.
Updated: USE_CASES description "27 checks" in seo_audit.py.

---

### v2.5.0 — 2026-06-20
**Batch H: Technical SEO use case (27 checks) + mobile fixes**

- New use case `technical_seo` — composite of crawlability(10) + on_page(8) + site_health(9)
- Mobile search tap-target added (`#tb-mob-search` button, hidden on desktop)
- C25 partial fix: `/api/reports/delete_bulk` missing `ok` key in response
- AUDIT_LOG: marked S18, C21, C23 as fixed (were already fixed in code, log was stale)

---

### v2.4.0 — 2026-06-20
**Batch G: CI fixes, /api/me, mobile improvements**

- CI SHA pinning corrected (39-char truncated SHAs → verified 40-char SHAs)
- `/api/me` endpoint added — SPA reads this to skip `/api/users` for non-admins (eliminates 403 console noise)
- `.tool-row` CSS added — layouts in 15+ tool panels were unstyled
- Pre-push hook created at `.githooks/pre-push`

---

### v2.3.0 — 2026-06-19
**Page-type detection + specialist audit modules**

- `tools/page_type.py` — auto-detects course / blog / product / generic pages
- `tools/course_audit.py` — 8-section course page audit (schema, CTAs, instructor, pricing, FAQ...)
- `tools/blog_audit.py` — author / date / schema / OG / reading time audit
- `tools/duplicate_content.py` — cross-URL duplicate content detector via SimHash
- `tools/issue_scoring.py` — impact × effort scoring for audit issues; `scored_issues` in result shape
- All four wired into dashboard: page-type detector, course audit, blog audit, duplicate scan panels

---

### v2.2.0 — 2026-06-19
**Code quality refactors (Batches C–F)**

Major refactors in `app/blueprints/audit.py`, `core/checker.py`, `tools/`:
- Extracted `_run_audit_thread` from 170-line god function
- Extracted `run_fns_parallel` / `run_phase` into `tools/_phase_runner.py`
- Unified API error shape via `api_error()` helper
- Replaced `dict-counter` hack with `itertools.count()`
- Jinja2 template for HTML reports (replaced 200-line f-string)
- `SCHEMA_BUILDERS` dispatch dict replaced 15-branch elif chain
- `_check_public_url()` / `require_public_url` decorator replaced 10+ walrus patterns
- Rate-limit + exponential backoff for GSC URL inspection (quota exhaustion protection)
- `print()` → `logger` everywhere in Flask import path
- CSV export standardized to 7-col format

---

### v2.1.0 — 2026-06-18
**Security hardening (Batches A–B) + UI/UX + content**

Security fixes (20 items):
- CSRF deny-by-default — was an opt-in allowlist covering only 5 paths
- TOTP brute-force prevention — rate limit + `_record_failed_login`
- Admin user management throttled
- `NO_AUTH=1` blocked on cloud hosts (Render/Fly/Railway/Heroku/GCloud/Azure)
- SSRF guards via `validate_public_url()` + `safe_requests_get()`
- XXE/OOB-fetch blocked: `XMLParser(resolve_entities=False, no_network=True)`
- OpenAPI spec gated behind auth
- `next` param tightened against open redirect
- STARTTLS enforced (no cleartext fallback)
- Dockerfile base image pinned by SHA256 digest
- CI actions SHA-pinned (not tag-pinned)
- COOP / CORP / Permissions-Policy headers added
- `_failed_attempts` dict TTL-capped (unbounded memory growth)
- Login history paginated (was flat 500-row read)
- Configurable `SEO_SUITE_LIMITER_URI` for Redis-backed rate limiting

UI/UX fixes (12 items):
- 4 undefined CSS variables (`--surface-1`, `--bg-2`, `--c-surface2`, `--c-border2`) defined
- Skip link added for keyboard accessibility
- `<span class="label">` → `<label for="...">` for screen reader compatibility
- Modal ARIA roles (`role="dialog"`, `aria-modal`, `aria-label="Close"`)
- Sidebar collapse state persisted to localStorage
- Mobile bottom nav dead link corrected
- `dashboard.js?v=VERSION` cache-busting on the `/app` route
- `/health` endpoint now returns `version` field (nav logo was showing "v?")

Content:
- H1 benefit-led rewrite: "Run technical SEO audits free. No SaaS fees, no data leaks."
- Per-page meta descriptions added
- Stub pages: `/privacy`, `/terms`, `/changelog`
- Blog pillar posts, trust signals, CTA hierarchy fix

---

### v2.0.0 — 2026-06-17
**Initial public-ready release**

Core features: Indexing checker, 7 use-case SEO audit (SSE streaming), 40+ tools, GSC integration, Schema/robots/sitemap/hreflang generators, IndexNow, AI assistant (Groq), multi-user + TOTP, reports (HTML/Excel/CSV/PDF), dark mode.

---

## Open Items

### Security
| ID | Priority | Item |
|---|---|---|
| S15 | LOW | Playwright `--no-sandbox` on attacker HTML — fix: remove or use user namespace sandboxing |
| S-NEW | MED | Migrate ~1000 inline `onclick` handlers to `addEventListener` so CSP `unsafe-inline` can be removed |

### Code Quality
| ID | Priority | Item |
|---|---|---|
| C20 | LOW | `generate_html` 200-line f-string → Jinja2 template (`core/checker.py:30474`) |
| C24 | LOW | Three URL-validation idioms (`_reject_unsafe`, `_require_public_url`, `is_safe_url`) — consolidate to one |
| C25 | LOW | `/api/reports/*` responses missing `ok` key — standardize shape |

### Product / UX
| ID | Priority | Item |
|---|---|---|
| P1 | HIGH | First-run onboarding wizard — new users land with zero guidance |
| P2 | HIGH | Client/project grouping in Reports panel — flat timestamp list, no domain label |
| P3 | HIGH | Cross-URL issue aggregation in audit results — no "37 pages missing H1" view |
| P4 | MED | API docs + webhook output for developer users |
| P6 | MED | Multiple schedule slots (currently one job per install) |
| P7 | MED | Team/role management UI in Settings (backend exists, no UI) |
| P8 | LOW | GitHub install link missing from marketing nav/footer |
| P9 | LOW | Screaming Frog CSV not accepted as URL source |

### Content
| ID | Priority | Item |
|---|---|---|
| CT3 | HIGH | Zero trust signals on home page (no GitHub stars, no quotes, no user count) |
| CT11 | LOW | Tone inconsistency across marketing pages |
| U5 | MED | Brand color `#6366f1` hardcoded in two CSS files — should be one token |
| U11 | LOW | Command palette hidden on mobile (no tap-target for search palette) |

---

## Roadmap

### Phase 0 — Must Fix First (Unblocks later features)
1. **Sitemap SSRF fix** — sitemap fetching bypasses safe request wrapper; blocks Sitemap Audit
2. **Schema validation SSRF fix** — blocks Rich Results / Schema Validation UI
3. **Path anchoring consistency** — runtime data splits dirs when app launched outside repo root
4. **Numeric request validation** — malformed payloads → 500s; blocks any new tool endpoints
5. **Use-case sitemap fallback fix** — sitemap mode audits the XML itself when expansion fails
6. **`robots.txt` safe-fetch fix** — fetch still bypasses SSRF wrapper

### Phase 1 — No Paid API (after Phase 0)
- **Rich Results / Schema Validation UI** — backend route exists, just needs UI wiring
- **Sitemap Audit** — in/out of sitemap, orphans, non-indexables, oversized warnings
- **Bing Visibility Workspace** — URL inspection, search performance, sitemap status
- **IndexNow Submission Tool** — action workflow after indexing diagnosis
- **Trend Explorer** — free keyword trend comparison (no paid provider needed)

### Phase 2 — Authenticated Free-Platform Integrations
- **Baseline GSC Opportunity Layer** — high-impression/low-CTR, decay detection, device splits
- **Performance Opportunity Layer** — CWV risk grouping, repeated asset bottlenecks
- **Groq AI Assistance Layer** — explain findings, draft fixes, meta variants (opt-in per panel)

### Phase 3 — Paid / Metered Features
- Content Gap / Competitor Gap
- Backlink Reclamation workflow
- AI Visibility / Citation Tracking
- Paid-enriched GSC Opportunity Layer

**Canonical build order:** Phase 0 → Rich Results → Sitemap Audit → Bing Visibility → IndexNow → Trend Explorer → GSC Opportunity → Performance Opportunity → Groq AI → Content Gap → Backlink Reclamation → AI Visibility → Paid GSC

---

## Architectural Decisions

| Decision | Rationale |
|---|---|
| Single gunicorn worker (`--workers 1`) | SSE queues and run state live in process memory — multiple workers break state |
| Vanilla JS SPA (no React/Vue) | Zero build step, zero NPM; matches the self-hosted philosophy |
| SQLite for users/sessions | Persistent disk required anyway; no external DB dependency for auth |
| `fetch_page()` shared cache (30-min TTL) | Prevents per-check HTTP requests during multi-check audits; ~10 checks share one fetch |
| `validate_public_url()` + `safe_requests_get()` | All user-controlled URL fetches go through SSRF validation — SSRF is the highest-risk attack surface |
| `httpx[http2]` for HTTP/2 detection | `requests` library is HTTP/1.1 only; `httpx` already in requirements |
| `VERSION` in `core/version.py` | Single source of truth; `/app` route injects `?v=VERSION` for cache-busting |
| CSRF deny-by-default | All mutation endpoints protected; exemptions must be explicit (`_CSRF_EXEMPT_PATHS`) |
| `NO_AUTH` blocked on cloud hosts | Guards against accidental public exposure on Render/Fly/Railway/Heroku deploys |

---

_Last updated: 2026-06-22 — v2.6.1_
