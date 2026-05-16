# Repository Review & Cleanup

## Review Snapshot

- Review date: 2026-05-15
- Scope: `app/server.py`, `core/*`, `tools/*`, tests
- Current test status: `111 passed`
- Planning status:
  - these findings are now the blockers referenced by [TOOL_ROADMAP.md](D:/Coding/SEO%20Suite/TOOL_ROADMAP.md)
- Note:
  - several issues below are not covered by the current test suite

> Note: this file is a review artifact used for planning and documentation only. It is not required by the application runtime and may be deleted if you want to remove review notes. If deleted, consider removing the link from `TOOL_ROADMAP.md`.

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

## 1. Medium - Inconsistent path anchoring splits runtime state

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

## 2. Medium - Unguarded numeric parsing returns 500 on bad client input

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

## Repository Cleanup Recommendations

This section summarizes files that look obsolete, redundant, or better archived outside the root of the repository.

### Highest-confidence deletions
These files are safe to remove and are not part of the active application surface.

- `dashboard.py`
  - Legacy entrypoint replaced by `main.py`.
  - `PROJECT_ANALYSIS.md` explicitly calls this file out as legacy.
  - No active source references to it exist in the codebase.

- `README.html`
  - Redundant generated copy of `README.md`.
  - If the repo is intended to use Markdown-based documentation, the HTML file is not needed.

### Strong archive/pruning candidates
These are planning, research, and review artifacts that may still be useful internally, but they clutter the root and can be moved to an `archive/` or `docs/` folder if kept.

- `CODE_REVIEW.md`
- `FREE_TOOLS_RESEARCH.md`
- `PROJECT_ANALYSIS.md`
- `GITHUB_REFERENCE.md`
- `INSTALL_PACKAGES.md`
- `RECOMMENDED_PACKAGES.md`
- `agents.md`

> Note: Some of these files are still referenced by `TOOL_ROADMAP.md` and possibly by internal planning workflows. If you choose to delete them, update those references first.

### Workspace cleanup notes
These are not likely commits, but are runtime or local metadata files that are already ignored by `.gitignore`:

- `data/` directory contents
- `.env`
- `.vscode/`
- `.agentmaster/`
- `.claude/settings.local.json`

If you want the working folder clean, these can be removed locally, but they should remain ignored in git.

### Recommended action
1. Delete `dashboard.py` and `README.html` immediately.
2. Move the planning/research docs into `archive/` or a dedicated docs folder, or keep only the most active ones in root.
3. Keep `README.md`, `pyproject.toml`, `requirements.txt`, `main.py`, `app/`, `core/`, `tools/`, `tests/`, and `TOOL_ROADMAP.md` as the active codebase.
4. Optionally delete local runtime artifacts under `data/` and ignored local config files if you want a clean working directory.

### Rationale
- `dashboard.py` is a true code-level legacy file that no longer matches the current app entrypoint.
- `README.html` is a generated artifact that duplicates the canonical `README.md`.
- The other root markdown files are useful for planning, but they are not required for the product and can be archived to reduce repository noise.

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
