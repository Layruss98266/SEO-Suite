"""Tests for tools.duplicate_detector."""

from unittest.mock import MagicMock, patch

from tools.duplicate_detector import (
    MAX_URLS_HARD_CAP,
    _normalise,
    scan_duplicates,
)


def _make_html(title: str = "", description: str = "", h1: str = "") -> str:
    return (
        "<html><head>"
        f"<title>{title}</title>"
        f'<meta name="description" content="{description}">'
        f"</head><body><h1>{h1}</h1></body></html>"
    )


def _fake_response(html: str, url: str = "https://example.com/"):
    m = MagicMock()
    m.status_code = 200
    m.url = url
    m.text = html
    m.headers = {}
    return m


class TestNormalise:
    def test_strips_whitespace_and_lowercases(self):
        assert _normalise("  Hello World  ") == "hello world"

    def test_collapses_internal_whitespace(self):
        assert _normalise("foo\n\t  bar") == "foo bar"

    def test_empty_string(self):
        assert _normalise("") == ""

    def test_none_safe(self):
        assert _normalise(None) == ""  # type: ignore[arg-type]


class TestScanDuplicates:
    def test_three_urls_share_title_grouped(self):
        urls = ["https://a.com/", "https://b.com/", "https://c.com/"]

        def fake_fetch(url, headers=None):
            return _fake_response(
                _make_html(title="Same Title", description=f"desc {url}", h1=f"h1 {url}"),
                url=url,
            )

        with patch("tools.duplicate_detector.fetch_html", side_effect=fake_fetch), patch(
            "tools.duplicate_detector.is_safe_url", return_value=(True, "")
        ):
            result = scan_duplicates(urls)

        assert result["ok"] is True
        assert result["scanned"] == 3
        assert result["failed"] == 0
        title_groups = [g for g in result["groups"] if g["type"] == "title"]
        assert len(title_groups) == 1
        assert title_groups[0]["count"] == 3
        assert set(title_groups[0]["urls"]) == set(urls)
        assert result["summary"]["total_dup_titles"] == 1
        # descriptions/h1 unique → no groups
        assert result["summary"]["total_dup_descriptions"] == 0
        assert result["summary"]["total_dup_h1s"] == 0

    def test_all_unique_inputs_no_groups(self):
        urls = ["https://a.com/", "https://b.com/"]

        def fake_fetch(url, headers=None):
            return _fake_response(
                _make_html(title=f"T-{url}", description=f"D-{url}", h1=f"H-{url}"),
                url=url,
            )

        with patch("tools.duplicate_detector.fetch_html", side_effect=fake_fetch), patch(
            "tools.duplicate_detector.is_safe_url", return_value=(True, "")
        ):
            result = scan_duplicates(urls)

        assert result["ok"] is True
        assert result["groups"] == []
        assert result["summary"] == {
            "total_dup_titles": 0,
            "total_dup_descriptions": 0,
            "total_dup_h1s": 0,
        }

    def test_max_urls_cap_respected(self):
        # 150 URLs, cap is 100
        urls = [f"https://example{i}.com/" for i in range(150)]
        seen: list[str] = []

        def fake_fetch(url, headers=None):
            seen.append(url)
            return _fake_response(_make_html(title="x"), url=url)

        with patch("tools.duplicate_detector.fetch_html", side_effect=fake_fetch), patch(
            "tools.duplicate_detector.is_safe_url", return_value=(True, "")
        ):
            result = scan_duplicates(urls, max_urls=100)

        assert result["scanned"] == MAX_URLS_HARD_CAP
        assert len(seen) == MAX_URLS_HARD_CAP

    def test_hard_cap_overrides_max_urls(self):
        urls = [f"https://example{i}.com/" for i in range(200)]

        def fake_fetch(url, headers=None):
            return _fake_response(_make_html(title="x"), url=url)

        with patch("tools.duplicate_detector.fetch_html", side_effect=fake_fetch), patch(
            "tools.duplicate_detector.is_safe_url", return_value=(True, "")
        ):
            result = scan_duplicates(urls, max_urls=500)

        assert result["scanned"] == MAX_URLS_HARD_CAP

    def test_whitespace_and_case_normalisation_groups_matches(self):
        urls = ["https://a.com/", "https://b.com/"]
        htmls = {
            "https://a.com/": _make_html(title="  Hello   World  "),
            "https://b.com/": _make_html(title="hello world"),
        }

        def fake_fetch(url, headers=None):
            return _fake_response(htmls[url], url=url)

        with patch("tools.duplicate_detector.fetch_html", side_effect=fake_fetch), patch(
            "tools.duplicate_detector.is_safe_url", return_value=(True, "")
        ):
            result = scan_duplicates(urls)

        title_groups = [g for g in result["groups"] if g["type"] == "title"]
        assert len(title_groups) == 1
        assert title_groups[0]["count"] == 2

    def test_unsafe_url_counted_as_failed(self):
        urls = ["https://safe.com/", "http://169.254.169.254/"]

        def fake_safe(url):
            return (url.startswith("https://safe"), "blocked")

        def fake_fetch(url, headers=None):
            return _fake_response(_make_html(title="x"), url=url)

        with patch("tools.duplicate_detector.fetch_html", side_effect=fake_fetch), patch(
            "tools.duplicate_detector.is_safe_url", side_effect=fake_safe
        ):
            result = scan_duplicates(urls)

        assert result["scanned"] == 1
        assert result["failed"] == 1

    def test_empty_input_returns_empty_groups(self):
        result = scan_duplicates([])
        assert result["ok"] is True
        assert result["scanned"] == 0
        assert result["groups"] == []

    def test_groups_sorted_by_count_descending(self):
        urls = [f"https://e{i}.com/" for i in range(5)]
        # 4 share title "A", 2 share title "B" (one URL has unique title)
        titles = {
            "https://e0.com/": "A",
            "https://e1.com/": "A",
            "https://e2.com/": "A",
            "https://e3.com/": "A",
            "https://e4.com/": "B",
        }
        # Add a 6th URL sharing title B
        urls.append("https://e5.com/")
        titles["https://e5.com/"] = "B"

        def fake_fetch(url, headers=None):
            return _fake_response(_make_html(title=titles[url]), url=url)

        with patch("tools.duplicate_detector.fetch_html", side_effect=fake_fetch), patch(
            "tools.duplicate_detector.is_safe_url", return_value=(True, "")
        ):
            result = scan_duplicates(urls)

        title_groups = [g for g in result["groups"] if g["type"] == "title"]
        assert [g["count"] for g in title_groups] == [4, 2]
