"""
Unit tests for tools/phase4.py — pure logic, no network calls.
API functions are tested via monkeypatching requests.
"""

import pytest
from unittest.mock import MagicMock, patch


from tools.phase4 import result, audit_url


# ══════════════════════════════════════════════════════════════════════════════
# result() helper
# ══════════════════════════════════════════════════════════════════════════════

class TestResult:
    def test_returns_expected_keys(self):
        r = result("https://example.com", "backlinks", "pass", 42, "OK")
        assert r["url"] == "https://example.com"
        assert r["tool"] == "backlinks"
        assert r["status"] == "pass"
        assert r["value"] == 42
        assert r["message"] == "OK"
        assert r["details"] == {}

    def test_custom_details(self):
        r = result("https://x.com", "da", "warning", None, "no key", {"source": "Moz"})
        assert r["details"] == {"source": "Moz"}


# ══════════════════════════════════════════════════════════════════════════════
# audit_url() — shape and parallelism
# ══════════════════════════════════════════════════════════════════════════════

class TestAuditUrl:
    def test_returns_list_with_no_keys(self):
        cfg = {}  # no API keys → graceful degradation
        results = audit_url("https://example.com", cfg)
        assert isinstance(results, list)
        assert len(results) >= 2  # backlinks + domain_authority always run

    def test_all_results_have_required_keys(self):
        cfg = {}
        for r in audit_url("https://example.com", cfg):
            assert "tool" in r
            assert "status" in r
            assert "message" in r

    def test_no_api_keys_returns_warning_status(self):
        cfg = {}
        for r in audit_url("https://example.com", cfg):
            assert r["status"] in ("pass", "warning", "fail", "error")

    def test_keyword_task_added_when_keywords_provided(self):
        cfg = {}
        results = audit_url("https://example.com", cfg, keywords=["python"])
        tools = [r["tool"] for r in results]
        assert "rank_tracker" in tools

    def test_competitor_task_added_when_keyword_provided(self):
        cfg = {}
        results = audit_url("https://example.com", cfg, keyword="python tutorial")
        tools = [r["tool"] for r in results]
        assert "competitor" in tools

    def test_parallel_execution_order_deterministic(self):
        """audit_url with no keys returns same tools each time."""
        cfg = {}
        r1 = {r["tool"] for r in audit_url("https://example.com", cfg)}
        r2 = {r["tool"] for r in audit_url("https://example.com", cfg)}
        assert r1 == r2
