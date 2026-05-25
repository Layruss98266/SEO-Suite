"""Tests for tools/indexnow.py — IndexNow submission tool."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from tools import indexnow


class TestGenerateKey:
    def test_returns_32_hex_chars(self):
        key = indexnow.generate_key()
        assert isinstance(key, str)
        assert len(key) == 32
        assert all(c in "0123456789abcdef" for c in key)

    def test_keys_are_unique(self):
        keys = {indexnow.generate_key() for _ in range(20)}
        assert len(keys) == 20  # all distinct


class TestSubmitUrl:
    def test_private_url_rejected(self):
        result = indexnow.submit_url("http://127.0.0.1/page", "k" * 32, "example.com")
        assert result["ok"] is False
        assert "error" in result

    def test_invalid_url_rejected(self):
        result = indexnow.submit_url("not-a-url", "k" * 32, "example.com")
        assert result["ok"] is False

    @patch("tools.indexnow.safe_requests_post")
    def test_successful_submission(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_post.return_value = mock_resp

        result = indexnow.submit_url(
            "https://example.com/page", "abcd" * 8, "example.com"
        )
        assert result["ok"] is True
        assert result["status"] == 200
        assert result["url"] == "https://example.com/page"

    @patch("tools.indexnow.safe_requests_post")
    def test_accepted_202_is_ok(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 202
        mock_post.return_value = mock_resp

        result = indexnow.submit_url(
            "https://example.com/page", "abcd" * 8, "example.com"
        )
        assert result["ok"] is True

    @patch("tools.indexnow.safe_requests_post")
    def test_non_ok_status_returns_error(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 422
        mock_post.return_value = mock_resp

        result = indexnow.submit_url(
            "https://example.com/page", "abcd" * 8, "example.com"
        )
        assert result["ok"] is False
        assert result["status"] == 422
        assert "422" in result["error"]

    @patch("tools.indexnow.safe_requests_post")
    def test_network_error_returns_error(self, mock_post):
        mock_post.side_effect = ConnectionError("boom")

        result = indexnow.submit_url(
            "https://example.com/page", "abcd" * 8, "example.com"
        )
        assert result["ok"] is False
        assert "Request failed" in result["error"]

    @patch("tools.indexnow.safe_requests_post")
    def test_passes_correct_params(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_post.return_value = mock_resp

        indexnow.submit_url(
            "https://example.com/page", "thekey1234567890" * 2, "example.com"
        )
        call_kwargs = mock_post.call_args.kwargs
        assert call_kwargs["params"]["url"] == "https://example.com/page"
        assert call_kwargs["params"]["key"] == "thekey1234567890" * 2
        assert (
            call_kwargs["params"]["keyLocation"]
            == f"https://example.com/{'thekey1234567890' * 2}.txt"
        )


class TestSubmitBulk:
    def test_empty_after_filtering_returns_error(self):
        result = indexnow.submit_bulk(
            ["http://127.0.0.1/", "not-a-url"], "k" * 32, "example.com"
        )
        assert result["ok"] is False
        assert len(result["skipped"]) == 2

    @patch("tools.indexnow.safe_requests_post")
    def test_partial_skip_succeeds_for_rest(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_post.return_value = mock_resp

        result = indexnow.submit_bulk(
            [
                "https://example.com/a",
                "http://127.0.0.1/private",  # rejected
                "https://example.com/b",
            ],
            "k" * 32,
            "example.com",
        )
        assert result["ok"] is True
        assert result["submitted"] == 2
        assert len(result["skipped"]) == 1

    @patch("tools.indexnow.safe_requests_post")
    def test_payload_shape(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_post.return_value = mock_resp

        indexnow.submit_bulk(
            ["https://example.com/a", "https://example.com/b"],
            "k" * 32,
            "example.com",
        )
        body = mock_post.call_args.kwargs["json"]
        assert body["host"] == "example.com"
        assert body["key"] == "k" * 32
        assert body["urlList"] == ["https://example.com/a", "https://example.com/b"]

    @patch("tools.indexnow.safe_requests_post")
    def test_network_error_returns_error(self, mock_post):
        mock_post.side_effect = TimeoutError("slow")
        result = indexnow.submit_bulk(
            ["https://example.com/a"], "k" * 32, "example.com"
        )
        assert result["ok"] is False
        assert result["submitted"] == 0
        assert "Request failed" in result["error"]
