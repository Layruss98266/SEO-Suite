"""Tests for the Settings 'test connection' dispatcher and route (no network)."""

import sys
import types
from unittest.mock import patch

_pw = types.ModuleType("playwright")
_pw.sync_api = types.ModuleType("playwright.sync_api")
_pw.sync_api.sync_playwright = None
_pw.sync_api.TimeoutError = TimeoutError
sys.modules.setdefault("playwright", _pw)
sys.modules.setdefault("playwright.sync_api", _pw.sync_api)

import pytest

from tools.connection_tests import run_test


class TestDispatcher:
    def test_unknown_provider(self):
        r = run_test("nope", {}, {})
        assert r["ok"] is False and "Unknown provider" in r["message"]

    def test_missing_credentials_no_network(self):
        for prov in ("groq", "moz", "serpapi", "dataforseo", "bing", "pagespeed"):
            r = run_test(prov, {}, {})
            assert r["ok"] is False
            assert r["message"]  # has a helpful message

    def test_sentinel_falls_back_to_config(self):
        # User sends the masked sentinel; the test must use the stored key,
        # and a stored Groq key reaches _chat (which we stub to succeed).
        with patch("tools.ai_assist._chat", return_value="ok") as chat:
            r = run_test("groq", {"groq_api_key": "••••••••"},
                         {"groq_api_key": "gsk_stored"})
        assert r["ok"] is True
        # _chat called with the stored key, not the sentinel
        assert chat.call_args[0][1] == "gsk_stored"

    def test_typed_value_preferred_over_config(self):
        with patch("tools.ai_assist._chat", return_value="ok") as chat:
            run_test("groq", {"groq_api_key": "gsk_typed"}, {"groq_api_key": "gsk_stored"})
        assert chat.call_args[0][1] == "gsk_typed"


class TestRoute:
    @pytest.fixture
    def client(self):
        from app import server
        server.app.config["TESTING"] = True
        with server.app.test_client() as c:
            yield c

    def test_route_returns_json(self, client):
        r = client.post("/api/settings/test/groq", json={})
        assert r.status_code == 200
        assert r.get_json()["ok"] is False  # no key configured in test env

    def test_route_unknown_provider(self, client):
        r = client.post("/api/settings/test/bogus", json={})
        assert r.status_code == 200
        assert r.get_json()["ok"] is False
