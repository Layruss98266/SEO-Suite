import pytest

from tools._common import safe_error, xml_text, ToolFetchError, HEADERS, DEFAULT_TIMEOUT, MAX_RESPONSE_BYTES


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
