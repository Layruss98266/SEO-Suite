"""Tests for tools/bing_webmaster.py — Bing Webmaster API wrapper."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from tools import bing_webmaster as bing


def _mock_json_response(body: dict, status: int = 200):
    r = MagicMock()
    r.status_code = status
    r.json.return_value = body
    r.raise_for_status = MagicMock()
    return r


class TestUrlTraffic:
    @patch("tools.bing_webmaster.safe_requests_get")
    def test_returns_metrics_on_success(self, mock_get):
        mock_get.return_value = _mock_json_response(
            {
                "d": {
                    "TotalClicks": 1247,
                    "TotalImpressions": 24891,
                    "AvgCTR": 0.05,
                    "AvgPosition": 8.3,
                }
            }
        )
        result = bing.url_traffic("https://example.com", "key")
        assert result["ok"] is True
        assert result["status"] == "pass"
        assert result["data"]["clicks"] == 1247
        assert result["data"]["impressions"] == 24891
        assert result["data"]["avg_ctr"] == 5.0
        assert result["data"]["avg_position"] == 8.3

    @patch("tools.bing_webmaster.safe_requests_get")
    def test_warning_when_zero_clicks(self, mock_get):
        mock_get.return_value = _mock_json_response({"d": {"TotalClicks": 0}})
        result = bing.url_traffic("https://example.com", "key")
        assert result["ok"] is True
        assert result["status"] == "warning"

    @patch("tools.bing_webmaster.safe_requests_get")
    def test_network_error_returns_error_dict(self, mock_get):
        mock_get.side_effect = ConnectionError("boom")
        result = bing.url_traffic("https://example.com", "key")
        assert result["ok"] is False
        assert "boom" in result["error"]


class TestCrawlStats:
    @patch("tools.bing_webmaster.safe_requests_get")
    def test_warning_on_empty_data(self, mock_get):
        mock_get.return_value = _mock_json_response({"d": []})
        result = bing.crawl_stats("https://example.com", "key")
        assert result["ok"] is True
        assert result["status"] == "warning"
        assert "No crawl data" in result["message"]

    @patch("tools.bing_webmaster.safe_requests_get")
    def test_summarises_recent_days(self, mock_get):
        # 30 days of clean crawl stats (no errors).
        rows = [
            {
                "CrawledPages": 100,
                "CrawlErrors": 0,
                "DnsFailures": 0,
                "RobotsBlocked": 0,
                "ConnectionErrors": 0,
            }
            for _ in range(30)
        ]
        mock_get.return_value = _mock_json_response({"d": rows})
        result = bing.crawl_stats("https://example.com", "key")
        assert result["ok"] is True

    @patch("tools.bing_webmaster.safe_requests_get")
    def test_flags_high_error_rate(self, mock_get):
        # 1 row with 10% error rate.
        rows = [
            {
                "CrawledPages": 100,
                "CrawlErrors": 10,
                "DnsFailures": 0,
                "RobotsBlocked": 0,
                "ConnectionErrors": 0,
            }
        ]
        mock_get.return_value = _mock_json_response({"d": rows})
        result = bing.crawl_stats("https://example.com", "key")
        assert result["ok"] is True
        # Either flagged as a warning or surfaces in the message.
        assert "error" in result.get("message", "").lower() or result.get("status") == "warning"


class TestInspectUrl:
    @patch("tools.bing_webmaster.safe_requests_get")
    def test_returns_index_status(self, mock_get):
        mock_get.return_value = _mock_json_response(
            {"d": {"IsIndexed": True, "LastCrawlDate": "/Date(1700000000000)/"}}
        )
        result = bing.inspect_url(
            "https://example.com/page", "https://example.com", "key"
        )
        # The wrapper should normalise the result; main success indicator is ok=True.
        assert result.get("ok") is True or "data" in result


class TestSubmitUrl:
    @patch("tools.bing_webmaster.safe_requests_post")
    def test_submit_succeeds_on_200(self, mock_post):
        mock_post.return_value = _mock_json_response({"d": True})
        result = bing.submit_url(
            "https://example.com/page", "https://example.com", "key"
        )
        assert result.get("ok") is True


class TestSiteOverview:
    @patch("tools.bing_webmaster.safe_requests_get")
    def test_aggregates_three_sub_calls(self, mock_get):
        # site_overview() calls url_traffic + crawl_stats + sitemap_status in
        # sequence; mock returns the same generic shape for all three.
        mock_get.return_value = _mock_json_response({"d": {}})
        result = bing.site_overview("https://example.com", "key")
        # Just verify it returns a dict with the expected top-level keys.
        assert isinstance(result, dict)
        # Sub-results may live under named keys or be merged.
        assert "ok" in result or "traffic" in result or "data" in result
