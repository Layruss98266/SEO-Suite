# SEO Suite Architecture

This document describes how SEO Suite is structured: the request flow, where state lives, how the SSE streaming works, the security model, and the threading model.

For setup and usage, see [README.md](README.md). For contributing conventions, see [CONTRIBUTING.md](CONTRIBUTING.md).

---

## High-Level Picture

```
┌──────────────────────────────────────────────────────────────────────┐
│                          Browser (single tab)                         │
│                                                                       │
│  Dashboard SPA  ←—— SSE stream ——  Live progress + completion events  │
└──────────────────────────────────────────────────────────────────────┘
                                  │
                                  │ HTTP / SSE
                                  ▼
┌──────────────────────────────────────────────────────────────────────┐
│                    Single Flask process (1 worker, N threads)         │
│                                                                       │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌────────────┐      │
│  │ Blueprints │  │  Routes    │  │ Middleware │  │   Limiter  │      │
│  │ (site,     │  │ (indexing, │  │ (CSRF,     │  │ (per-IP    │      │
│  │  auth,     │  │  audit,    │  │  CSP,      │  │  rate caps)│      │
│  │  misc)     │  │  tools,    │  │  HSTS)     │  │            │      │
│  │            │  │  reports,  │  │            │  │            │      │
│  │            │  │  settings) │  │            │  │            │      │
│  └─────┬──────┘  └─────┬──────┘  └────────────┘  └────────────┘      │
│        │               │                                              │
│        └───────┬───────┘                                              │
│                ▼                                                       │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │                       app/state.py                            │   │
│  │  In-process state shared across all routes/threads:          │   │
│  │    • SSE subscriber queues (_index_subscribers, ...)         │   │
│  │    • Run status dicts    (_index_status, _audit_status)      │   │
│  │    • Cancel/pause events                                     │   │
│  │    • Partial result buffers                                  │   │
│  │    • Locks (_lock, _sub_lock)                                │   │
│  │    • Path constants (PROJECT_ROOT, DATA_DIR, REPORTS_DIR)    │   │
│  │    • Helper functions (_int, _norm_url, _safe_report_path)   │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                │                                                       │
│                ▼                                                       │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │                     core/  +  tools/                          │   │
│  │   Pure-Python business logic — no Flask, no shared state     │   │
│  │   (checker, seo_audit, security, auth, phase1-4, etc.)       │   │
│  └──────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────────┘
        │                       │                          │
        ▼                       ▼                          ▼
   data/reports/         data/users.json          data/profiles.json
   (HTML, XLSX, CSV,     (auth)                   (saved audit configs)
    JSON sidecars)
```

---

## Module Layout

```
app/
├── server.py              ← Slim Flask factory (~165 lines) — app construction
│                            + CORS + Sentry + limiter + blueprint registration
├── state.py               ← Shared state, paths, helpers, constants
├── middleware.py          ← Security headers, CSRF, error handlers
├── __init__.py            ← create_app() factory wrapper
├── blueprints/            ← Every route lives here, grouped by domain
│   ├── site.py            ← /, /features, /pricing, /blog, /about, /contact
│   ├── auth_views.py      ← /login, /signup, /logout, /api/users, /api/auth_status
│   ├── misc.py            ← /app, /health, /health/ready, /api/use_cases, /api/tasks
│   ├── reports.py         ← /api/reports/*, /api/open, /api/download, /api/history, PDF
│   ├── settings.py        ← /api/settings, /api/profiles, /api/upload, /api/compare
│   ├── tools.py           ← /api/tools/* (33 routes)
│   ├── indexing.py        ← /api/index/* (run/stream/cancel/pause/resume/retry/partial)
│   ├── audit.py           ← /api/audit/* (run/stream/cancel/pause/resume/partial/phase)
│   └── runners.py         ← /api/usecase/run, /api/usecase/run_bulk
├── templates/
│   ├── dashboard.html     ← Single-page app shell for /app
│   └── site/              ← Marketing site templates
└── static/
    ├── css/
    └── js/
core/
├── server.py              (none — historical; logic is in core/checker.py etc.)
├── checker.py             ← Google indexing checker (Playwright + GSC API fallback)
├── seo_audit.py           ← Audit orchestrator (use cases, tasks, scoring)
├── security.py            ← SSRF guards, DNS rebinding mitigation, safe HTTP wrappers
├── auth.py                ← Session auth, password hashing, account lockout
├── notifier.py            ← Email / Slack / Teams webhooks
├── report_generator.py    ← HTML / XLSX / CSV builders
├── sitemap_parser.py      ← Sitemap XML fetch + parse
└── version.py             ← Single source of truth for VERSION
tools/
├── phase1.py              ← Technical SEO (no API)
├── phase2.py              ← PageSpeed / Core Web Vitals
├── phase3.py              ← Google Search Console (clicks, queries, sitemaps)
├── phase4.py              ← Backlinks / Authority / Rankings (Moz, DataForSEO, SerpAPI)
├── generators.py          ← Schema, robots.txt, sitemap, hreflang, meta
├── quick_tools.py         ← SERP preview, headers, redirect chain, etc.
├── bing_webmaster.py      ← Bing API wrapper
├── ai_assist.py           ← Groq LLM integration
├── schema_validator.py    ← JSON-LD / microdata validation
├── connection_tests.py    ← "Test connection" handlers for Settings UI
└── _common.py             ← Shared safe_error() and helpers
```

---

## Request Flow

### A typical request to `POST /api/audit/run`

```
1. HTTP request arrives at gunicorn (or Flask dev server)
2. Flask routes to api_audit_run() in app/server.py
3. @login_required decorator checks session — bounces to /login if absent
4. @limiter.limit("10 per hour") — flask-limiter counts per-IP
5. Middleware @app.before_request fires:
     - _csrf_protect: skipped for JSON API requests (only HTML forms checked)
6. Route handler:
     a. Validates request body (JSON shape, required fields)
     b. _norm_url() + is_safe_url() — SSRF guard if input is a URL
     c. _int() — clamp numeric fields to safe ranges
     d. Atomic check + set state._audit_status["running"] under _lock
     e. Spawns daemon thread to do the actual work
     f. Returns 202 with estimated total + workers count
7. Worker thread:
     a. Fetches URLs (sitemap parse, domain crawl, or upload load)
     b. Resolves GSC service if enabled
     c. ThreadPoolExecutor(max_workers=N) running audit_single_url per URL
     d. After each URL: _audit_queue.put(progress) — broadcasts to SSE subscribers
     e. After all URLs: writes HTML + JSON + XLSX reports, broadcasts done
     f. Finally: _audit_status["running"] = False under _lock
8. Middleware @app.after_request fires:
     - _set_security_headers: CSP, X-Frame-Options, HSTS, etc.
```

### A typical SSE subscription

```
GET /api/audit/stream
  ↓
@limiter.exempt   ← long-lived connection, never counted against rate cap
@login_required
  ↓
sub = _subscribe(_audit_subscribers)   ← new bounded Queue(maxsize=1000)
  ↓
gen():
  while True:
    try:
      msg = sub.get(timeout=30)        ← block up to 30s
      yield f"data: {json.dumps(msg)}\n\n"
      if msg.type in ("done", "error", "cancelled"): break
    except queue.Empty:
      yield 'data: {"type":"ping"}\n\n'   ← keepalive
  ↓
finally: _unsubscribe(_audit_subscribers, sub)
```

A background daemon thread sweeps stale (full) queues every 5 minutes.

---

## State Management

### Where State Lives

| State | Module | Purpose |
|-------|--------|---------|
| `_index_status`, `_audit_status` | `app/state.py` | Dicts mutated in place; never reassigned (so test monkey-patches survive) |
| `_lock`, `_sub_lock` | `app/state.py` | Coarse-grained mutexes guarding all status mutations |
| `_index_subscribers`, `_audit_subscribers` | `app/state.py` | Lists of per-client `queue.Queue` for SSE |
| `_index_cancel`, `_audit_cancel` | `app/state.py` | `threading.Event` — set to request cancellation |
| `_index_paused`, `_audit_paused` | `app/state.py` | `threading.Event` — clear to pause, set to resume |
| `_audit_partial`, `_audit_full_results` | `app/state.py` | Per-URL result buffers; capped at `MAX_AUDIT_RESULTS=5000` |
| `CFG` | `app/state.py` | Mutable dict mirroring `config.json`; updated on `/api/settings POST` |
| Flask `session` | Per-request | Authed user, CSRF token (signed cookie, server-side memory in Flask) |

### Single-Process Constraint

**SEO Suite runs as one process, period.** Run state lives in process memory:

- SSE queues — can't split across workers (one tab would miss events fired in another worker)
- Run status — can't split across workers (two `/api/audit/run` could both pass the "already running?" check)

This is why `gunicorn --workers 1 --threads 8` is the only supported topology. The Dockerfile, fly.toml, and render.yaml all enforce single-instance deployment.

Scale **up** (CPU/RAM), not **out**.

To move to multiple instances eventually, you'd need:
1. Redis (or similar) for `_index_subscribers` / `_audit_subscribers`
2. Redis-backed `flask-limiter` storage
3. Atomic `_lock` replacement (e.g. Redis SETNX)
4. Job queue (Celery/RQ) for the audit worker thread

None of this is done yet.

---

## Security Model

### Auth Layers

1. **Session-based** — Flask sessions signed with `SEO_SUITE_SECRET`, HttpOnly + SameSite=Lax cookies
2. **Password hashing** — werkzeug `scrypt`, 32768 cost factor
3. **Account lockout** — 10 failed attempts in 15 min → 15 min lock (`core/auth._is_locked_out`)
4. **Rate limiting** — `/login` 5/min, `/signup` 10/min, `/api/audit/run` 10/hour, others 240/min default

### SSRF Protection

The big risk vector: SEO Suite fetches user-supplied URLs server-side (audit, indexing, tools).

- `core/security.validate_public_url()` — rejects localhost, RFC1918, link-local, multicast, cloud metadata IPs
- `core/security.safe_requests_get/head/post()` — re-validates every redirect hop
- `core/security._pinned_create_connection` — monkey-patches urllib3 to re-check the resolved IP at TCP connect time (defends against DNS rebinding)

### Path Traversal

- `app/state._safe_report_path(name, exts)` — every download/open/PDF route routes through this
- `app/state._safe_upload_path(raw)` — verifies uploads stay under `data/uploads/`
- Filename regex: `^[\w\-]+(?:\.[\w\-]+)*$`

### CSRF

- Form POSTs to `/login`, `/signup`, `/contact` require `_csrf_token` matching session token
- JSON API requests are exempt (no cross-origin form attack vector with SameSite=Lax)
- Token generated lazily via `app/middleware.generate_csrf_token()`, exposed to Jinja as `csrf_token()`

### Headers

Applied to every response by `app/middleware._set_security_headers`:

- `Content-Security-Policy` — restricts script/style/font origins
- `X-Frame-Options: DENY` — anti-clickjacking
- `X-Content-Type-Options: nosniff`
- `Referrer-Policy: strict-origin-when-cross-origin`
- `Strict-Transport-Security` — only when `SEO_SUITE_COOKIE_SECURE=1`

---

## Threading Model

```
Main thread          Gunicorn dispatches HTTP requests to threads
  │
  ├── SSE cleanup thread (daemon, every 5 min)
  │     Drops stale (full) subscriber queues
  │
  ├── Request thread N (handles one HTTP request)
  │
  ├── Audit worker thread (daemon, one per /api/audit/run)
  │     └─ ThreadPoolExecutor(max_workers=workers)
  │          ├─ Per-URL audit task 1
  │          ├─ Per-URL audit task 2
  │          └─ ...
  │
  ├── Indexing worker thread (daemon, one per /api/index/run)
  │     └─ Playwright browser pool internally
  │
  └── SSE response thread (daemon, one per /api/{index,audit}/stream)
        Pulls from its subscriber queue, yields data: lines
```

### Concurrency Invariants

| Invariant | Enforced by |
|-----------|-------------|
| At most one indexing run at a time | `_lock` + `_index_status["running"]` check |
| At most one audit run at a time | `_lock` + `_audit_status["running"]` check |
| At most `SEO_SUITE_PDF_WORKERS` (=2) PDF exports concurrently | `_pdf_semaphore` |
| Audit threads see cancel within ~1 future-completion | `_audit_cancel.is_set()` checks before submit + after result |
| Cancel/pause survives multiple workers | `threading.Event` is process-shared and thread-safe |

---

## Data Persistence

| Store | Backend | Purpose |
|-------|---------|---------|
| `data/seo_suite.db` (table `users`) | **SQLite (WAL)** | User accounts (hashed passwords, admin flags, created_at). Migrated from `users.json` on first read. |
| `data/profiles.json` | JSON | Saved audit configurations |
| `data/history.json` | JSON | Indexing run history (for trend chart) |
| `data/reports/*.html` | HTML | Audit + indexing reports (primary file) |
| `data/reports/*.xlsx` | XLSX | Audit Excel reports |
| `data/reports/*.csv` | CSV | Indexing reports + audit partial exports |
| `data/reports/*.json` | JSON | Audit sidecar (avg score, totals) |
| `data/uploads/*.csv` | CSV | User-uploaded URL lists (sanitized of formula injection) |
| `config.json` | JSON | Non-secret settings + API keys (latter masked in GET responses) |
| `.env` | KV | Secrets (DB-style: gitignored) |

### Why SQLite for users (and not the rest)

The user store has the strictest atomicity needs:

- A torn write would lock everyone out
- Concurrent reads must not block (login is hot path)
- We want indexed `WHERE username = ?` lookups as the table grows

SQLite gives us atomic transactions, WAL-mode read concurrency, and indexed
lookups for free. The migration is opportunistic — see `core/db.py`:
`load_users()` checks if the table is empty and imports `users.json` on
first read, then renames the file to `.migrated` so it isn't re-imported.

`profiles.json` and `history.json` stay as JSON for now — they're rarely
written and never read on the auth hot path.

### Rollback

If SQLite causes problems, force the legacy JSON backend:

```bash
SEO_SUITE_USERS_BACKEND=json python main.py
```

This skips the SQLite path entirely and reads/writes `users.json`. Rename
`users.json.migrated` back to `users.json` first to recover the data.

---

## Observability

- **Logging** — Python `logging` to stdout + `data/app.log`. Set
  `SEO_SUITE_LOG_JSON=1` to emit structured JSON logs (ELK / Datadog / Loki
  pipelines) via `python-json-logger`. Falls back to text format if the lib
  isn't installed.
- **Sentry** — Opt-in via `SENTRY_DSN` env var; 5% transaction sampling.
- **Liveness probe** — `GET /health` returns `{"status":"ok"}`
  (intentionally minimal — no run state, no version, no auth).
- **Readiness probe** — `GET /health/ready` checks the data directory is
  writable and that the `reports/` + `uploads/` sub-directories exist.
  Returns 200 + `{"status":"ok","checks":{...}}` when healthy, 503 +
  per-check failure details when degraded.
- **Prometheus metrics** — `GET /metrics` (unauthenticated; restrict at the
  network layer in prod). Exports:
  - `http_requests_total{method,endpoint,status}` — counter
  - `http_request_duration_seconds{method,endpoint}` — histogram
  - `audit_runs_total{status="started|completed|cancelled|error"}` — counter
  - `indexing_runs_total{status=...}` — counter
  - `audit_running`, `indexing_running` — 0/1 gauges
  - `sse_subscribers{stream="audit|indexing"}` — gauge
  - Default Python process metrics (memory, GC, threads)

  The endpoint refreshes gauges from live state on each scrape. Returns 503
  if `prometheus-client` isn't installed (`pip install prometheus-client`).

Future:

- GSC credentials + Sentry DSN reachability in the readiness probe

---

## Build & Deploy

### Local dev

```bash
python main.py   # http://localhost:8080
```

### Production WSGI

```bash
gunicorn --workers 1 --threads 8 --worker-class gthread --timeout 300 \
  --bind 0.0.0.0:8080 app.server:app
```

The Dockerfile uses the official Playwright Python image as a base, copies the app, installs Chromium, exposes 8080. See [DEPLOYMENT.md](DEPLOYMENT.md) for Render / Fly.io / Docker recipes.

---

## Testing

- **238 tests** under `tests/` covering routes, security, tools, generators, audit, indexing, settings, users
- **`pytest-cov`** available for coverage reports
- **`conftest.py`** disables rate limiting + zeroes auth env vars so tests don't trip session checks
- **Fixtures** monkey-patch `app.server._audit_status` etc. — relies on dict identity being preserved by the refactor (status dicts are mutated in place, never reassigned)

---

## API Versioning

Every `/api/<path>` route is mirrored under `/api/v1/<path>` by a small loop
at the bottom of `app/server.py`. The aliasing is purely additive — the
unversioned routes stay as the default for the bundled dashboard and any
existing integrations. New clients should target `/api/v1/*` so future
breaking changes can ship as `/api/v2/*` without forcing migrations.

The aliases share view functions with the original routes (Flask
`add_url_rule` re-points the same callable under a `v1.<endpoint>` name), so
there's no code duplication or maintenance burden when the underlying handler
changes.

## Open Architecture Questions

These are real trade-offs, not just TODOs. Open for discussion:

1. **Job queue vs. in-process threads** — current setup loses work if the server restarts mid-audit. Moving to RQ/Celery adds an ops burden (Redis) but enables proper retry semantics and multi-instance deploys.

2. **Per-user data isolation** — currently all users share `data/`. Should each user get a scoped subdirectory? (Probably yes for SaaS, no for self-hosted single-team.)

3. **GSC quota management** — a busy account can hit the URL Inspection rate limit. We currently fall back to browser-based checks per URL; a fairer approach would be to coalesce + backoff at the service layer.

4. **Frontend state management** — `dashboard.js` is ~3000 lines of vanilla JS with growing complexity. Worth migrating to Alpine.js/HTMX before it gets unmanageable? Or TypeScript?

5. **Test coverage** — 238 tests is a lot, but coverage gaps likely exist in `app/server.py` routes that need integration tests. Run `pytest --cov` to find out.
