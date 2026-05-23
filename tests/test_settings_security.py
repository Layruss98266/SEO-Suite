"""
Tests for /api/settings secret masking, preserve-if-unchanged, and validation.
"""

import json
import sys
import types

# Stub playwright before importing server (mirrors test_new_tools).
_pw = types.ModuleType("playwright")
_pw.sync_api = types.ModuleType("playwright.sync_api")
_pw.sync_api.sync_playwright = None
_pw.sync_api.TimeoutError = TimeoutError
sys.modules.setdefault("playwright", _pw)
sys.modules.setdefault("playwright.sync_api", _pw.sync_api)

import pytest

from app import server
from app.server import _SECRET_SENTINEL


@pytest.fixture
def client(tmp_path, monkeypatch):
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({
        "groq_api_key": "gsk_realsecret123",
        "pagespeed_api_key": "AIzaRealKey",
        "indexnow_host": "example.com",
        "email": {"enabled": True, "smtp_host": "smtp.x.com", "smtp_port": 587,
                  "smtp_pass": "realpw", "smtp_user": "u@x.com"},
        "slack": {"enabled": False, "webhook_url": "https://hooks.slack.com/services/real"},
    }))
    monkeypatch.setattr(server, "CONFIG_PATH", cfg)
    server.app.config["TESTING"] = True
    with server.app.test_client() as c:
        yield c, cfg


class TestMasking:
    def test_secrets_masked_on_get(self, client):
        c, _ = client
        body = c.get("/api/settings").get_json()
        assert body["groq_api_key"] == _SECRET_SENTINEL
        assert body["pagespeed_api_key"] == _SECRET_SENTINEL
        assert body["email"]["smtp_pass"] == _SECRET_SENTINEL
        assert body["slack"]["webhook_url"] == _SECRET_SENTINEL

    def test_non_secrets_visible_on_get(self, client):
        c, _ = client
        body = c.get("/api/settings").get_json()
        assert body["indexnow_host"] == "example.com"
        assert body["email"]["smtp_host"] == "smtp.x.com"
        assert body["email"]["smtp_user"] == "u@x.com"


class TestPreserveOnSave:
    def test_sentinel_preserves_stored_secret(self, client):
        c, cfg = client
        # Save with the masked sentinel (user didn't touch the key)
        c.post("/api/settings", json={"groq_api_key": _SECRET_SENTINEL})
        saved = json.loads(cfg.read_text())
        assert saved["groq_api_key"] == "gsk_realsecret123"

    def test_real_value_overwrites(self, client):
        c, cfg = client
        c.post("/api/settings", json={"groq_api_key": "gsk_newkey"})
        saved = json.loads(cfg.read_text())
        assert saved["groq_api_key"] == "gsk_newkey"

    def test_nested_sentinel_preserves_only_that_field(self, client):
        c, cfg = client
        c.post("/api/settings", json={"email": {
            "enabled": True, "smtp_host": "smtp.new.com",
            "smtp_pass": _SECRET_SENTINEL, "smtp_user": "u@x.com",
        }})
        saved = json.loads(cfg.read_text())
        assert saved["email"]["smtp_pass"] == "realpw"      # preserved
        assert saved["email"]["smtp_host"] == "smtp.new.com"  # updated


class TestValidation:
    def test_bad_port_rejected(self, client):
        c, _ = client
        r = c.post("/api/settings", json={"email": {"smtp_port": 99999}})
        assert r.status_code == 400
        assert "port" in r.get_json()["error"].lower()

    def test_non_numeric_port_rejected(self, client):
        c, _ = client
        r = c.post("/api/settings", json={"email": {"smtp_port": "abc"}})
        assert r.status_code == 400

    def test_bad_indexnow_host_rejected(self, client):
        c, _ = client
        r = c.post("/api/settings", json={"indexnow_host": "https://example.com/path"})
        assert r.status_code == 400
        assert "host" in r.get_json()["error"].lower()

    def test_non_https_webhook_rejected(self, client):
        c, _ = client
        r = c.post("/api/settings", json={"slack": {"webhook_url": "http://insecure"}})
        assert r.status_code == 400

    def test_gsc_traversal_path_rejected(self, client):
        c, _ = client
        r = c.post("/api/settings", json={"gsc": {"credentials_file": "../../etc/passwd"}})
        assert r.status_code == 400

    def test_valid_save_succeeds(self, client):
        c, _ = client
        r = c.post("/api/settings", json={"indexnow_host": "valid-host.com",
                                          "email": {"smtp_port": 465}})
        assert r.status_code == 200
