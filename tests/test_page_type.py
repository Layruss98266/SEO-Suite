"""Tests for tools.page_type — page-type auto-detector."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from tools.page_type import THRESHOLD, detect_page_type


def _run(url: str, html: str = "") -> dict:
    """Bypass SSRF + fetch by patching validate_public_url and passing html."""
    with patch("tools.page_type.validate_public_url", return_value=url):
        return detect_page_type(url, html=html)


# ─── URL pattern detection (no fetch) ─────────────────────────────────────────

class TestUrlPatternDetection:
    @pytest.mark.parametrize("url,expected", [
        ("https://example.com/course/python-101", "course"),
        ("https://example.com/courses/ml/intro", "course"),
        ("https://example.com/training/aws",     "course"),
        ("https://example.com/learn/sql",        "course"),
        ("https://example.com/blog/hello-world", "blog"),
        ("https://example.com/news/2026/launch", "blog"),
        ("https://example.com/article/abc",      "blog"),
        ("https://example.com/product/widget",   "product"),
        ("https://example.com/shop/sku-123",     "product"),
        ("https://example.com/p/abc-def",        "product"),
    ])
    def test_url_pattern_alone_is_not_enough(self, url, expected):
        # 0.20 url weight alone is below the 0.40 threshold → generic
        res = _run(url, html="<html><body>nothing</body></html>")
        assert res["ok"] is True
        assert res["type"] == "generic"
        assert any(s["name"].startswith("url-pattern:") for s in res["signals"])

    def test_url_plus_og_type_clears_threshold(self):
        html = '<html><head><meta property="og:type" content="article"></head></html>'
        res = _run("https://example.com/blog/post-1", html=html)
        assert res["ok"] is True
        assert res["type"] == "blog"
        assert res["confidence"] >= THRESHOLD


# ─── JSON-LD schema detection ─────────────────────────────────────────────────

class TestJsonLdSchema:
    @pytest.mark.parametrize("schema_type,expected", [
        ("Course",       "course"),
        ("Product",      "product"),
        ("Article",      "blog"),
        ("BlogPosting",  "blog"),
        ("NewsArticle",  "blog"),
    ])
    def test_schema_detected(self, schema_type, expected):
        html = (
            '<html><head><script type="application/ld+json">'
            f'{{"@context":"https://schema.org","@type":"{schema_type}","name":"x"}}'
            '</script></head><body></body></html>'
        )
        res = _run("https://example.com/x", html=html)
        assert res["ok"] is True
        assert res["type"] == expected
        assert res["confidence"] >= 0.40
        assert any(s["name"].lower() == f"schema:{schema_type.lower()}" for s in res["signals"])

    def test_schema_in_graph_array(self):
        html = (
            '<html><head><script type="application/ld+json">'
            '{"@context":"https://schema.org","@graph":['
            '{"@type":"WebSite"},{"@type":"Product","name":"foo"}]}'
            '</script></head></html>'
        )
        res = _run("https://example.com/whatever", html=html)
        assert res["type"] == "product"

    def test_malformed_jsonld_ignored(self):
        html = (
            '<html><head><script type="application/ld+json">{not valid json</script>'
            '</head><body>plain page</body></html>'
        )
        res = _run("https://example.com/", html=html)
        # Should not crash; falls to generic with no signals
        assert res["ok"] is True
        assert res["type"] == "generic"


# ─── Confidence threshold ─────────────────────────────────────────────────────

class TestConfidenceThreshold:
    def test_empty_page_is_generic(self):
        res = _run("https://example.com/", html="<html><body></body></html>")
        assert res["type"] == "generic"
        assert res["confidence"] < THRESHOLD

    def test_weak_signals_below_threshold_are_generic(self):
        # Only a blog url pattern (0.20) — under 0.40
        res = _run("https://example.com/blog/", html="<html></html>")
        assert res["type"] == "generic"

    def test_structural_combo_can_win(self):
        # Two strong structural signals + url pattern → 0.15 + 0.15 + 0.20 = 0.50
        html = (
            '<html><body>'
            '<span itemprop="price">$49.99</span>'
            '<button>Add to cart</button>'
            '<p>Buy now while in stock.</p>'
            '</body></html>'
        )
        res = _run("https://example.com/product/widget", html=html)
        assert res["type"] == "product"
        assert res["confidence"] >= THRESHOLD


# ─── Error handling ───────────────────────────────────────────────────────────

class TestErrors:
    def test_invalid_url_returns_error(self):
        # Don't patch validate_public_url — let it reject
        res = detect_page_type("not-a-url")
        assert res["ok"] is False
        assert "error" in res
