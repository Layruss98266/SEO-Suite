"""Tests for core/sitemap_parser.py."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from core.sitemap_parser import SitemapParser


SIMPLE_SITEMAP = b"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://example.com/page1</loc></url>
  <url><loc>https://example.com/page2</loc></url>
  <url><loc>https://example.com/page3</loc></url>
</urlset>
"""

SITEMAP_INDEX = b"""<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <sitemap><loc>https://example.com/sitemap-1.xml</loc></sitemap>
  <sitemap><loc>https://example.com/sitemap-2.xml</loc></sitemap>
</sitemapindex>
"""

MALFORMED_SITEMAP = b"""<urlset>
  <url><loc>https://example.com/page-a</loc>
  <url><loc>https://example.com/page-b</loc></url>
</urlset>
"""


def _mock_response(content: bytes, status: int = 200):
    r = MagicMock()
    r.content = content
    r.text = content.decode("utf-8", errors="replace")
    r.status_code = status
    return r


class TestSitemapParserFetch:
    @patch("core.security.safe_requests_get")
    def test_parses_simple_sitemap(self, mock_get):
        mock_get.return_value = _mock_response(SIMPLE_SITEMAP)
        parser = SitemapParser()
        urls = parser.fetch("https://example.com/sitemap.xml")
        assert len(urls) == 3
        assert "https://example.com/page1" in urls
        assert "https://example.com/page2" in urls
        assert "https://example.com/page3" in urls

    @patch("core.security.safe_requests_get")
    def test_parses_sitemap_index(self, mock_get):
        # Each child sitemap returns distinct URLs so filter_public_urls
        # doesn't dedupe them down.
        leaf_a = b"""<?xml version="1.0"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://example.com/a1</loc></url>
  <url><loc>https://example.com/a2</loc></url>
</urlset>"""
        leaf_b = b"""<?xml version="1.0"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://example.com/b1</loc></url>
</urlset>"""
        mock_get.side_effect = [
            _mock_response(SITEMAP_INDEX),
            _mock_response(leaf_a),
            _mock_response(leaf_b),
        ]
        parser = SitemapParser()
        urls = parser.fetch("https://example.com/sitemap_index.xml")
        assert len(urls) == 3
        assert "https://example.com/a1" in urls
        assert "https://example.com/b1" in urls

    @patch("core.security.safe_requests_get")
    def test_rejects_private_sitemap_url(self, mock_get):
        parser = SitemapParser()
        urls = parser.fetch("http://127.0.0.1/sitemap.xml")
        assert urls == []
        mock_get.assert_not_called()

    @patch("core.security.safe_requests_get")
    def test_network_error_returns_empty(self, mock_get):
        mock_get.side_effect = ConnectionError("boom")
        parser = SitemapParser()
        urls = parser.fetch("https://example.com/sitemap.xml")
        assert urls == []

    @patch("core.security.safe_requests_get")
    def test_malformed_xml_falls_back_to_regex(self, mock_get):
        # Genuinely broken XML — neither ET nor lxml (even with recover=True)
        # can build a tree, forcing the regex fallback in _fallback_parse.
        truly_broken = (
            b"NOT XML AT ALL <loc>https://example.com/recovered-a</loc> "
            b"trailing garbage <loc>https://example.com/recovered-b</loc> end"
        )
        mock_get.return_value = _mock_response(truly_broken)
        parser = SitemapParser()
        urls = parser.fetch("https://example.com/sitemap.xml")
        # Regex fallback extracts both URLs.
        assert any("recovered-a" in u for u in urls)
        assert any("recovered-b" in u for u in urls)

    @patch("core.security.safe_requests_get")
    def test_cycle_protection(self, mock_get):
        # Sitemap that points to itself — recursion would never terminate
        # without _seen tracking.
        self_ref = b"""<?xml version="1.0"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <sitemap><loc>https://example.com/sitemap.xml</loc></sitemap>
</sitemapindex>"""
        mock_get.return_value = _mock_response(self_ref)
        parser = SitemapParser()
        # Should return [] without infinite loop.
        urls = parser.fetch("https://example.com/sitemap.xml")
        assert urls == []
        # Only one fetch should have happened (cycle detected on the second).
        assert mock_get.call_count == 1


class TestSitemapParserFromDomain:
    @patch("core.security.safe_requests_get")
    def test_finds_at_standard_path(self, mock_get):
        mock_get.return_value = _mock_response(SIMPLE_SITEMAP)
        parser = SitemapParser()
        urls = parser.from_domain("example.com")
        assert len(urls) == 3

    @patch("core.security.safe_requests_get")
    def test_falls_back_to_homepage_when_no_sitemap(self, mock_get):
        # Always return empty / 404-shaped content.
        mock_get.return_value = _mock_response(b"<html>not a sitemap</html>")
        parser = SitemapParser()
        urls = parser.from_domain("example.com")
        # Falls back to homepage only.
        assert urls == ["https://example.com"]

    def test_normalises_bare_domain(self):
        parser = SitemapParser()
        with patch("core.security.safe_requests_get") as mock_get:
            mock_get.return_value = _mock_response(SIMPLE_SITEMAP)
            parser.from_domain("example.com")
            # First call should target https:// scheme.
            call_url = mock_get.call_args_list[0].args[0]
            assert call_url.startswith("https://example.com")
