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
