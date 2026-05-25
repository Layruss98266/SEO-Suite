"""
Tests for new routes added in the gap-fill session:
  - /api/tools/gsc_position_tracker
  - /api/tools/gsc_ctr_analyzer
  - /api/tools/gsc_coverage_errors
  - /api/tools/gsc_sitemaps_status
  - /api/tools/notify_test
  - /api/audit/phase/<n>
"""

import json
import pytest
import sys
import types

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
# GSC tools — all require GSC enabled; test validation guards
# ══════════════════════════════════════════════════════════════════════════════

class TestGscPositionTracker:
    def test_missing_url_returns_400(self, client):
        r = client.post("/api/tools/gsc_position_tracker",
                        json={"site_url": "https://example.com/"})
        assert r.status_code == 400

    def test_missing_site_url_returns_400(self, client):
        r = client.post("/api/tools/gsc_position_tracker",
                        json={"url": "https://example.com/page"})
        assert r.status_code == 400

    def test_gsc_disabled_returns_400(self, client, monkeypatch):
        import app.server as srv
        monkeypatch.setitem(srv.CFG, "gsc", {"enabled": False})
        r = client.post("/api/tools/gsc_position_tracker",
                        json={"url": "https://example.com/page",
                              "site_url": "https://example.com/"})
        assert r.status_code == 400
        assert b"not enabled" in r.data.lower() or b"GSC" in r.data

    def test_private_url_rejected(self, client):
        r = client.post("/api/tools/gsc_position_tracker",
                        json={"url": "http://192.168.1.1/page",
                              "site_url": "https://example.com/"})
        assert r.status_code in (400, 422)


class TestGscCtrAnalyzer:
    def test_missing_site_url_returns_400(self, client):
        r = client.post("/api/tools/gsc_ctr_analyzer", json={})
        assert r.status_code == 400

    def test_gsc_disabled_returns_400(self, client, monkeypatch):
        import app.server as srv
        monkeypatch.setitem(srv.CFG, "gsc", {"enabled": False})
        r = client.post("/api/tools/gsc_ctr_analyzer",
                        json={"site_url": "https://example.com/"})
        assert r.status_code == 400

    def test_private_site_url_rejected(self, client):
        r = client.post("/api/tools/gsc_ctr_analyzer",
                        json={"site_url": "http://localhost/"})
        assert r.status_code in (400, 422)


class TestGscCoverageErrors:
    def test_missing_site_url_returns_400(self, client):
        r = client.post("/api/tools/gsc_coverage_errors", json={})
        assert r.status_code == 400

    def test_gsc_disabled_returns_400(self, client, monkeypatch):
        import app.server as srv
        monkeypatch.setitem(srv.CFG, "gsc", {"enabled": False})
        r = client.post("/api/tools/gsc_coverage_errors",
                        json={"site_url": "https://example.com/"})
        assert r.status_code == 400

    def test_private_ip_rejected(self, client):
        r = client.post("/api/tools/gsc_coverage_errors",
                        json={"site_url": "http://10.0.0.1/"})
        assert r.status_code in (400, 422)


class TestGscSitemapsStatus:
    def test_missing_site_url_returns_400(self, client):
        r = client.post("/api/tools/gsc_sitemaps_status", json={})
        assert r.status_code == 400

    def test_gsc_disabled_returns_400(self, client, monkeypatch):
        import app.server as srv
        monkeypatch.setitem(srv.CFG, "gsc", {"enabled": False})
        r = client.post("/api/tools/gsc_sitemaps_status",
                        json={"site_url": "https://example.com/"})
        assert r.status_code == 400

    def test_gsc_enabled_but_bad_creds_returns_400(self, client, monkeypatch):
        import app.server as srv
        from app.blueprints import tools as tools_bp
        monkeypatch.setitem(srv.CFG, "gsc",
                            {"enabled": True, "credentials_file": "/nonexistent.json"})
        def _bad_build():
            raise FileNotFoundError("no creds")
        # Patch the blueprint's bound name, not server's, since the route lives there.
        monkeypatch.setattr(tools_bp, "build_gsc_service", _bad_build)
        r = client.post("/api/tools/gsc_sitemaps_status",
                        json={"site_url": "https://example.com/"})
        assert r.status_code == 400
        assert b"auth" in r.data.lower()


# ══════════════════════════════════════════════════════════════════════════════
# Notify test
# ══════════════════════════════════════════════════════════════════════════════

class TestNotifyTest:
    def test_invalid_channel_returns_400(self, client):
        r = client.post("/api/tools/notify_test", json={"channel": "discord"})
        assert r.status_code == 400
        body = json.loads(r.data)
        assert not body["ok"]

    def test_missing_channel_returns_400(self, client):
        r = client.post("/api/tools/notify_test", json={})
        assert r.status_code == 400

    def test_valid_channel_accepted(self, client, monkeypatch):
        """With a mocked NotificationService, all three channels should return ok."""
        import app.server as srv

        class _FakeNotifier:
            def __init__(self, cfg): pass
            def send_email(self, *a, **kw): pass
            def send_slack(self, *a): pass
            def send_teams(self, *a): pass

        monkeypatch.setattr("core.notifier.NotificationService", _FakeNotifier)
        for ch in ("email", "slack", "teams"):
            r = client.post("/api/tools/notify_test", json={"channel": ch})
            body = json.loads(r.data)
            assert body.get("ok") is True, f"channel={ch} failed: {body}"


# ══════════════════════════════════════════════════════════════════════════════
# Individual phase execution
# ══════════════════════════════════════════════════════════════════════════════

class TestAuditPhase:
    def test_invalid_phase_returns_400(self, client):
        for p in (0, 5, 99):
            r = client.post(f"/api/audit/phase/{p}",
                            json={"url": "https://example.com/"})
            assert r.status_code == 400, f"phase {p} should be 400"

    def test_missing_url_returns_400(self, client):
        r = client.post("/api/audit/phase/1", json={})
        assert r.status_code == 400

    def test_private_url_rejected(self, client):
        r = client.post("/api/audit/phase/1",
                        json={"url": "http://127.0.0.1/"})
        assert r.status_code in (400, 422)

    def test_phase2_without_api_key_returns_400(self, client, monkeypatch):
        import app.server as srv
        monkeypatch.setitem(srv.CFG, "pagespeed_api_key", "")
        r = client.post("/api/audit/phase/2",
                        json={"url": "https://example.com/"})
        assert r.status_code == 400
        assert b"PageSpeed" in r.data or b"api" in r.data.lower()

    def test_phase3_without_gsc_returns_400(self, client, monkeypatch):
        import app.server as srv
        monkeypatch.setitem(srv.CFG, "gsc", {"enabled": False})
        r = client.post("/api/audit/phase/3",
                        json={"url": "https://example.com/"})
        assert r.status_code == 400
        assert b"GSC" in r.data or b"not enabled" in r.data.lower()

    def test_phase4_without_credentials_returns_400(self, client, monkeypatch):
        import app.server as srv
        for k in ("dataforseo_login", "dataforseo_password",
                  "moz_access_id", "moz_secret_key", "serpapi_key"):
            monkeypatch.setitem(srv.CFG, k, "")
        r = client.post("/api/audit/phase/4",
                        json={"url": "https://example.com/"})
        assert r.status_code == 400

    def test_phase1_runs_with_mocked_tools(self, client, monkeypatch):
        """Phase 1 should succeed when tool functions are mocked."""
        _pass = lambda url: {"tool": "mock", "status": "pass", "value": None,
                             "message": "ok", "details": {}, "url": url}
        import tools.phase1 as p1
        for fn in ("robots_check", "http_status_check", "redirect_check",
                   "canonical_check", "title_check", "meta_description_check",
                   "heading_check", "image_alt_check", "word_count_check",
                   "broken_link_check", "internal_links_check",
                   "sitemap_validate", "schema_check"):
            monkeypatch.setattr(p1, fn, _pass, raising=False)
        r = client.post("/api/audit/phase/1",
                        json={"url": "https://example.com/"})
        assert r.status_code == 200
        body = json.loads(r.data)
        assert body["ok"] is True
        assert "results" in body
        assert body["phase"] == 1
