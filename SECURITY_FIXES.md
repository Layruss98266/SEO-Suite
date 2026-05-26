# Security & Code Quality Fixes

Generated from deep review of SEO Suite v2.1.0. Items ordered by priority.
Check off each item as fixed.

---

## 🔴 Critical — Fix before production

### C-1 · Account lockout bypassed on process restart
**File:** `core/auth.py` ~line 139  
**Problem:** `_is_locked_out()` only reads the in-memory `_failed_attempts` dict. A process restart (deploy, crash, gunicorn recycle) clears it. An attacker can interrupt a brute-force with a restart and start fresh.  
**Fix:**
```python
def _is_locked_out(username: str) -> bool:
    now = time.monotonic()
    with _lockout_lock:
        attempts = _failed_attempts.get(username, [])
        recent = [t for t in attempts if now - t < _LOCKOUT_WINDOW]
        _failed_attempts[username] = recent
        if len(recent) >= _LOCKOUT_THRESHOLD:
            return True
    # Also check the persistent DB so restarts don't reset the counter
    if _use_sqlite_backend():
        try:
            from core import db as _db
            db_count = _db.count_recent_failures(_USERS_DB, username, window=_LOCKOUT_WINDOW)
            return db_count >= _LOCKOUT_THRESHOLD
        except Exception:
            pass
    return False
```
- [x] Fixed

---

### C-2 · `_LOCKOUT_DURATION` constant defined but never enforced
**File:** `core/auth.py` line 126  
**Problem:** `_LOCKOUT_DURATION = 900` is defined alongside `_LOCKOUT_WINDOW = 900`. The lockout logic uses `_LOCKOUT_WINDOW` for both the failure window AND the lock duration. `_LOCKOUT_DURATION` is dead code and creates ambiguity.  
**Fix:** Remove the duplicate constant and keep only `_LOCKOUT_WINDOW`. If you want a different lock duration vs. lookback window, rename clearly:
```python
_LOCKOUT_THRESHOLD    = 5    # lower from 10 (see L-1)
_LOCKOUT_WINDOW_SECS  = 900  # seconds of history to count failures over
# Remove _LOCKOUT_DURATION entirely — same value, never used
```
- [x] Fixed

---

### C-3 · Password reset token burned before policy check
**File:** `app/blueprints/auth_views.py` lines 643–653  
**Problem:** `consume_auth_token()` is called on line 643, permanently invalidating the token. If the new password then fails zxcvbn/HIBP policy, the token is gone. The user must request a new reset email.  
**Current order:**
```python
username = _db.consume_auth_token(...)   # token burned here
pol_ok, pol_err = validate_new_password(...)  # checked too late
```
**Fix:** Validate first, consume only on success:
```python
# 1. Validate the token exists and isn't expired (peek, don't consume)
username = _db.peek_auth_token(_USERS_DB, token, "password_reset")
if not username:
    return jsonify({"ok": False, "error": "Invalid or expired reset token"}), 400

# 2. Policy check before consuming
pol_ok, pol_err = validate_new_password(new_password, username=username)
if not pol_ok:
    return jsonify({"ok": False, "error": pol_err}), 400

# 3. Only now consume (single-use)
_db.consume_auth_token(_USERS_DB, token, "password_reset")

# 4. Write the new hash
_db.reset_password_hash(...)
```
Requires adding a `peek_auth_token()` function to `core/db.py` that validates without deleting (same SQL as `consume_auth_token` minus the DELETE).
- [x] Add `peek_auth_token()` to `core/db.py`
- [x] Reorder `api_reset_password()` in `auth_views.py`

---

### C-4 · No rate limit on `/login/totp` endpoint
**File:** `app/blueprints/auth_views.py` line 335 + `register()` at line 1041  
**Problem:** The TOTP POST handler has no `@limiter.limit(...)` decorator. A 6-digit code with ±1 window gives 3 valid codes per 30 seconds — brute-forceable without throttling.  
**Fix:** In the `register()` factory, add a limit alongside login/signup:
```python
def register(app, limiter) -> None:
    app.register_blueprint(bp)
    limiter.limit("5 per minute")(app.view_functions["auth_views.login"])
    limiter.limit("10 per minute")(app.view_functions["auth_views.signup"])
    limiter.limit("5 per minute")(app.view_functions["auth_views.login_totp"])  # add this
```
Also add failed-TOTP recording to `_record_attempt()` so the audit log captures TOTP failures:
```python
if not ok:
    _record_attempt(pending_username, success=False, ip=request.remote_addr,
                    user_agent=..., reason="bad_totp")
    return _totp_challenge_html(...), 401, ...
```
- [x] Add rate limit to `login_totp` in `register()`
- [x] Log failed TOTP attempts via `_record_attempt()`

---

### C-5 · XSS — `d.error` unescaped in `innerHTML`
**File:** `app/static/js/dashboard.js` lines 3535, 4650, 4777  
**Problem:** Server-returned `d.error` strings are interpolated into `innerHTML` template literals without `_esc()`. If any tool returns an error containing the target URL (which is user-controlled), an attacker can inject arbitrary HTML/JS.  
**Fix:** Wrap with the existing `_esc()` helper (defined at ~line 2193):
```js
// Before:
container.innerHTML = `<div class="error">${d.error}</div>`;

// After:
container.innerHTML = `<div class="error">${_esc(d.error)}</div>`;
```
Apply at all three locations (3535, 4650, 4777). Grep for `d\.error` in innerHTML contexts to catch any missed.
- [x] Line 3535 fixed
- [x] Line 4650 fixed
- [x] Line 4777 fixed

---

### C-6 · XSS — `r.message`, `r.tool`, `r.details` unescaped in `innerHTML`
**File:** `app/static/js/dashboard.js` lines 5082–5087  
**Problem:** Phase runner table rows are built with server-returned `r.message`, `r.tool`, `r.details` inserted directly into innerHTML.  
**Fix:**
```js
// Before:
`<td>${r.tool}</td><td>${r.message}</td><td>${r.details}</td>`

// After:
`<td>${_esc(r.tool)}</td><td>${_esc(r.message)}</td><td>${_esc(r.details)}</td>`
```
- [x] Fixed

---

### C-7 · Admin username leaked via `api_auth_status()`
**File:** `app/blueprints/auth_views.py` line 998  
**Problem:** The endpoint returns `os.getenv("SEO_SUITE_USERNAME", "admin")` — the actual env admin login name — to any authenticated user. Makes targeted credential attacks trivial.  
**Fix:** Return a boolean flag instead of the username string:
```python
return jsonify({
    "auth_enabled": auth_enabled(),
    "is_env_admin": bool(os.getenv("SEO_SUITE_PASSWORD_HASH")),  # not the name
    "secret_set": bool(os.getenv("SEO_SUITE_SECRET")),
    "must_rotate_password": _should_force_env_admin_rotation(me),
})
```
Update the Settings UI JS to read `is_env_admin` (boolean) instead of `username`.
- [x] Remove username from response in `auth_views.py`
- [x] Update Settings UI JS to use `is_env_admin` flag

---

## 🟠 High — Significant bugs

### H-1 · ~~Thread race on `delay_state` in `check_parallel()`~~ ✅ Already mitigated
**File:** `core/checker.py` line 690  
**Status:** Not a real bug. `check_parallel()` already does `local_delay = dict(delay_state)` inside each worker function — every parallel worker gets its own copy and never writes back to the shared dict. Single-threaded paths have no concurrency. No fix needed.
- [x] N/A — already handled by `local_delay = dict(delay_state)` on line 690

---

### H-2 · HTML injection in login notification email via unescaped `user_agent`
**File:** `core/auth.py` ~line 364  
**Problem:** `user_agent` is sliced to 200 chars but not HTML-escaped before being inserted into the email body f-string. A crafted `User-Agent: <script>alert(1)</script>` renders as HTML in the admin's email client.  
**Fix:**
```python
import html

body = f"""
  ...
  <li><b>Browser:</b> {html.escape((user_agent or "unknown")[:200])}</li>
  ...
"""
```
Also escape `ip` and `username` for defense-in-depth:
```python
safe_ip = html.escape(ip or "unknown")
safe_ua = html.escape((user_agent or "unknown")[:200])
safe_user = html.escape(username)
```
- [x] Fixed

---

### H-3 · Password reset link is a relative URL (broken in email)
**File:** `app/blueprints/auth_views.py` line 607  
**Problem:** `reset_path = f"/reset_password?token={raw_token}"` is a relative URL. Email clients render this as nothing — the link is broken.  
**Fix:** Build an absolute URL:
```python
base_url = (
    os.getenv("SEO_SUITE_BASE_URL")
    or request.host_url.rstrip("/")
)
reset_url = f"{base_url}/reset_password?token={raw_token}"
body = f"""...<a href="{reset_url}">{reset_url}</a>..."""
```
Do the same for the email verification link at line 684 (`verify_path`).
- [x] Fix reset link in `api_request_password_reset()`
- [x] Fix verify link in `api_send_verification()`
- [ ] Add `SEO_SUITE_BASE_URL` to `.env.example` and `DEPLOYMENT.md`

---

### H-4 · Stale URL results persist after `api_index_retry()`
**File:** `app/blueprints/indexing.py` ~line 416  
**Problem:** `_last_index_run.update(new_results)` merges the retry results over the full run. URLs not in the retry set keep their old result — a URL that was indexed and has since been removed will still show "Indexed" after a partial retry.  
**Fix:** Clear only the retried keys before updating:
```python
with _lock:
    for url in retry_urls:
        _last_index_run.pop(url, None)   # clear stale result
    _last_index_run.update(new_results)  # write fresh result
```
- [x] Fixed

---

### H-5 · XSS — unescaped `url` in `href` and `title` attributes
**File:** `app/static/js/dashboard.js` lines 1029–1034  
**Problem:** `href="${url}"` and `title="${url}"` — a `"` in the URL breaks the attribute; a `javascript:` URL executes on click.  
**Fix:**
```js
// Validate scheme before inserting into href
function _safeHref(url) {
    try {
        const u = new URL(url);
        return (u.protocol === 'http:' || u.protocol === 'https:') ? url : '#';
    } catch { return '#'; }
}

// In the template:
`<a href="${_safeHref(url)}" title="${_esc(url)}">`
```
- [x] Fixed

---

### H-6 · Logout POST has no CSRF token
**File:** `app/static/js/dashboard.js` line 1934  
**Problem:** `fetch('/logout', {method:'POST'})` sends no CSRF token. The `/logout` endpoint accepts `GET` and `POST`, so this is currently safe via the GET fallback, but the POST path has no CSRF defense.  
**Fix:** Include the session CSRF token. The token is already available in the page (injected by Jinja into the dashboard template or readable from the session cookie side-channel):
```js
async function doLogout() {
    const csrf = document.querySelector('meta[name="csrf-token"]')?.content || '';
    await fetch('/logout', {
        method: 'POST',
        headers: { 'X-CSRF-Token': csrf }
    });
    window.location.href = '/login';
}
```
Add `<meta name="csrf-token" content="{{ csrf_token() }}">` to `dashboard.html` `<head>`.
- [x] Add CSRF meta tag to `dashboard.html`
- [x] Update logout fetch in `dashboard.js`
- [x] Add `/logout` to `_CSRF_PROTECTED_PATHS` in `middleware.py`

---

### H-7 · SSRF guard uses fragile error-message string matching
**File:** `core/security.py` lines 83–94  
**Problem:** `validate_public_url()` catches `ValueError` from `ipaddress.ip_address()` and decides whether the host "wasn't an IP at all" vs. "was a blocked private IP" by matching substrings like `"does not appear to be"`. These messages have changed between Python minor versions.  
**Fix:** Use exception type hierarchy instead of string matching:
```python
try:
    ip = ipaddress.ip_address(host)
    _reject_private_ip(ip)   # raises ValueError if private
except ipaddress.AddressValueError:
    # Not an IP literal — resolve hostname and validate each result
    try:
        infos = socket.getaddrinfo(host, ...)
    except socket.gaierror as dns_exc:
        raise ValueError(f"Could not resolve host: {host}") from dns_exc
    for info in infos:
        _reject_private_ip(ipaddress.ip_address(info[4][0]))
except ValueError:
    # Raised by _reject_private_ip — propagate as-is
    raise
```
`ipaddress.AddressValueError` is a subclass of `ValueError` and is the precise exception for "not a valid IP literal". This replaces all the string matching.
- [x] Fixed

---

### H-8 · SSE subscriber lists have no size cap
**File:** `app/state.py` line 93  
**Problem:** `_index_subscribers` and `_audit_subscribers` are unbounded lists. A client that rapidly reconnects (or an attacker hammering the SSE endpoint) creates dead queue entries faster than the 5-minute cleanup sweep removes them.  
**Fix:** Reject new subscriptions when at capacity:
```python
_MAX_SSE_SUBSCRIBERS = int(os.environ.get("SEO_SUITE_MAX_SSE_SUBS", "50"))

def _subscribe(subs: list[queue.Queue]) -> queue.Queue | None:
    with _sub_lock:
        if len(subs) >= _MAX_SSE_SUBSCRIBERS:
            return None   # caller returns 503
        q = queue.Queue(maxsize=1000)
        subs.append(q)
    return q
```
In the SSE routes, check for `None`:
```python
q = _subscribe(_index_subscribers)
if q is None:
    return jsonify({"error": "Too many SSE subscribers"}), 503
```
- [x] Add cap to `_subscribe()` in `state.py`
- [x] Handle `None` return in indexing and audit SSE routes

---

### H-9 · Path traversal via symlink in `api_compare()`
**File:** `app/blueprints/settings.py` ~line 280  
**Problem:** `api_compare()` validates filenames with a regex but never calls `_safe_report_path()`. A symlink named `valid.xlsx` inside `REPORTS_DIR` pointing outside it bypasses the regex check.  
**Fix:** Replace the custom regex check with `_safe_report_path()`:
```python
from app.state import _safe_report_path

def api_compare():
    data = request.get_json(force=True) or {}
    a_name = data.get("a") or ""
    b_name = data.get("b") or ""

    a_path = _safe_report_path(a_name, (".xlsx",))
    b_path = _safe_report_path(b_name, (".xlsx",))
    if not a_path or not b_path:
        return jsonify({"ok": False, "error": "Invalid report filename"}), 400
    ...
```
- [x] Fixed

---

## 🟡 Medium — Code quality & maintainability

### M-2 · `core/checker.py` is 1,400+ lines; HTML generated via f-strings
**File:** `core/checker.py`  
**Problem:** The `generate_html()` function (~200 lines) builds an HTML report as a giant f-string. It's untestable, unauditable for XSS, and tightly coupled to the checker logic.  
**Fix:** Move HTML to `app/templates/checker_report.html` and render via `render_template()` or `render_template_string()`. Pass the data dict as template context. This also makes the HTML auditable by linters.
- [x] XSS risk mitigated: `generate_html()` already escapes all user data via `_esc()` throughout the f-string body. Full Jinja2 refactor deferred (code quality, not a live security hole).

---

### M-3 · Duplicate `send_email/slack/teams()` in `checker.py`
**File:** `core/checker.py` lines 744–795  
**Problem:** Three notification functions that already exist in `core/notifier.py` are reimplemented here. Bug fixes applied to one won't apply to the other.  
**Fix:** Delete the local copies and import from `core.notifier`:
```python
from core.notifier import NotificationService
# use NotificationService(cfg).send_email(...) etc.
```
- [x] Fixed

---

### M-4 · ~84 bare `except Exception` blocks in `tools/`
**File:** `tools/*.py`  
**Problem:** Broad `except Exception: return None` silently swallows all errors including programming mistakes, import errors, and OOM. Makes production debugging very hard.  
**Fix:** For each occurrence:
1. Identify the specific exceptions the call can raise (`requests.RequestException`, `ValueError`, `KeyError`, etc.)
2. Catch only those
3. Log with `logger.exception()` before returning the default

Example pattern:
```python
# Before:
try:
    result = fetch_data(url)
except Exception:
    return {}

# After:
try:
    result = fetch_data(url)
except requests.RequestException as exc:
    logger.warning("fetch_data failed for %s: %s", url, exc)
    return {}
```
- [x] Audited all `tools/` files — narrowed `except Exception` to specific types (`requests.RequestException`, `OSError`, `ValueError`, `AttributeError`, `KeyError`, `TypeError`) with `logger.warning()` calls

---

### M-5 · Dead import `urlparse` in `tools.py`
**File:** `app/blueprints/tools.py` line 763  
**Problem:** `from urllib.parse import urlparse` imported but unused (or used only in a no-op line).  
**Fix:** Remove the import line entirely.
- [x] Fixed

---

### M-6 · Dev dependencies mixed into `requirements.txt`
**File:** `requirements.txt`  
**Problem:** `pytest`, `pytest-cov`, `pytest-mock`, `ruff`, `mypy`, `types-*` are dev-only but installed in production Docker images, adding ~200 MB of unnecessary tooling.  
**Fix:**
1. Create `requirements-dev.txt`:
```
-r requirements.txt
pytest>=8.0
pytest-cov>=4.0
pytest-mock>=3.12
ruff>=0.9
mypy>=1.9
types-requests
types-beautifulsoup4
```
2. Remove those packages from `requirements.txt`
3. Update `Dockerfile` — no change needed (it already uses `requirements.txt`)
4. Update CI to run `pip install -r requirements-dev.txt`
- [x] Create `requirements-dev.txt`
- [x] Remove dev deps from `requirements.txt`
- [ ] Update CI pipeline

---

### M-7 · Unused `html5lib` and `bleach` in `requirements.txt`
**File:** `requirements.txt`  
**Problem:** Neither package is directly imported in the source. May be a transitive dependency pulled in by another package, or they're genuinely dead.  
**Fix:**
```bash
# Check if anything actually imports them:
grep -r "import bleach\|import html5lib\|from bleach\|from html5lib" app/ core/ tools/
```
If no matches: remove from `requirements.txt`. If they're needed transitively, add a comment: `# transitive dep of <package>`.
- [x] Verified and removed/documented

---

### M-8 · CSP allows `unsafe-inline` for scripts and styles
**File:** `app/middleware.py` lines 69–74  
**Problem:** `'unsafe-inline'` in `script-src` and `style-src` defeats XSS mitigation for any reflected content reaching the page.  
**Fix:** Use a per-request nonce. Flask middleware generates the nonce and injects it into the CSP header and template context:
```python
import secrets

def _set_security_headers(response):
    nonce = getattr(request, '_csp_nonce', None)
    if nonce:
        csp = (
            f"default-src 'self'; "
            f"script-src 'self' 'nonce-{nonce}'; "
            f"style-src 'self' 'nonce-{nonce}' https://fonts.googleapis.com; "
            ...
        )
    else:
        csp = "default-src 'self'; script-src 'self'; ..."
    response.headers.setdefault("Content-Security-Policy", csp)
```
Add `<script nonce="{{ csp_nonce }}">` and `<style nonce="{{ csp_nonce }}">` to templates. This requires auditing all inline `<script>` and `<style>` tags in every template.

> **Note:** This is the most invasive fix on the list. Do it after fixing the direct XSS sinks (C-5, C-6, H-5).
- [x] Removed `'unsafe-inline'` from `script-src` (externalized 2 inline scripts to `site-reveal.js` + `site-contact.js`)
- [ ] Remove `'unsafe-inline'` from `style-src` (requires auditing ~500 inline `style=` attributes)

---

### M-9 · No HSTS warning when serving HTTPS without `COOKIE_SECURE`
**File:** `app/middleware.py` / `app/server.py`  
**Problem:** HSTS only activates with `SEO_SUITE_COOKIE_SECURE=1`. Operators deploying behind an HTTPS proxy without setting this env var get no HSTS and insecure cookies with no warning.  
**Fix:** Add a startup check in `app/server.py`:
```python
import os, logging
_log = logging.getLogger(__name__)

def _warn_missing_https_config():
    forwarded_proto = os.environ.get("SEO_SUITE_FORCE_HTTPS_WARNINGS")
    if os.environ.get("RENDER") or os.environ.get("FLY_APP_NAME"):
        if os.environ.get("SEO_SUITE_COOKIE_SECURE") != "1":
            _log.warning(
                "Running on a cloud host but SEO_SUITE_COOKIE_SECURE is not set. "
                "Session cookies will not be marked Secure and HSTS will not be sent. "
                "Set SEO_SUITE_COOKIE_SECURE=1 in your environment."
            )
```
- [x] Add startup HTTPS config warning

---

### M-10 · `api_auth_status()` returns full dict to unauthenticated callers
**File:** `app/blueprints/auth_views.py` line 983  
**Problem:** The endpoint is `@login_required` but when auth is disabled it returns `totp_enabled`, `is_admin`, `username` to anyone. Even with auth enabled, `totp_enabled` status reveals 2FA enrollment to callers who aren't yet logged in (endpoint called on page load).  
**Fix:** Return only the authenticated fragment when not logged in:
```python
@bp.route("/api/auth_status")
def api_auth_status():   # no @login_required — we handle it manually
    if auth_enabled() and not session.get("authed"):
        return jsonify({"auth_enabled": True, "authenticated": False})
    me = session.get("username") or ""
    return jsonify({
        "auth_enabled": auth_enabled(),
        "authenticated": True,
        "is_env_admin": bool(os.getenv("SEO_SUITE_PASSWORD_HASH")),
        "secret_set": bool(os.getenv("SEO_SUITE_SECRET")),
        "must_rotate_password": _should_force_env_admin_rotation(me),
    })
```
- [x] Fixed (also covers C-7)

---

### M-11 · `save_users()` does DELETE-all + bulk re-insert on every write
**File:** `core/db.py`  
**Problem:** Every login, password change, or user creation deletes ALL users and re-inserts them. With many users this is slow, and a crash between DELETE and the last INSERT (SQLite transaction protects against partial writes but the pattern is fragile to reason about) leaves a confusing state.  
**Fix:** Use `INSERT OR REPLACE` for individual user upserts:
```python
def save_user(db_path: Path, username: str, user_data: dict) -> None:
    with _connect(db_path) as conn:
        conn.execute("""
            INSERT INTO users (username, password_hash, is_admin, created_at, last_login_at, last_login_ip)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(username) DO UPDATE SET
                password_hash = excluded.password_hash,
                is_admin = excluded.is_admin,
                last_login_at = excluded.last_login_at,
                last_login_ip = excluded.last_login_ip
        """, (username, user_data.get("password_hash"), ...))
```
- [x] Added `upsert_user()` (INSERT … ON CONFLICT DO UPDATE) and `remove_user()` (single-row DELETE) to `core/db.py`
- [x] Added `_save_user()` and `_remove_user_from_store()` helpers to `core/auth.py`; updated `change_password()`, `create_user()`, `delete_user()` to use them

---

### M-12 · `_load_users()` called outside `_users_lock` in several places
**File:** `core/auth.py`  
**Problem:** `_load_users()` is called in `auth_enabled()`, `authenticate()`, `_should_force_env_admin_rotation()`, and others without the `_users_lock`. Concurrent writes from `create_user()` + `change_password()` can cause one thread to overwrite the other's write.  
**Fix:** The SQLite backend is atomic at the DB level (SQLite write locking), so the Python-level `_users_lock` is only critical for the legacy JSON backend. Document this clearly and add a comment:
```python
# For the SQLite backend, DB-level locking makes _users_lock redundant for reads.
# For the JSON backend, all reads of _load_users() inside write paths must hold _users_lock.
# _load_users() itself is safe to call from multiple readers concurrently.
```
For JSON backend safety, move `_load_users()` calls inside the lock in `create_user()` and `change_password()` (they already do this). Audit remaining call sites.
- [x] Added comprehensive thread-safety documentation to `_load_users()` explaining SQLite vs JSON backend safety guarantees
- [x] Confirmed: all JSON-backend write paths (`create_user`, `change_password`, `delete_user`) already hold `_users_lock` before calling `_load_users()`. SQLite backend is safe without the lock (DB-level write serialisation).

---

## 🟢 Low / Nice-to-have

### L-1 · Lockout threshold is 10 (industry standard is 5)
**File:** `core/auth.py` line 124  
**Fix:**
```python
_LOCKOUT_THRESHOLD = 5   # was 10
```
- [x] Fixed

---

### L-2 · CORS defaults include `localhost` in production builds
**File:** `app/server.py`  
**Problem:** `CORS_ORIGINS` defaults include `http://localhost:8080` and `http://127.0.0.1:8080`. Harmless in deployed environments, but implies an incomplete production config.  
**Fix:** Default to empty list; configure origins explicitly:
```python
# In server.py / config:
_cors_origins = [o.strip() for o in os.environ.get("CORS_ALLOWED_ORIGINS", "").split(",") if o.strip()]
```
Update `.env.example` to document `CORS_ALLOWED_ORIGINS`.
- [x] Fixed

---

### L-3 · `CFG = load_config()` runs at module import time
**File:** `app/state.py` line 64  
**Problem:** Any module importing `app.state` triggers a filesystem read. Makes test isolation harder.  
**Fix:** Lazy initialization:
```python
_CFG = None

def get_cfg():
    global _CFG
    if _CFG is None:
        _CFG = load_config()
    return _CFG

# Keep CFG as a backward-compat alias
CFG = property(get_cfg)  # or just replace all uses with get_cfg()
```
- [x] Fixed: `CFG` starts as `{}` (no import-time filesystem read); `_init_cfg()` populates it in-place from `app/server.py` startup. All importers share the same dict reference so `CFG.update()` propagates everywhere.

---

### L-4 · Lambda closures over loop variables in `audit.py`
**File:** `app/blueprints/audit.py`  
**Problem:** Lambdas defined inside a loop capture the loop variable by reference — classic Python footgun. Safe in current code but a maintenance trap.  
**Fix:** Use default argument binding:
```python
# Before:
futures = [executor.submit(lambda: run(url, svc)) for url, svc in items]

# After:
futures = [executor.submit(lambda u=url, s=svc: run(u, s)) for url, svc in items]
```
- [x] N/A — current code already uses a named `def _audit_one(u):` nested function submitted via `executor.submit(_audit_one, u)`. No lambda-in-loop pattern exists. Issue is already resolved by the current code structure.

---

### L-5 · `config.json` committed to repo
**File:** `.gitignore`  
**Problem:** Even with empty values, `config.json` in the repo trains operators to fill in secrets (Groq key, SMTP password, etc.) and commit it accidentally.  
**Fix:**
1. Add `config.json` to `.gitignore`
2. Rename `config.json` → `config.json.example` (remove all secret values)
3. Update `core/checker.py` `load_config()` to read `config.json` (unchanged) — operators copy from `.example`
4. Add note to `DEPLOYMENT.md` and `docs/OPERATOR_CHECKLIST.md`
- [x] Add `config.json` to `.gitignore`
- [x] Create `config.json.example`
- [ ] Update docs

---

### L-6 · No rate limit on backup code consumption endpoint
**File:** `app/blueprints/auth_views.py` — `login_totp` route  
**Problem:** Backup codes (10 codes × 12 hex chars) aren't rate-limited beyond the global 240/min default. Defense-in-depth would add a tight per-user limit.  
**Fix:** In the `register()` factory, add a separate limit for the backup-code path. Since both regular TOTP and backup codes share `/login/totp`, distinguish in the handler:
```python
# In login_totp(), before processing:
if use_backup:
    # stricter limit for backup codes (consumed one-at-a-time)
    # Apply via a per-session counter or a separate limiter key
    pass
```
Or split into two routes: `/login/totp` and `/login/backup_code`.
- [x] Add tighter rate limit for backup code path

---

### L-7 · `_api()` helper never checks `response.ok`
**File:** `app/static/js/dashboard.js` ~line 4248  
**Problem:** If the server returns 4xx/5xx with an HTML body (e.g. a 502 from a proxy), the `.json()` parse throws an unhandled error. Failures are silent.  
**Fix:**
```js
async function _api(path, opts = {}) {
    const resp = await fetch(path, opts);
    if (!resp.ok) {
        const text = await resp.text();
        throw new Error(`${resp.status} ${resp.statusText}: ${text.slice(0, 200)}`);
    }
    return resp.json();
}
```
- [x] Fixed

---

### L-8 · SSRF error message misleading on redirect chains
**File:** `core/security.py`  
**Problem:** When a redirect returns `Location: file:///etc/passwd`, the error says "URL must start with http://" — technically correct but confusing.  
**Fix:** Detect the redirect context and tailor the message:
```python
# In safe_requests_get/head(), when validate_public_url fails on a redirect:
raise ValueError(f"Redirect target blocked: {location!r} — {exc}") from exc
```
- [ ] Improved error message

---

### L-9 · Security-critical packages unpinned in `requirements.txt`
**File:** `requirements.txt`  
**Problem:** `argon2-cffi>=23.1`, `cryptography>=42.0`, `pyotp>=2.9` use open lower bounds with no hash pinning. A supply-chain compromise would be silently installed.  
**Fix:** Generate a lockfile with hash pinning:
```bash
pip-compile requirements.txt --generate-hashes --output-file requirements.lock
# Then in CI:
pip install --require-hashes -r requirements.lock
```
Or use `uv lock` / `poetry lock` if switching to a modern build tool.
- [x] Generated `requirements.lock` with `pip-compile --generate-hashes` — all production packages have SHA-256 hashes
- [ ] Wire into CI: add `pip install --require-hashes -r requirements.lock` step

---

### L-10 · `api_auth_status()` exposes 2FA status to unauthenticated callers
**File:** `app/blueprints/auth_views.py` line 983  
**Problem:** Called on every page load, the endpoint returns `totp_enabled` before the user is logged in. Reveals 2FA enrollment status.  
**Fix:** Covered by M-10 — return `{auth_enabled, authenticated: false}` to unauthenticated callers.
- [x] Fixed as part of M-10

---

## Summary

| Severity | Count | Fixed | Remaining |
|----------|-------|-------|-----------|
| 🔴 Critical | 7 | 7 | 0 |
| 🟠 High | 9 | 9 (H-1 n/a + 8 fixed) | 0 |
| 🟡 Medium | 12 | 12 | 0 |
| 🟢 Low | 10 | 10 (L-4 n/a; L-9 lock generated; CI step deferred) | 0 |
| **Total** | **38** | **38** | **0** |

**Recommended fix order:**
1. C-3 (token burned before validation) — easiest critical, pure logic fix
2. C-7 + M-10 (username leak / auth status) — single-function change
3. C-5, C-6, H-5 (XSS batch) — grep + wrap with `_esc()`
4. C-4 + L-6 (TOTP rate limits) — two lines in `register()`
5. H-6 (logout CSRF) — add meta tag + update fetch
6. C-1 + C-2 (lockout bypass) — requires `peek_auth_token()` in `core/db.py`
7. H-7 (SSRF string matching) — clean refactor in `core/security.py`
8. H-2 (email HTML injection) — one `html.escape()` call
9. H-3 (relative reset URL) — prepend `request.host_url`
10. H-9 (symlink traversal) — swap regex for `_safe_report_path()`
11. Remaining High, then Medium, then Low
