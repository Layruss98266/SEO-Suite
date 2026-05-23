from tools.generators import generate_sitemap, generate_hreflang, generate_robots_txt, generate_schema


class TestGenerateSitemap:
    def test_escapes_xml_in_loc(self):
        r = generate_sitemap({"urls": [{"url": "https://e.com/?a=1&b=2"}]})
        assert r["ok"] is True
        assert "<loc>https://e.com/?a=1&amp;b=2</loc>" in r["content"]
        assert "&b=2" not in r["content"].replace("&amp;", "")  # raw & gone

    def test_injection_attempt_is_escaped(self):
        r = generate_sitemap({"urls": [{"url": "https://e.com/</loc><script>x</script>"}]})
        assert "<script>" not in r["content"]
        assert "&lt;script&gt;" in r["content"]

    def test_invalid_scheme_url_skipped_and_warned(self):
        r = generate_sitemap({"urls": [
            {"url": "https://good.com/"},
            {"url": "javascript:alert(1)"},
        ]})
        assert r["url_count"] == 1
        assert any("scheme" in w.lower() for w in r["warnings"])

    def test_priority_out_of_range_dropped_and_warned(self):
        r = generate_sitemap({"urls": [{"url": "https://e.com/", "priority": "5"}]})
        assert "<priority>" not in r["content"]
        assert any("priority" in w.lower() for w in r["warnings"])

    def test_bad_changefreq_dropped_and_warned(self):
        r = generate_sitemap({"urls": [{"url": "https://e.com/", "changefreq": "often"}]})
        assert "<changefreq>" not in r["content"]
        assert any("changefreq" in w.lower() for w in r["warnings"])

    def test_valid_optional_fields_emitted(self):
        r = generate_sitemap({"urls": [{"url": "https://e.com/", "priority": "0.8", "changefreq": "daily"}]})
        assert "<priority>0.8</priority>" in r["content"]
        assert "<changefreq>daily</changefreq>" in r["content"]
        assert r["warnings"] == []

    def test_no_urls_is_error(self):
        assert generate_sitemap({"urls": []})["ok"] is False


class TestGenerateHreflang:
    def test_valid_pair_emitted_and_escaped(self):
        r = generate_hreflang({"items": [{"locale": "en-US", "url": "https://e.com/?a=1&b=2"}]})
        assert r["ok"] is True
        assert 'hreflang="en-US"' in r["html_tags"]
        assert "&amp;b=2" in r["html_tags"]

    def test_invalid_locale_dropped_and_warned(self):
        r = generate_hreflang({"items": [
            {"locale": "english", "url": "https://e.com/"},
            {"locale": "fr", "url": "https://e.com/fr"},
        ]})
        assert r["count"] == 1
        assert any("english" in w for w in r["warnings"])

    def test_invalid_url_scheme_dropped(self):
        r = generate_hreflang({"items": [{"locale": "en", "url": "javascript:x"}]})
        assert r["ok"] is False or r["count"] == 0

    def test_xdefault_accepted(self):
        r = generate_hreflang({"items": [{"locale": "x-default", "url": "https://e.com/"}]})
        assert 'hreflang="x-default"' in r["html_tags"]


class TestGenerateRobotsTxt:
    def test_numeric_crawl_delay_emitted(self):
        r = generate_robots_txt({"rules": [{"user_agent": "*", "disallow": ["/admin"], "crawl_delay": "5"}]})
        assert "Crawl-delay: 5" in r["content"]
        assert r["warnings"] == []

    def test_non_numeric_crawl_delay_dropped_and_warned(self):
        r = generate_robots_txt({"rules": [{"user_agent": "*", "crawl_delay": "soon"}]})
        assert "Crawl-delay" not in r["content"]
        assert any("crawl" in w.lower() for w in r["warnings"])

    def test_newline_in_path_is_stripped(self):
        r = generate_robots_txt({"rules": [{"user_agent": "*", "disallow": ["/a\nUser-agent: evil"]}]})
        # Injected directive must not appear on its own line
        assert "User-agent: evil" not in r["content"].splitlines()


class TestGenerateSchemaWarnings:
    def test_missing_required_field_warned(self):
        # Article requires headline, description, author, publisher, date_published, url
        r = generate_schema("article", {"headline": "Hi"})
        assert r["ok"] is True
        assert "warnings" in r
        assert any("author" in w.lower() for w in r["warnings"])

    def test_all_required_present_no_warnings(self):
        r = generate_schema("article", {
            "headline": "Hi", "description": "d", "author": "A",
            "publisher": "P", "date_published": "2026-01-01", "url": "https://e.com/",
        })
        assert r["ok"] is True
        assert r["warnings"] == []

    def test_unknown_type_unchanged(self):
        assert generate_schema("nope", {})["ok"] is False
