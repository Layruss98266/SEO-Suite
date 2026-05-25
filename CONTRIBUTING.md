# Contributing to SEO Suite

Thanks for your interest in contributing! This document covers the development workflow, code conventions, and PR process.

## Quick Start

```bash
# 1. Clone and create a venv
git clone https://github.com/Surya8991/SEO-Suite.git
cd SEO-Suite
python -m venv .venv
source .venv/bin/activate    # or `.venv\Scripts\activate` on Windows

# 2. Install dependencies
pip install -r requirements.txt
python -m playwright install chromium

# 3. Configure secrets (optional — most features degrade gracefully without keys)
cp .env.example .env
# Edit .env if you want GSC, PageSpeed, Groq, etc.

# 4. Run the app
python main.py
# Open http://localhost:8080

# 5. (Optional) Install pre-commit hooks so lint/format runs on every commit
pip install pre-commit detect-secrets
pre-commit install
```

### Pre-commit hooks

The repo ships a `.pre-commit-config.yaml` that runs on every `git commit`:

- **Built-in checks** — trailing whitespace, end-of-file fixer, YAML/TOML/JSON validity, merge-conflict markers, large files, **private keys**, line endings
- **Ruff** — auto-fix + format on staged Python files
- **detect-secrets** — block accidentally committed credentials (tuned via `.secrets.baseline`)
- **Smoke pytest** — runs `tests/test_server.py` + `tests/test_review_fixes.py` to catch obvious breakage

Skip with `git commit --no-verify` if you really need to (don't make it a habit — CI runs the same checks).

## Development Workflow

### Before You Start

1. **Open an issue first** for features or significant refactors so we can discuss approach before you invest time
2. **Bug fixes** can go straight to a PR
3. **Documentation** improvements are always welcome

### Branch Naming

```
feature/add-bing-ctr-tool
fix/audit-timeout-on-large-sitemap
refactor/extract-tools-blueprint
docs/clarify-gsc-setup-step-5
```

### Making Changes

1. Create a branch off `main`
2. Make your changes (see [Code Style](#code-style) and [Architecture](#architecture-overview) below)
3. Add or update tests
4. Run the full test suite locally: `pytest -q`
5. Run lints: `ruff check . && ruff format --check .`
6. Commit with a clear message (see [Commit Messages](#commit-messages))
7. Open a PR

## Architecture Overview

See [ARCHITECTURE.md](ARCHITECTURE.md) for the full picture. The TL;DR:

- **`app/server.py`** — Flask app construction + remaining inline routes (indexing, audit, reports, settings, tools)
- **`app/state.py`** — Shared run-state, paths, helpers, constants
- **`app/middleware.py`** — Security headers, CSRF, error handlers
- **`app/blueprints/`** — Route groups extracted into Flask blueprints
- **`core/`** — Business logic (auth, indexing checker, audit orchestrator, security)
- **`tools/`** — Individual SEO check modules (phase1-4, generators, quick tools)
- **`tests/`** — Pytest suite (currently 238 tests)

## Code Style

### Python

- **Formatting** — `ruff format` (configured in `pyproject.toml`)
- **Linting** — `ruff check` (errors block CI)
- **Type hints** — Required on new public functions; `mypy` is informational, not enforced
- **Line length** — 100 chars (soft), 120 (hard)
- **Docstrings** — Triple-quoted, first line is a sentence ending in a period

### Patterns

| Do | Don't |
|----|-------|
| Use `from app.state import ...` for shared state | Define module-level mutable state in route files |
| Use `_safe_report_path()` / `_safe_upload_path()` for filesystem access | Use `Path(user_input)` directly |
| Use `validate_public_url()` / `safe_requests_get()` for outbound HTTP | Use `requests.get(user_url)` directly (SSRF risk) |
| Use `_int(data, key, default, lo, hi)` for numeric request fields | Use `int(data.get(key))` directly (no clamping, may crash) |
| Catch specific exceptions: `except (ValueError, KeyError)` | Catch broad `except Exception` unless logging+re-raising |
| Use `@login_required` / `@admin_required` on protected routes | Manually check `session["authed"]` per route |

### Adding a New Route

For a **single route** that fits an existing blueprint:

```python
# In app/blueprints/<existing>.py
@bp.route("/api/new_thing", methods=["POST"])
@login_required
def api_new_thing():
    data = request.get_json(force=True) or {}
    # ... validation, work ...
    return jsonify({"ok": True})
```

For a **new route group**, create a blueprint:

```python
# app/blueprints/new_group.py
from flask import Blueprint, jsonify, request
from core.auth import login_required

bp = Blueprint("new_group", __name__)

@bp.route("/api/new_group/something", methods=["POST"])
@login_required
def something():
    ...

def register(app, limiter=None) -> None:
    app.register_blueprint(bp)
    if limiter:
        limiter.limit("10 per hour")(app.view_functions["new_group.something"])
```

Then register in `app/server.py`:

```python
from app.blueprints import new_group as _new_group_bp
_new_group_bp.register(app, limiter)
```

## Testing

- **Run all tests:** `pytest -q`
- **Run one file:** `pytest tests/test_server.py -v`
- **Run one test:** `pytest tests/test_server.py::TestAuditRunValidation::test_already_running_returns_400_on_second_call`
- **With coverage:** `pytest --cov=app --cov=core --cov=tools --cov-report=html`

### Writing Tests

- One test = one behaviour
- Use descriptive names: `test_<what>_when_<context>_then_<expected>`
- Mock external services (use `pytest-mock`)
- Test files mirror module names: `tools/foo.py` → `tests/test_foo.py`

## Commit Messages

Follow conventional commits:

```
feat: add Bing CTR analyzer tool
fix: prevent audit thread leak when GSC auth fails
refactor: extract tools blueprint from server.py
docs: clarify Step 5 in GSC setup guide
test: add integration test for retry endpoint
chore: bump cryptography to 42.0.5
```

**Body** should explain *why*, not *what* (the diff shows what).

```
fix: cap audit partial buffer at 5000 entries

Large sitemaps (50k+ URLs) were causing the in-memory partial result
buffer to grow unbounded, eventually OOMing the worker. The completed
report still writes every URL to disk; only the live progress feed is
capped.
```

## Security

- **Never commit secrets** — `.env` is git-ignored. If you accidentally commit one, rotate the key immediately
- **SSRF** — Always validate user-supplied URLs via `validate_public_url()` before fetching server-side
- **Path traversal** — Always validate filesystem paths via `_safe_report_path()` or `_safe_upload_path()`
- **CSRF** — Form-encoded POSTs to `/login`, `/signup`, `/contact` require a `_csrf_token`. JSON API requests are exempt (SameSite cookies handle them)
- **Report vulnerabilities** privately — open a security advisory on GitHub rather than a public issue

## Reviewing PRs

- All PRs require at least one approving review
- CI must pass (tests + lint)
- Squash-merge to keep history clean

## Questions?

- Open a [discussion](https://github.com/Surya8991/SEO-Suite/discussions)
- Check [README.md](README.md) for project overview
- Check [docs/USECASE_GUIDES.md](docs/USECASE_GUIDES.md) for feature deep-dives
- Check [docs/SETUP_GUIDES.md](docs/SETUP_GUIDES.md) for API integration setup
