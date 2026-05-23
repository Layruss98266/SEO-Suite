from unittest.mock import patch, MagicMock

from tools.schema_validator import validate_url


def _resp(text, status=200):
    m = MagicMock()
    m.status_code = status
    m.text = text
    m.url = "https://e.com/"
    return m


class TestValidateUrl:
    def test_rejects_private_url(self):
        r = validate_url("http://127.0.0.1/")
        assert r["ok"] is False

    def test_parses_jsonld_block(self):
        html = '<script type="application/ld+json">{"@context":"https://schema.org","@type":"Article","headline":"x","author":"a","datePublished":"2026-01-01"}</script>'
        with patch("tools.schema_validator.validate_public_url", return_value="https://e.com/"), \
             patch("tools.schema_validator.fetch_html", return_value=_resp(html)):
            r = validate_url("https://e.com/")
        assert r["ok"] is True
        assert "Article" in r["types_found"]

    def test_fetch_error_is_sanitised(self):
        from tools._common import ToolFetchError
        with patch("tools.schema_validator.validate_public_url", return_value="https://e.com/"), \
             patch("tools.schema_validator.fetch_html", side_effect=ToolFetchError("Response too large (>5 MB)")):
            r = validate_url("https://e.com/")
        assert r["ok"] is False
        assert "too large" in r["error"].lower()
