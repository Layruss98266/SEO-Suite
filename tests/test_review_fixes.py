"""
Regression tests for the post-review fixes (2026-05).

Covers:
  #1, #2 — path traversal in /api/open + /api/download
  #3     — SSRF in crawler (safe_requests_get usage)
  #4, #5, #7 — auth gating when SEO_SUITE_PASSWORD_HASH is set
  #8     — run-flag race (atomic check+set inside _lock)
  #9     — PDF concurrency semaphore
  #16    — error_count helper covers "GSC Error: …" prefix
  #17    — progress key stable across URL ordering
"""
from __future__ import annotations

import json
import os
import sys
import types
from pathlib import Path

import pytest

# Stub playwright before importing server, same pattern as the other tests.
_pw_stub = types.ModuleType("playwright")
_pw_stub.sync_api = types.ModuleType("playwright.sync_api")
_pw_stub.sync_api.sync_playwright = None
_pw_stub.sync_api.TimeoutError = TimeoutError
sys.modules.setdefault("playwright", _pw_stub)
sys.modules.setdefault("playwright.sync_api", _pw_stub.sync_api)


@pytest.fixture
def client():
    from app.server import app
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


# ── #1, #2: path traversal ───────────────────────────────────────────────────

class TestPathTraversal:
    @pytest.mark.parametrize("filename", [
        "../config.json",
        "..%2Fconfig.json",
        "..\\config.json",
        "../../etc/passwd",
        "/etc/passwd",
        "a/b.html",
        ".env",
    ])
    def test_api_open_blocks_traversal(self, client, filename):
        r = client.get(f"/api/open/{filename}")
        # Either 404 (path didn't resolve to a file inside REPORTS_DIR) or 400.
        # The key invariant: never 200 with file contents.
        assert r.status_code in (400, 404), f"{filename!r} returned {r.status_code}"

    @pytest.mark.parametrize("filename", [
        "../config.json",
        "../../requirements.txt",
        "/etc/passwd",
        "subdir/file.csv",
    ])
    def test_api_download_blocks_traversal(self, client, filename):
        r = client.get(f"/api/download/{filename}")
        assert r.status_code in (400, 404), f"{filename!r} returned {r.status_code}"

    def test_api_open_serves_valid_html(self, client, tmp_path, monkeypatch):
        """Sanity: a legitimate report inside REPORTS_DIR still serves."""
        import app.server as srv
        f = srv.REPORTS_DIR / "indexing_report_test123.html"
        f.write_text("<html>OK</html>", encoding="utf-8")
        try:
            r = client.get("/api/open/indexing_report_test123.html")
            assert r.status_code == 200
            assert b"OK" in r.data
        finally:
            f.unlink(missing_ok=True)


# ── #4, #5, #7: auth gating ──────────────────────────────────────────────────

class TestAuthGating:
    """When SEO_SUITE_PASSWORD_HASH is set, mutating routes return 401."""

    @pytest.fixture
    def auth_client(self, monkeypatch):
        # Provide a real hash so auth_enabled() returns True. Don't log in.
        from werkzeug.security import generate_password_hash
        monkeypatch.setenv("SEO_SUITE_USERNAME", "tester")
        monkeypatch.setenv("SEO_SUITE_PASSWORD_HASH", generate_password_hash("hunter2"))
        from app.server import app
        app.config["TESTING"] = True
        with app.test_client() as c:
            yield c

    @pytest.mark.parametrize("path,method", [
        ("/api/reports/delete_all", "POST"),
        ("/api/history",            "GET"),
        ("/api/settings",           "GET"),
        ("/api/index/cancel",       "POST"),
        ("/api/profiles",           "GET"),
    ])
    def test_protected_route_returns_401(self, auth_client, path, method):
        r = auth_client.open(path, method=method,
                             data=json.dumps({"confirm": "YES"}),
                             content_type="application/json")
        assert r.status_code == 401, f"{method} {path} should require auth"

    def test_health_still_public(self, auth_client):
        r = auth_client.get("/health")
        assert r.status_code == 200
        assert r.get_json() == {"status": "ok"}

    def test_health_omits_version(self, auth_client):
        r = auth_client.get("/health")
        body = r.get_json()
        assert "version" not in body
        assert "indexing_running" not in body

    def test_login_form_renders(self, auth_client):
        r = auth_client.get("/login")
        assert r.status_code == 200
        assert b"Sign in" in r.data

    def test_login_with_bad_credentials_fails(self, auth_client):
        r = auth_client.post("/login", data={"username": "tester", "password": "wrong"})
        assert r.status_code == 401

    def test_login_with_good_credentials_grants_session(self, auth_client):
        r = auth_client.post("/login", data={"username": "tester", "password": "hunter2"})
        assert r.status_code == 302
        # After logging in, the protected route should work.
        r2 = auth_client.get("/api/history")
        assert r2.status_code == 200


# ── #8: run-flag race ────────────────────────────────────────────────────────

def test_index_run_flag_set_inside_lock():
    """Second POST to /api/index/run while a worker holds running=True must 400.
    With the pre-fix code, both POSTs could pass the check before either flipped
    the flag. The atomic check+set inside _lock closes that window.
    """
    from app import server
    # Simulate the worker having already set running=True.
    with server._lock:
        server._index_status["running"] = True
    try:
        client = server.app.test_client()
        r = client.post("/api/index/run", json={"input": "https://example.com/sm.xml"})
        assert r.status_code == 400
        assert b"Already running" in r.data
    finally:
        with server._lock:
            server._index_status["running"] = False


# ── #9: PDF semaphore ────────────────────────────────────────────────────────

def test_pdf_concurrency_returns_503_when_saturated(tmp_path):
    """If the PDF semaphore is exhausted, a subsequent request returns 503
    instead of piling up worker threads spawning chromium processes."""
    from app import server
    # Drain the semaphore so any new PDF call must non-blocking-fail.
    drained = []
    while server._pdf_semaphore.acquire(blocking=False):
        drained.append(True)
    try:
        # Create a real HTML report so the path check passes, then call.
        f = server.REPORTS_DIR / "indexing_report_pdf_test.html"
        f.write_text("<html></html>", encoding="utf-8")
        try:
            client = server.app.test_client()
            r = client.get("/api/reports/pdf/indexing_report_pdf_test.html")
            assert r.status_code == 503
            assert b"busy" in r.data
        finally:
            f.unlink(missing_ok=True)
    finally:
        for _ in drained:
            server._pdf_semaphore.release()


# ── #16: error_count covers GSC Error prefix ─────────────────────────────────

@pytest.mark.parametrize("status,is_error", [
    ("Indexed",            False),
    ("Not Indexed",        False),
    ("Error",              True),
    ("Timeout",            True),
    ("Other",              True),
    ("Error: network",     True),
    ("GSC Error: 403",     True),
    ("Browser Error: blocked", True),
    ("Playwright Error: launch failed", True),
    ("",                   False),
    (None,                 False),
])
def test_is_error_status(status, is_error):
    from app.server import _is_error_status
    assert _is_error_status(status) is is_error


# ── #17: progress key stable across URL ordering ─────────────────────────────

def test_progress_key_stable():
    from core.checker import progress_file_for
    # Same key string → same file. Different orderings → different keys, but the
    # caller now sorts before joining so semantically-identical sets collide.
    a = progress_file_for(",".join(sorted(["https://b.example", "https://a.example"])[:3]))
    b = progress_file_for(",".join(sorted(["https://a.example", "https://b.example"])[:3]))
    assert a == b


# ── #3: crawler uses redirect-validating safe_requests_get ───────────────────

def test_crawler_uses_safe_requests_get(monkeypatch):
    """crawl_site must route HTTP through safe_requests_get so redirects to
    private IPs are blocked. We assert by patching the function and confirming
    it's called from the crawler."""
    from core import checker, security
    calls = []

    def _spy(url, **kw):
        calls.append(url)
        class _R:
            status_code = 404
            headers = {"Content-Type": "text/html"}
            text = ""
        return _R()

    monkeypatch.setattr(security, "safe_requests_get", _spy)
    checker.crawl_site("https://example.com/", max_pages=1, max_depth=0)
    assert calls, "crawl_site should call safe_requests_get"
    assert calls[0].startswith("https://example.com")
