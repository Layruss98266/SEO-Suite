"""
Unit tests for core/checker.py — pure logic functions only.
No network, no browser, no filesystem side-effects.
"""

import csv
import json
import os
import tempfile
from pathlib import Path

import pytest

# ── Helpers to isolate imports ────────────────────────────────────────────────
# Prevent playwright sys.exit on import by pre-patching if needed
import sys, types

# Stub playwright so tests don't need a browser installed
_pw_stub = types.ModuleType("playwright")
_pw_stub.sync_api = types.ModuleType("playwright.sync_api")
_pw_stub.sync_api.sync_playwright = None
_pw_stub.sync_api.TimeoutError = TimeoutError
sys.modules.setdefault("playwright", _pw_stub)
sys.modules.setdefault("playwright.sync_api", _pw_stub.sync_api)

from core.checker import (
    filter_urls,
    get_crawl_depth,
    get_url_type,
    get_priority_score,
    compare_runs,
    _normalize_url,
    load_from_csv_excel,
)


# ══════════════════════════════════════════════════════════════════════════════
# filter_urls
# ══════════════════════════════════════════════════════════════════════════════

class TestFilterUrls:
    URLS = [
        "https://example.com/category/foo",
        "https://example.com/blog/bar",
        "https://example.com/course/python",
        "https://example.com/tag/python",
    ]

    def test_no_pattern_returns_all(self):
        assert filter_urls(self.URLS, "") == self.URLS

    def test_pattern_filters_correctly(self):
        result = filter_urls(self.URLS, "/category/")
        assert result == ["https://example.com/category/foo"]

    def test_pattern_case_insensitive(self):
        result = filter_urls(self.URLS, "/BLOG/")
        assert result == ["https://example.com/blog/bar"]

    def test_empty_list(self):
        assert filter_urls([], "/category/") == []

    def test_no_match_returns_empty(self):
        assert filter_urls(self.URLS, "/nonexistent/") == []


# ══════════════════════════════════════════════════════════════════════════════
# get_crawl_depth
# ══════════════════════════════════════════════════════════════════════════════

class TestGetCrawlDepth:
    def test_homepage_depth_zero(self):
        assert get_crawl_depth("https://example.com/") == 0
        assert get_crawl_depth("https://example.com") == 0

    def test_single_segment(self):
        assert get_crawl_depth("https://example.com/blog") == 1

    def test_two_segments(self):
        assert get_crawl_depth("https://example.com/blog/my-post") == 2

    def test_three_segments(self):
        assert get_crawl_depth("https://example.com/a/b/c") == 3


# ══════════════════════════════════════════════════════════════════════════════
# get_url_type
# ══════════════════════════════════════════════════════════════════════════════

class TestGetUrlType:
    def test_homepage(self):
        assert get_url_type("https://example.com/") == "Homepage"
        assert get_url_type("https://example.com") == "Homepage"

    def test_blog_segment(self):
        assert get_url_type("https://example.com/blog/my-post") == "Blog"

    def test_category_segment(self):
        assert get_url_type("https://example.com/category/python") == "Category"


# ══════════════════════════════════════════════════════════════════════════════
# get_priority_score
# ══════════════════════════════════════════════════════════════════════════════

class TestGetPriorityScore:
    def test_homepage_is_high(self):
        assert get_priority_score("https://example.com/") == "High"

    def test_high_value_pattern(self):
        assert get_priority_score("https://example.com/course/python") == "High"

    def test_low_value_pattern(self):
        assert get_priority_score("https://example.com/tag/python") == "Low"

    def test_medium_depth(self):
        # depth 2, no special pattern
        score = get_priority_score("https://example.com/blog/my-post")
        assert score == "Medium"

    def test_deep_url_is_low(self):
        score = get_priority_score("https://example.com/a/b/c/d/e")
        assert score == "Low"


# ══════════════════════════════════════════════════════════════════════════════
# _normalize_url
# ══════════════════════════════════════════════════════════════════════════════

class TestNormalizeUrl:
    def test_strips_scheme(self):
        assert not _normalize_url("https://example.com/").startswith("http")

    def test_strips_www(self):
        assert not _normalize_url("https://www.example.com/path").startswith("www")

    def test_strips_trailing_slash(self):
        assert not _normalize_url("https://example.com/path/").endswith("/")

    def test_strips_fragment(self):
        assert "#" not in _normalize_url("https://example.com/path#section")

    def test_lowercases(self):
        assert _normalize_url("https://EXAMPLE.COM/Path") == _normalize_url("https://example.com/path")


# ══════════════════════════════════════════════════════════════════════════════
# compare_runs
# ══════════════════════════════════════════════════════════════════════════════

class TestCompareRuns:
    def _write_csv(self, rows: list[dict], path: Path):
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["URL", "Google Indexed"])
            w.writeheader()
            w.writerows(rows)

    def test_detects_newly_indexed(self, tmp_path):
        prev = tmp_path / "prev.csv"
        self._write_csv([
            {"URL": "https://example.com/a", "Google Indexed": "Not Indexed"},
            {"URL": "https://example.com/b", "Google Indexed": "Indexed"},
        ], prev)
        current = {
            "https://example.com/a": "Indexed",
            "https://example.com/b": "Indexed",
        }
        result = compare_runs(current, prev)
        assert "https://example.com/a" in result["newly_indexed"]
        assert result["newly_deindexed"] == []

    def test_detects_newly_deindexed(self, tmp_path):
        prev = tmp_path / "prev.csv"
        self._write_csv([
            {"URL": "https://example.com/c", "Google Indexed": "Indexed"},
        ], prev)
        current = {"https://example.com/c": "Not Indexed"}
        result = compare_runs(current, prev)
        assert "https://example.com/c" in result["newly_deindexed"]
        assert result["newly_indexed"] == []

    def test_no_change(self, tmp_path):
        prev = tmp_path / "prev.csv"
        self._write_csv([
            {"URL": "https://example.com/d", "Google Indexed": "Indexed"},
        ], prev)
        current = {"https://example.com/d": "Indexed"}
        result = compare_runs(current, prev)
        assert result["newly_indexed"] == []
        assert result["newly_deindexed"] == []


# ══════════════════════════════════════════════════════════════════════════════
# load_from_csv_excel
# ══════════════════════════════════════════════════════════════════════════════

class TestLoadFromCsvExcel:
    def test_loads_urls_from_csv(self, tmp_path):
        p = tmp_path / "urls.csv"
        p.write_text("URL\nhttps://example.com/a\nhttps://example.com/b\nnot-a-url\n")
        result = load_from_csv_excel(str(p))
        assert "https://example.com/a" in result
        assert "https://example.com/b" in result
        assert "not-a-url" not in result

    def test_missing_file_returns_empty(self):
        result = load_from_csv_excel("/nonexistent/path/file.csv")
        assert result == []

    def test_raises_for_header_only_csv_without_url_column(self, tmp_path):
        p = tmp_path / "keywords.csv"
        p.write_text("keyword,volume\nseo audit,1200\nindex checker,400\n", encoding="utf-8")
        with pytest.raises(ValueError, match="URL column|http\\(s\\) URL"):
            load_from_csv_excel(str(p))

    def test_loads_urls_from_named_url_column_even_with_extra_columns(self, tmp_path):
        p = tmp_path / "mixed.csv"
        p.write_text(
            "Name,URL,Notes\n"
            "Home,https://example.com/,primary\n"
            "Docs,https://example.com/docs,secondary\n",
            encoding="utf-8",
        )
        assert load_from_csv_excel(str(p)) == [
            "https://example.com/",
            "https://example.com/docs",
        ]


# ══════════════════════════════════════════════════════════════════════════════
# Stage 0-A regression — fetch_sitemap_urls SSRF redirect protection
# ══════════════════════════════════════════════════════════════════════════════

class TestFetchSitemapUrlsSsrf:
    """fetch_sitemap_urls must not follow redirects that land on private IPs."""

    def test_redirect_to_private_ip_returns_empty(self, monkeypatch):
        """Simulates a sitemap URL that redirects to an internal host.

        safe_requests_get raises ValueError for private-IP redirects; the
        function must catch that and return [] rather than propagating.

        The import inside fetch_sitemap_urls is a local `from core.security
        import safe_requests_get as _safe_get`, so we patch at the source
        module (core.security) rather than at core.checker.
        """
        import core.security as sec

        def _raising_get(url, **kwargs):
            raise ValueError("SSRF: redirect target is a private address")

        monkeypatch.setattr(sec, "safe_requests_get", _raising_get)

        import core.checker as checker_mod
        result = checker_mod.fetch_sitemap_urls("https://example.com/sitemap.xml")
        assert result == []

    def test_network_error_returns_empty(self, monkeypatch):
        """Any network failure must also return [] without raising."""
        import core.security as sec

        def _failing_get(url, **kwargs):
            raise ConnectionError("Network unreachable")

        monkeypatch.setattr(sec, "safe_requests_get", _failing_get)

        import core.checker as checker_mod
        result = checker_mod.fetch_sitemap_urls("https://example.com/sitemap.xml")
        assert result == []
