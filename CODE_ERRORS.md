# Code Errors

## Review Snapshot

- Review date: 2026-05-15
- Scope: `app/server.py`, `core/*`, `tools/*`, tests
- Current test status: `111 passed`
- Planning status:
  - these findings are now the blockers referenced by [TOOL_ROADMAP.md](D:/Coding/SEO%20Suite/TOOL_ROADMAP.md)
- Note:
  - several issues below are not covered by the current test suite

## Why These Matter Now

These are not just isolated bugs. They block safe expansion of the product across the current dashboard surfaces:

- use cases: Crawl Access, Search Console, Rankings, future Bing Visibility
- tools: hidden Schema Validation, future IndexNow, future Trend Explorer
- generators: especially `robots.txt` and XML Sitemap workflows that users will naturally connect to validation and audit features

## Task Logic Review Notes

The current use-case task model already exists in both the frontend and backend:

- frontend task definitions: [dashboard.js](D:/Coding/SEO%20Suite/app/static/js/dashboard.js:26)
- backend task definitions: [core/seo_audit.py](D:/Coding/SEO%20Suite/core/seo_audit.py:63)

The biggest logic issues are not crashes, but planning and UX mismatches:

- `performance` currently includes a task with ID `crawlability` labeled `GSC URL inspection`
  - this mixes performance and crawl semantics in one place
- `search_console` is too thin
  - only `clicks_impressions` and `top_queries` are exposed today
- `authority` and `rankings` are too compressed
  - they do not yet reflect the richer sub-workflows the roadmap expects
- some checks likely need clearer ownership
  - for example `ttfb` appears under On-Page SEO even though users may expect it under Performance

Suggested direction:

- keep default task sets simple
- split richer logic into clearer sub-checks where the backend already supports or can support it
- preserve task-ID parity between `dashboard.js` and `core/seo_audit.py`
- add tests whenever task IDs, labels, grouping, or prerequisites change

## 1. High - SSRF bypass in sitemap fetching

- Files:
  - `core/checker.py`
  - `app/server.py`
- Key lines:
  - `core/checker.py:140-191`
  - `app/server.py:323-345`
  - `app/server.py:471-485`
- Problem:
  - `fetch_sitemap_urls()` uses `urllib.request.urlopen()` directly instead of `safe_requests_get()`.
  - Redirect targets and nested sitemap targets are not re-validated hop by hop.
  - The indexing and audit routes call this function for user-controlled sitemap/domain inputs.
- Impact:
  - a public sitemap URL can redirect the server into private or metadata endpoints
  - Crawl Access and any future Sitemap Audit work inherit this risk
  - Bing-style sitemap intelligence should not be added on top of this fetch path
- Recommended fix:
  - replace raw sitemap HTTP fetches with `safe_requests_get()`
  - or route all sitemap loading through one hardened sitemap parser
- Roadmap effect:
  - blocks `Sitemap Audit`
  - partially blocks `Bing Visibility Workspace`

## 2. High - SSRF bypass in schema validation

- File:
  - `tools/schema_validator.py`
- Key lines:
  - `tools/schema_validator.py:175-188`
- Problem:
  - the initial URL is validated once, then fetched with `requests.get(..., allow_redirects=True)`
  - redirect targets are not re-checked for public safety
- Impact:
  - `/api/tools/schema_validate` can be used to follow a public URL into internal/private addresses
  - exposing the schema validator as a visible tool would amplify the risk
- Recommended fix:
  - replace the raw `requests.get()` call with `safe_requests_get()`
- Roadmap effect:
  - blocks `Rich Results / Schema Validation UI`

## 3. Medium - Inconsistent path anchoring splits runtime state

- Files:
  - `app/server.py`
  - `core/checker.py`
  - `core/seo_audit.py`
- Key lines:
  - `app/server.py:101-109`
  - `app/server.py:971-973`
  - `core/checker.py:88-102`
  - `core/seo_audit.py:35`
- Problem:
  - the Flask app now anchors some paths to `PROJECT_ROOT`, but other paths still use cwd-relative values like `Path("data/uploads")`, `Path("data/profiles.json")`, `Path("data")`, `Path("config.json")`, and `Path("data/reports")`
  - settings may be read from one location while uploads, profiles, reports, history, and progress are written elsewhere
- Impact:
  - launching the app outside repo root can create split config/data folders
  - report discovery, resume behavior, profile loading, and settings persistence can diverge
  - new integrations that write logs or cached results become harder to support
- Recommended fix:
  - centralize a shared project-root path helper
  - use it for config, upload, report, history, profile, and progress paths
- Roadmap effect:
  - blocks or partially blocks `Bing Visibility Workspace`, `IndexNow Submission Tool`, and report-heavy new tools

## 4. Medium - Unguarded numeric parsing returns 500 on bad client input

- File:
  - `app/server.py`
- Key lines:
  - `app/server.py:306`
  - `app/server.py:443`
  - `app/server.py:447`
  - `app/server.py:476`
  - `app/server.py:1256`
  - `app/server.py:1312-1315`
- Problem:
  - several routes call `int(...)` directly on user input
  - invalid payloads like `"limit": "abc"` or `"top_n": "ten"` raise `ValueError` and bubble into 500s
- Impact:
  - clients get server errors for ordinary validation mistakes
  - the same pattern is likely to spread into new paginated, filtered, or threshold-based tools if left alone
- Recommended fix:
  - add a small coercion helper that validates bounds and returns `400` JSON errors consistently
- Roadmap effect:
  - partially blocks `Bing Visibility Workspace`, `IndexNow Submission Tool`, and `Trend Explorer`

## 5. Medium - Use-case sitemap mode audits the sitemap itself on fetch failure

- File:
  - `app/server.py`
- Key lines:
  - `app/server.py:1139-1145`
- Problem:
  - in `/api/usecase/run`, `input_format == "sitemap"` resolves the first sitemap URL, but if no URLs are found it falls back to `raw_url`
  - that means the app can run a content audit against the sitemap XML URL itself instead of returning a clear error
- Impact:
  - users can get misleading audit results for XML documents instead of the intended page URL
  - sitemap-driven Crawl Access or future sitemap reporting becomes less trustworthy
- Recommended fix:
  - return a `400` when the sitemap resolves to zero valid URLs instead of falling back to the sitemap source URL
- Roadmap effect:
  - blocks clean `Sitemap Audit` and weakens Crawl Access trust

## 6. Medium - Upload/profile paths are still cwd-relative in the Flask app

- File:
  - `app/server.py`
- Key lines:
  - `app/server.py:971-973`
  - `app/server.py:1027`
- Problem:
  - `UPLOAD_DIR` and `PROFILES_PATH` still use `Path("data/...")` instead of the already-established `PROJECT_ROOT` / `DATA_DIR`
- Impact:
  - running the server from another working directory can save uploaded files and profiles to a different tree than the rest of the app uses
  - user-facing profile and file workflows become inconsistent
- Recommended fix:
  - rebase both constants onto `DATA_DIR`
- Roadmap effect:
  - contributes to the broader path-consistency blocker

## 7. Medium - `robots.txt` fetching still bypasses the SSRF-safe request layer

- File:
  - `tools/phase1.py`
- Key lines:
  - `tools/phase1.py:90-99`
- Problem:
  - `robots_check()` relies on `urllib.robotparser.RobotFileParser.read()`, which fetches `robots.txt` internally and does not use `safe_requests_get()`
  - the base page URL is public, but redirect handling for `/robots.txt` is not controlled by the app's SSRF guards
- Impact:
  - a hostile public host can redirect `robots.txt` fetches toward internal addresses
  - Crawl Access should not expand while this fetch path remains inconsistent
- Recommended fix:
  - fetch `robots.txt` through the safe wrapper first
  - parse the content manually instead of calling `RobotFileParser.read()`
- Roadmap effect:
  - blocks safer Crawl Access expansion
  - makes future `robots.txt` validator/tester work riskier

## 8. Low - Settings refresh does not propagate through every consumer path

- Files:
  - `app/server.py`
  - `tools/phase2.py`
- Key lines:
  - `app/server.py:961-964`
  - `tools/phase2.py:16-27`
- Problem:
  - `/api/settings` refreshes `CFG` in `app.server`, `core.checker`, and `core.seo_audit`, but some consumers reload config indirectly from `core.checker.load_config()`, which is itself cwd-relative
- Impact:
  - threshold-driven behavior can diverge after settings changes when cwd-relative config resolution does not match the Flask app's anchored config path
- Recommended fix:
  - fix the central path anchoring first
  - then make config consumers read from a single canonical source
- Roadmap effect:
  - mostly a follow-on cleanup after path normalization

## Fix Order

Use this order unless a higher-priority regression appears:

1. Sitemap SSRF fix
2. Schema validation SSRF fix
3. Path anchoring consistency
4. Numeric request validation
5. Use-case sitemap fallback fix
6. `robots.txt` safe-fetch fix
7. Upload/profile path cleanup
8. Settings refresh consistency

## Test Gaps To Add

- route-level tests for malformed numeric payloads
- redirect-safety tests for sitemap fetching
- redirect-safety tests for schema validation
- use-case sitemap zero-result tests
- path-anchoring tests for uploads, profiles, and reports
- `robots.txt` safe-fetch regression coverage

## Current Test Inventory

Existing tests already cover a useful amount of function and route behavior:

- [tests/test_server.py](D:/Coding/SEO%20Suite/tests/test_server.py)
  - health route
  - dashboard route
  - upload validation
  - audit-run validation
  - settings API basics
- [tests/test_checker.py](D:/Coding/SEO%20Suite/tests/test_checker.py)
  - `filter_urls`
  - `get_crawl_depth`
  - `get_url_type`
  - `get_priority_score`
  - `_normalize_url`
  - `compare_runs`
  - `load_from_csv_excel`
- [tests/test_security_fixes.py](D:/Coding/SEO%20Suite/tests/test_security_fixes.py)
  - `esc`
  - `is_safe_url`
  - report escaping
  - cancel race behavior
  - settings whitelist behavior
- [tests/test_review_fixes.py](D:/Coding/SEO%20Suite/tests/test_review_fixes.py)
  - path traversal blocking
  - auth gating
  - run-flag race protection
  - PDF concurrency behavior
  - `_is_error_status`
  - progress-key stability
  - crawler safe-fetch usage
- [tests/test_quick_tools.py](D:/Coding/SEO%20Suite/tests/test_quick_tools.py)
  - `_attr_text`
- [tests/test_phase4.py](D:/Coding/SEO%20Suite/tests/test_phase4.py)
  - `result`
  - `audit_url`
  - keyword-triggered task additions
- [tests/test_keyword_research.py](D:/Coding/SEO%20Suite/tests/test_keyword_research.py)
  - `normalize_keyword`
  - `normalize_intent`
  - DataForSEO mapping helpers
  - `research_keywords`

## Highest-Value Additional Tests

- task-definition parity tests
  - assert task IDs in `dashboard.js` and `core/seo_audit.py` stay aligned
- use-case task selection tests
  - ensure selected tasks are the only ones run
- prerequisite-behavior tests
  - credentials missing should skip or warn predictably for Search Console, Performance, Authority, and Rankings
- task-label ownership tests
  - especially around Performance vs Crawl Access vs Search Console overlap
- schema-validation route tests
  - malformed URL, blocked redirect, and safe-success cases
- Search Console and Performance derived-insight tests
  - once those opportunity layers are added
