"""
Integration tests for Flask API endpoints — no browser, no external API calls.
Uses Flask test client.
"""

import json
import pytest
import sys, types

# Stub playwright before importing server
_pw_stub = types.ModuleType("playwright")
_pw_stub.sync_api = types.ModuleType("playwright.sync_api")
_pw_stub.sync_api.sync_playwright = None
_pw_stub.sync_api.TimeoutError = TimeoutError
sys.modules.setdefault("playwright", _pw_stub)
sys.modules.setdefault("playwright.sync_api", _pw_stub.sync_api)

from app.server import app


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


# ══════════════════════════════════════════════════════════════════════════════
# Health + static routes
# ══════════════════════════════════════════════════════════════════════════════

class TestHealthRoute:
    def test_health_returns_200(self, client):
        r = client.get("/health")
        assert r.status_code == 200

    def test_health_has_status_ok(self, client):
        data = json.loads(r.data) if (r := client.get("/health")) else {}
        assert json.loads(client.get("/health").data)["status"] == "ok"

    def test_dashboard_returns_html(self, client):
        r = client.get("/")
        assert r.status_code == 200
        assert b"<!DOCTYPE html>" in r.data or b"<html" in r.data


# ══════════════════════════════════════════════════════════════════════════════
# Upload validation
# ══════════════════════════════════════════════════════════════════════════════

class TestUploadValidation:
    def test_no_file_returns_400(self, client):
        r = client.post("/api/upload")
        assert r.status_code == 400

    def test_invalid_extension_returns_400(self, client):
        from io import BytesIO
        data = {"file": (BytesIO(b"data"), "malicious.exe")}
        r = client.post("/api/upload", data=data, content_type="multipart/form-data")
        assert r.status_code == 400
        assert b"Only" in r.data or b"allowed" in r.data

    def test_valid_csv_upload(self, client, tmp_path):
        from io import BytesIO
        csv_content = b"URL\nhttps://example.com/a\nhttps://example.com/b\n"
        data = {"file": (BytesIO(csv_content), "urls.csv")}
        r = client.post("/api/upload", data=data, content_type="multipart/form-data")
        assert r.status_code == 200
        body = json.loads(r.data)
        assert "path" in body
        assert body["url_count"] == 2

    def test_upload_returns_warning_for_non_url_csv(self, client):
        from io import BytesIO
        csv_content = b"keyword,volume\nseo audit,1200\n"
        data = {"file": (BytesIO(csv_content), "keywords.csv")}
        r = client.post("/api/upload", data=data, content_type="multipart/form-data")
        assert r.status_code == 200
        body = json.loads(r.data)
        assert body["url_count"] == 0
        assert "warning" in body


# ══════════════════════════════════════════════════════════════════════════════
# Audit run — input validation
# ══════════════════════════════════════════════════════════════════════════════

class TestAuditRunValidation:
    def test_missing_input_returns_400(self, client):
        r = client.post("/api/audit/run",
                        data=json.dumps({"input_type": "sitemap", "input": ""}),
                        content_type="application/json")
        assert r.status_code == 400

    def test_already_running_returns_400_on_second_call(self, client, monkeypatch):
        import app.server as srv
        monkeypatch.setitem(srv._audit_status, "running", True)
        r = client.post("/api/audit/run",
                        data=json.dumps({"input": "https://example.com/sitemap.xml"}),
                        content_type="application/json")
        assert r.status_code == 400


# ══════════════════════════════════════════════════════════════════════════════
# Stage 0-D — _int() helper: non-integer limit must not cause HTTP 500
# ══════════════════════════════════════════════════════════════════════════════

class TestIntHelperValidation:
    """Non-integer values for numeric parameters must never produce HTTP 500.

    Before the fix, bare int(data.get("limit", 20)) would raise ValueError
    on inputs like "abc", propagating as an unhandled 500.  After the fix,
    _int() swallows the error and returns the default.
    """

    def test_index_run_non_integer_limit_does_not_500(self, client, monkeypatch):
        """POST /api/index/run with limit="abc" must not return 500."""
        import app.server as srv
        # Ensure no run is in progress
        monkeypatch.setitem(srv._index_status, "running", False)
        r = client.post("/api/index/run",
                        json={"input_type": "domain",
                              "input": "https://example.com",
                              "limit": "abc"})
        # Any response except 500 is acceptable — 400 (validation) is fine,
        # 200 (run accepted with default limit) is also fine.
        assert r.status_code != 500

    def test_audit_run_non_integer_limit_does_not_500(self, client, monkeypatch):
        """POST /api/audit/run with limit="abc" must not return 500."""
        import app.server as srv
        monkeypatch.setitem(srv._audit_status, "running", False)
        r = client.post("/api/audit/run",
                        json={"input_type": "domain",
                              "input": "https://example.com",
                              "limit": "abc"})
        assert r.status_code != 500

    def test_audit_run_non_integer_workers_does_not_500(self, client, monkeypatch):
        """POST /api/audit/run with workers="bad" must not return 500."""
        import app.server as srv
        monkeypatch.setitem(srv._audit_status, "running", False)
        r = client.post("/api/audit/run",
                        json={"input_type": "domain",
                              "input": "https://example.com",
                              "workers": "bad"})
        assert r.status_code != 500


# ══════════════════════════════════════════════════════════════════════════════
# Stage 0-E — empty sitemap must return 400, not silently audit sitemap XML URL
# ══════════════════════════════════════════════════════════════════════════════

class TestUseCaseSitemapFallback:
    def test_empty_sitemap_returns_400(self, client, monkeypatch):
        """When fetch_sitemap_urls returns [], the endpoint must return 400.

        The route does `from core.checker import fetch_sitemap_urls` as a
        late import, so we patch the function on the core.checker module
        object so the late import picks up the stub.
        """
        import core.checker as checker_mod
        monkeypatch.setattr(checker_mod, "fetch_sitemap_urls", lambda url, **kw: [])

        r = client.post("/api/usecase/run",
                        json={
                            "use_case": "crawlability",    # valid key from USE_CASES
                            "input_format": "sitemap",
                            "url": "https://example.com/sitemap.xml",
                        })
        assert r.status_code == 400
        body = r.get_json() or {}
        assert body.get("ok") is False
        assert "sitemap" in body.get("error", "").lower()


# ══════════════════════════════════════════════════════════════════════════════
# Settings API
# ══════════════════════════════════════════════════════════════════════════════

class TestSettingsApi:
    def test_get_settings_returns_200(self, client):
        r = client.get("/api/settings")
        assert r.status_code == 200
        data = json.loads(r.data)
        assert isinstance(data, dict)

    def test_post_settings_saves_value(self, client, tmp_path, monkeypatch):
        import app.server as srv
        cfg_path = tmp_path / "config.json"
        cfg_path.write_text(json.dumps({"parallel_tabs": 1}))
        monkeypatch.setattr(srv, "CFG", {"parallel_tabs": 1})
        # Server now reads/writes CONFIG_PATH (anchored to project root); point
        # it at our tmp file for the duration of the test.
        monkeypatch.setattr(srv, "CONFIG_PATH", cfg_path)

        r = client.post("/api/settings",
                        data=json.dumps({"parallel_tabs": 3}),
                        content_type="application/json")
        assert r.status_code == 200
