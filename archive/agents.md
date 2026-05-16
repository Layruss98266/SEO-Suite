# Agents Guide

## Mission

SEO Suite is a Flask-based SEO auditing and indexing platform with long-running background jobs, live progress streaming, local report generation, and multiple external integrations.

When working in this repo, prioritize:

- correctness over cleverness
- SSRF-safe server-side fetching
- stable long-running job behavior
- clear user-facing failure modes
- minimal, focused changes over broad refactors

## Architecture

### Main server

- `app/server.py`
  - primary Flask server
  - route handlers
  - SSE streaming
  - shared in-memory run state
  - uploads, reports, settings, profiles

### Indexing system

- `core/checker.py`
  - sitemap/domain/CSV input handling
  - indexing workflows
  - Playwright execution
  - indexing report generation
  - history/progress persistence

### Security layer

- `core/security.py`
  - SSRF validation
  - safe HTTP wrappers
  - HTML escaping helpers

### Audit system

- `core/seo_audit.py`
  - audit orchestration
  - use-case definitions
  - scoring logic
  - audit report generation

### Point tools

- `tools/`
  - quick tools
  - API-backed integrations
  - generators
  - validation utilities

### Frontend

- `app/templates/dashboard.html`
  - dashboard structure and panel layout
- `app/static/js/dashboard.js`
  - fetch calls
  - UI state
  - panel rendering
  - use-case/task definitions

### Runtime model

- indexing and audit runs execute in background threads
- progress is streamed over SSE
- most run state is stored in process memory
- reports, uploads, progress, and history are written to disk

## Non-Negotiable Safety Rules

### URL handling

Do:

- validate user-supplied URLs with `validate_public_url()`
- use `safe_requests_get()` or `safe_requests_head()` for user-controlled fetches
- treat redirects as security-sensitive
- assume sitemap URLs, schema URLs, and uploaded URL lists are hostile until validated

Do not:

- use raw `requests.get(..., allow_redirects=True)` for user input
- use raw `urllib.request.urlopen()` for user input without preserving redirect safety
- introduce new fetch paths that bypass `core/security.py`

### Filesystem behavior

Do:

- prefer project-root-anchored paths
- reuse existing root/data path patterns
- keep report and upload paths inside intended directories

Do not:

- add new cwd-relative `Path("data/...")` or `Path("config.json")` patterns
- weaken path traversal protections

## Concurrency Rules

- shared globals in `app/server.py` must be read or written under the correct lock
- preserve pause/resume/cancel behavior for indexing and audit runs
- preserve queue bounds for SSE subscribers
- preserve caps on partial result buffers unless the task explicitly changes memory behavior
- prefer locked in-place updates over reassigning shared dict/list objects

Examples of concurrency-sensitive areas:

- `_last_index_run`
- `_index_status`
- `_audit_status`
- `_audit_partial`
- `_audit_full_results`
- SSE subscriber queues

## Request Validation Rules

Do:

- return `400` for malformed client input
- validate JSON payload shape early
- guard all numeric parsing from request payloads
- preserve current response shapes unless the API contract is intentionally changing

Do not:

- let invalid `limit`, `workers`, `top_n`, `location_code`, or similar inputs raise uncaught `ValueError`
- turn ordinary client mistakes into `500` responses

## Frontend Coordination

Backend-only changes are often incomplete in this repo.

If a feature is meant to be user-facing, usually all of these are needed:

- a Flask route in `app/server.py`
- a visible entry or panel in `app/templates/dashboard.html`
- fetch/render/state logic in `app/static/js/dashboard.js`

Before adding a new user feature:

- check whether a matching panel already exists
- check whether a backend route already exists but is hidden from the UI
- keep response shapes compatible with current frontend expectations

## Testing Guidance

Run:

- `pytest -q`

Prefer adding or updating tests in:

- `tests/test_server.py`
  - route-level validation and integration behavior
- `tests/test_review_fixes.py`
  - regression coverage for known review findings
- `tests/test_security_fixes.py`
  - SSRF, traversal, and hardening coverage
- `tests/test_checker.py`
  - indexing/checker helper behavior
- `tests/test_quick_tools.py`
  - point tool behavior

Add tests whenever you change:

- request parsing
- URL safety logic
- upload handling
- report path handling
- run-state behavior
- retry/cancel/pause/resume logic
- sitemap or schema fetching behavior

## Known Risk Areas

Highest-risk areas in this repo:

- sitemap fetching and redirect handling
- schema validation fetches
- upload parsing and path validation
- shared run-state structures used by background threads
- config/data/report path consistency between modules
- external API timeout and failure handling

## Current Hotspots

These are already-known trouble spots and should be checked before related edits:

- sitemap SSRF path
  - `core/checker.py` sitemap fetching still needs careful review
- schema validation SSRF path
  - `tools/schema_validator.py` must not follow unsafe redirects
- cwd-relative path drift
  - some paths are anchored, others are still cwd-relative
- unguarded `int(...)` parsing
  - several routes still risk `500` on bad input

## Good Working Defaults

- make the smallest change that fully solves the problem
- reuse existing helpers before adding new abstractions
- prefer explicit validation and clear errors
- if a task touches crawling, redirects, uploads, or report files, assume it is security-sensitive
- if a task touches run state or SSE, assume it is concurrency-sensitive
- avoid broad refactors unless they are necessary for the task

## Deliverables

A good change in this repo usually includes:

- focused code changes
- preserved or improved error handling
- no new unsafe fetch path
- no accidental path drift
- updated tests when behavior changes
