"""
Regression tests for the security/correctness fixes:
1. HTML reports escape user-controlled strings (XSS).
2. SSRF guard rejects loopback/private/non-http URLs.
3. Cancel handlers don't flip `running` before the worker thread exits.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

from core.security import esc, is_safe_url


# ── 1. XSS regression ────────────────────────────────────────────────────────

def test_esc_escapes_script_tag():
    assert "<script>" not in esc("<script>alert(1)</script>")
    assert "&lt;script&gt;" in esc("<script>alert(1)</script>")
    assert esc(None) == ""
    # Quotes are escaped too — important for attribute interpolation
    assert "&quot;" in esc('"') or "&#x27;" in esc("'") or '"' not in esc('"')


def test_indexing_report_escapes_malicious_url(tmp_path):
    from core.report_generator import ReportGenerator
    bad_url = 'https://example.com/"><script>alert(1)</script>'
    rows = [{
        "num": 1, "url": bad_url, "status": "Indexed",
        "priority": "High", "depth": 1, "url_type": "Homepage",
        "checked_at": "2026-05-15",
    }]
    out = tmp_path / "r.html"
    ReportGenerator().html(rows, out, {"Indexed": 1}, {"Homepage": {"Indexed": 1}}, None, [])
    html = out.read_text(encoding="utf-8")
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_audit_report_escapes_malicious_url():
    from core.seo_audit import generate_html_report
    bad_url = 'https://example.com/"><script>alert(1)</script>'
    audit = {
        "url": bad_url, "score": 50, "results": [],
        "issues": [], "warnings": [], "passed": [],
        "use_cases": [], "counts": {"pass": 0, "warning": 0, "fail": 0},
    }
    html = generate_html_report([audit], [], "20260515_000000")
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


# ── 2. SSRF guard ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("url,expected_ok", [
    ("http://127.0.0.1/",            False),
    ("http://localhost:8080/admin",  False),
    ("http://169.254.169.254/",      False),   # AWS/GCP metadata IP
    ("http://10.0.0.1/",             False),
    ("http://192.168.1.1/",          False),
    ("file:///etc/passwd",           False),
    ("ftp://example.com/",           False),
    ("",                             False),
    ("https://example.com/",         True),
    ("https://www.google.com/",      True),
])
def test_is_safe_url(url, expected_ok):
    ok, reason = is_safe_url(url)
    assert ok is expected_ok, f"{url!r} → ok={ok}, reason={reason}"


# ── 3. Cancel race ───────────────────────────────────────────────────────────

def test_index_cancel_does_not_flip_running_flag():
    """The cancel handler must NOT clear `_index_status['running']` itself —
    only the worker's `finally` should, after the thread actually exits.
    Otherwise a new run posted immediately after cancel races the dying thread.
    """
    from app import server

    # Force the running flag on as if a worker were active
    with server._lock:
        server._index_status["running"] = True

    # Simulate cancel
    client = server.app.test_client()
    resp = client.post("/api/index/cancel")
    assert resp.status_code == 200

    # After cancel, `running` is still True until the worker's finally runs.
    # (In a real run the worker thread would clear it within milliseconds.)
    with server._lock:
        assert server._index_status["running"] is True

    # Clean up so we don't affect other tests
    with server._lock:
        server._index_status["running"] = False
    server._index_cancel.clear()


def test_audit_cancel_does_not_flip_running_flag():
    from app import server
    with server._lock:
        server._audit_status["running"] = True
    client = server.app.test_client()
    resp = client.post("/api/audit/cancel")
    assert resp.status_code == 200
    with server._lock:
        assert server._audit_status["running"] is True
    with server._lock:
        server._audit_status["running"] = False
    server._audit_cancel.clear()


# ── 4. Settings whitelist ────────────────────────────────────────────────────

# ── 5. Schema validator — SSRF redirect protection (Stage 0-B) ───────────────

def test_schema_validator_rejects_ssrf_redirect(monkeypatch):
    """schema_validator.validate_url must refuse a URL that redirects to an
    internal host, returning ok=False rather than propagating the fetch.
    """
    import tools.schema_validator as sv

    def _raising_get(url, **kwargs):
        raise ValueError("SSRF: redirect target is a private address")

    # validate_url now fetches via tools._common.fetch_html (re-exported into
    # the schema_validator namespace), so patch that.
    monkeypatch.setattr(sv, "fetch_html", _raising_get)
    result = sv.validate_url("https://example.com/")
    assert result["ok"] is False
    assert "error" in result


def test_schema_validator_returns_ok_for_valid_page(monkeypatch):
    """validate_url must parse a minimal valid JSON-LD block and return ok=True."""
    import types
    import tools.schema_validator as sv

    html = (
        '<html><head>'
        '<script type="application/ld+json">'
        '{"@context":"https://schema.org","@type":"WebSite","name":"Test","url":"https://example.com"}'
        '</script>'
        '</head></html>'
    )

    fake_resp = types.SimpleNamespace(status_code=200, text=html)

    monkeypatch.setattr(sv, "fetch_html", lambda url, **kw: fake_resp)
    monkeypatch.setattr(sv, "validate_public_url", lambda url: url)

    result = sv.validate_url("https://example.com/")
    assert result["ok"] is True
    assert result["block_count"] == 1
    assert "WebSite" in result["types_found"]
    assert result["summary"]["errors"] == 0


# ── 4. Settings whitelist ────────────────────────────────────────────────────

def test_settings_post_rejects_unknown_keys(tmp_path, monkeypatch):
    """Arbitrary keys in /api/settings POST must be dropped, not written."""
    from app import server

    cfg = tmp_path / "config.json"
    cfg.write_text("{}")
    # Point CONFIG_PATH at the tmp file — server no longer reads from cwd.
    monkeypatch.setattr(server, "CONFIG_PATH", cfg)

    client = server.app.test_client()
    resp = client.post("/api/settings", json={
        "parallel_tabs": 4,                      # allowed
        "__evil__": {"path": "/etc/passwd"},     # rejected
        "slack": {"webhook_url": "x"},           # allowed
    })
    assert resp.status_code == 200
    body = resp.get_json()
    assert "__evil__" in body.get("rejected_keys", [])
    saved = __import__("json").loads(cfg.read_text())
    assert "__evil__" not in saved
    assert saved.get("parallel_tabs") == 4
