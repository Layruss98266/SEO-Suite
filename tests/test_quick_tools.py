from unittest.mock import patch, MagicMock

from tools.quick_tools import _attr_text, _check_link


def _resp(status=200, url="https://e.com/", headers=None):
    m = MagicMock()
    m.status_code = status
    m.url = url
    m.headers = headers or {}
    return m


class FakeTag:
    def __init__(self, value):
        self.value = value

    def get(self, name, default=""):
        return self.value if name == "content" else default


class TestAttrText:
    def test_none_tag_returns_default(self):
        assert _attr_text(None, "content") == ""

    def test_none_attribute_returns_default(self):
        assert _attr_text(FakeTag(None), "content") == ""

    def test_list_attribute_is_joined(self):
        assert _attr_text(FakeTag(["one", "two"]), "content") == "one two"

    def test_string_attribute_is_stripped(self):
        assert _attr_text(FakeTag("  hello  "), "content") == "hello"


class TestCheckLink:
    def test_redirect_detected_via_final_url(self):
        final = _resp(status=200, url="https://e.com/new")
        with patch("tools.quick_tools.validate_public_url", return_value="https://e.com/old"), \
             patch("tools.quick_tools.safe_requests_head", return_value=final):
            r = _check_link("https://e.com/old", "e.com")
        assert r["redirect_to"] == "https://e.com/new"
        assert r["ok"] is True

    def test_405_falls_back_to_get(self):
        head = _resp(status=405, url="https://e.com/x")
        get  = _resp(status=200, url="https://e.com/x")
        with patch("tools.quick_tools.validate_public_url", return_value="https://e.com/x"), \
             patch("tools.quick_tools.safe_requests_head", return_value=head), \
             patch("tools.quick_tools.safe_requests_get", return_value=get):
            r = _check_link("https://e.com/x", "e.com")
        assert r["status"] == 200
        assert r["ok"] is True

    def test_non_http_scheme_skipped(self):
        r = _check_link("mailto:a@b.com", "e.com")
        assert r["type"] == "skip"


from tools.quick_tools import code_to_text_ratio


class TestCodeToTextRatio:
    def test_oversized_response_sanitised(self):
        from tools._common import ToolFetchError
        with patch("tools.quick_tools.fetch_html", side_effect=ToolFetchError("Response too large (>5 MB)")), \
             patch("tools.quick_tools.validate_public_url", return_value="https://e.com/"):
            r = code_to_text_ratio("https://e.com/")
        assert r["ok"] is False
        assert "too large" in r["error"].lower()

    def test_basic_ratio_computed(self):
        m = MagicMock()
        m.status_code = 200
        m.url = "https://e.com/"
        m.text = "<html><body>" + ("hello world " * 50) + "</body></html>"
        with patch("tools.quick_tools.fetch_html", return_value=m), \
             patch("tools.quick_tools.validate_public_url", return_value="https://e.com/"):
            r = code_to_text_ratio("https://e.com/")
        assert r["ok"] is True
        assert r["ratio_pct"] > 0
