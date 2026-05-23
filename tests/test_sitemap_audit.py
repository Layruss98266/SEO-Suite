from unittest.mock import patch, MagicMock

from tools.sitemap_audit import audit_sitemap

_PLAIN = b'''<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://e.com/a</loc><lastmod>2026-01-01</lastmod></url>
  <url><loc>https://e.com/b</loc><lastmod>not-a-date</lastmod></url>
</urlset>'''


def _resp(content, status=200, url="https://e.com/sitemap.xml"):
    m = MagicMock()
    m.status_code = status
    m.content = content
    m.url = url
    return m


class TestAuditSitemap:
    def test_plain_sitemap_fetched_once(self):
        with patch("tools.sitemap_audit.fetch_html", return_value=_resp(_PLAIN)) as fh, \
             patch("tools.sitemap_audit.fetch_sitemap_urls") as fsu, \
             patch("tools.sitemap_audit.validate_public_url", return_value="https://e.com/sitemap.xml"):
            r = audit_sitemap("https://e.com/sitemap.xml")
        assert r["ok"] is True
        assert fh.call_count == 1
        assert fsu.call_count == 0
        assert r["total_urls"] == 2

    def test_invalid_lastmod_counted(self):
        with patch("tools.sitemap_audit.fetch_html", return_value=_resp(_PLAIN)), \
             patch("tools.sitemap_audit.fetch_sitemap_urls"), \
             patch("tools.sitemap_audit.validate_public_url", return_value="https://e.com/sitemap.xml"):
            r = audit_sitemap("https://e.com/sitemap.xml")
        assert r["summary"]["invalid_lastmod"] == 1
