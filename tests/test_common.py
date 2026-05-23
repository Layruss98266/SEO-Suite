import pytest
from unittest.mock import patch, MagicMock

import requests

from tools._common import safe_error, xml_text, ToolFetchError, HEADERS, DEFAULT_TIMEOUT, MAX_RESPONSE_BYTES
from tools._common import fetch_html


class TestSafeError:
    def test_tool_fetch_error_message_preserved(self):
        assert safe_error(ToolFetchError("Response too large (6 MB)")) == "Response too large (6 MB)"

    def test_value_error_message_preserved(self):
        assert safe_error(ValueError("priority must be between 0.0 and 1.0")) == "priority must be between 0.0 and 1.0"

    def test_unknown_exception_is_generic(self):
        msg = safe_error(KeyError("internal_dict_key"))
        assert "internal_dict_key" not in msg
        assert msg == "Request failed. Please try again."

    def test_timeout_is_friendly(self):
        import requests
        assert safe_error(requests.Timeout("HTTPSConnectionPool host timed out")) == "The request timed out. Try again."


class TestXmlText:
    def test_escapes_all_xml_specials(self):
        assert xml_text('a&b<c>d"e\'f') == "a&amp;b&lt;c&gt;d&quot;e&#x27;f"

    def test_non_string_coerced(self):
        assert xml_text(0.8) == "0.8"

    def test_none_is_empty(self):
        assert xml_text(None) == ""


class TestConstants:
    def test_constants_present(self):
        assert "User-Agent" in HEADERS
        assert DEFAULT_TIMEOUT == 15
        assert MAX_RESPONSE_BYTES == 5_000_000


def _fake_response(*, status=200, headers=None, chunks=(b"<html></html>",)):
    resp = MagicMock()
    resp.status_code = status
    resp.headers = headers or {}
    resp.iter_content = MagicMock(return_value=iter(chunks))
    resp.close = MagicMock()
    return resp


class TestFetchHtml:
    def test_returns_response_under_cap(self):
        fake = _fake_response(chunks=(b"abc", b"def"))
        with patch("tools._common.safe_requests_get", return_value=fake):
            resp = fetch_html("https://example.com")
        assert resp is fake

    def test_aborts_when_content_length_exceeds_cap(self):
        fake = _fake_response(headers={"Content-Length": str(10_000_000)})
        with patch("tools._common.safe_requests_get", return_value=fake):
            with pytest.raises(ToolFetchError) as ei:
                fetch_html("https://example.com", max_bytes=5_000_000)
        assert "too large" in str(ei.value).lower()

    def test_aborts_when_streamed_bytes_exceed_cap(self):
        big = b"x" * 3_000_000
        fake = _fake_response(chunks=(big, big))  # 6 MB across chunks, no Content-Length
        with patch("tools._common.safe_requests_get", return_value=fake):
            with pytest.raises(ToolFetchError) as ei:
                fetch_html("https://example.com", max_bytes=5_000_000)
        assert "too large" in str(ei.value).lower()

    def test_retries_on_connection_error_then_succeeds(self):
        good = _fake_response()
        seq = [requests.ConnectionError("boom"), good]
        with patch("tools._common.safe_requests_get", side_effect=seq), \
             patch("tools._common.time.sleep"):
            resp = fetch_html("https://example.com", retries=2)
        assert resp is good

    def test_raises_tool_fetch_error_after_exhausting_retries(self):
        with patch("tools._common.safe_requests_get", side_effect=requests.ConnectionError("boom")), \
             patch("tools._common.time.sleep"):
            with pytest.raises(ToolFetchError):
                fetch_html("https://example.com", retries=2)
