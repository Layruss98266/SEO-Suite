"""Tests for tools/blog_audit.py — no network."""

from unittest.mock import MagicMock, patch

from tools.blog_audit import (
    _word_count,
    audit_blog_post,
    check_article_schema,
    check_author,
    check_category,
    check_h2_structure,
    check_internal_links,
    check_og_image,
    check_published_date,
    check_reading_time,
    check_updated_date,
)
from bs4 import BeautifulSoup

URL = "https://example.com/blog/post"


def _soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "html.parser")


def _article_nodes(soup):
    from tools.blog_audit import _find_article_nodes
    return _find_article_nodes(soup)


# ─── Individual checks ────────────────────────────────────────────────────────
class TestAuthor:
    def test_rel_author(self):
        s = _soup('<a rel="author" href="/u/jane">Jane Doe</a>')
        r = check_author(URL, s, [])
        assert r["status"] == "pass"
        assert "Jane Doe" in r["value"]

    def test_address_class_author(self):
        s = _soup('<address class="author">Jane</address>')
        assert check_author(URL, s, [])["status"] == "pass"

    def test_jsonld_author(self):
        s = _soup("")
        nodes = [{"@type": "Article", "author": {"name": "Jane"}}]
        r = check_author(URL, s, nodes)
        assert r["status"] == "pass"
        assert r["value"] == "Jane"

    def test_missing(self):
        assert check_author(URL, _soup("<p>nothing</p>"), [])["status"] == "fail"


class TestPublishedDate:
    def test_time_datetime(self):
        s = _soup('<time datetime="2026-01-15">Jan 15</time>')
        assert check_published_date(URL, s, [])["status"] == "pass"

    def test_meta_property(self):
        s = _soup('<meta property="article:published_time" content="2026-01-15T10:00:00Z">')
        assert check_published_date(URL, s, [])["status"] == "pass"

    def test_jsonld(self):
        nodes = [{"@type": "Article", "datePublished": "2026-01-15"}]
        assert check_published_date(URL, _soup(""), nodes)["status"] == "pass"

    def test_unparseable_warns(self):
        s = _soup('<meta property="article:published_time" content="last tuesday">')
        assert check_published_date(URL, s, [])["status"] == "warning"

    def test_missing(self):
        assert check_published_date(URL, _soup(""), [])["status"] == "fail"


class TestUpdatedDate:
    def test_modified_time(self):
        s = _soup('<meta property="article:modified_time" content="2026-02-01">')
        assert check_updated_date(URL, s, [])["status"] == "pass"

    def test_jsonld_modified(self):
        nodes = [{"@type": "BlogPosting", "dateModified": "2026-02-01"}]
        assert check_updated_date(URL, _soup(""), nodes)["status"] == "pass"

    def test_missing_is_warning(self):
        assert check_updated_date(URL, _soup(""), [])["status"] == "warning"


class TestCategory:
    def test_article_section(self):
        s = _soup('<meta property="article:section" content="Tech">')
        assert check_category(URL, s)["status"] == "pass"

    def test_breadcrumb(self):
        s = _soup('<nav class="breadcrumb"><a href="/">Home</a><a href="/tech">Tech</a></nav>')
        r = check_category(URL, s)
        assert r["status"] == "pass"
        assert r["value"] == "Tech"

    def test_rel_tag(self):
        s = _soup('<a rel="tag" href="/t/seo">SEO</a>')
        assert check_category(URL, s)["status"] == "pass"

    def test_missing(self):
        assert check_category(URL, _soup(""))["status"] == "warning"


class TestArticleSchema:
    def test_full_article(self):
        nodes = [{
            "@type": "Article",
            "headline": "X",
            "author": {"name": "J"},
            "datePublished": "2026-01-01",
            "image": "https://e.com/i.jpg",
        }]
        assert check_article_schema(URL, nodes)["status"] == "pass"

    def test_blogposting_missing_fields(self):
        nodes = [{"@type": "BlogPosting", "headline": "X"}]
        r = check_article_schema(URL, nodes)
        assert r["status"] == "warning"
        assert "author" in r["details"]["missing"]

    def test_no_article(self):
        assert check_article_schema(URL, [])["status"] == "fail"


class TestOgImage:
    def test_pass_with_dimensions(self):
        s = _soup(
            '<meta property="og:image" content="https://e.com/i.jpg">'
            '<meta property="og:image:width" content="1200">'
            '<meta property="og:image:height" content="630">'
        )
        assert check_og_image(URL, s)["status"] == "pass"

    def test_small_image_warns(self):
        s = _soup(
            '<meta property="og:image" content="https://e.com/i.jpg">'
            '<meta property="og:image:width" content="600">'
            '<meta property="og:image:height" content="400">'
        )
        assert check_og_image(URL, s)["status"] == "warning"

    def test_no_dimensions_warns(self):
        s = _soup('<meta property="og:image" content="https://e.com/i.jpg">')
        assert check_og_image(URL, s)["status"] == "warning"

    def test_missing_fails(self):
        assert check_og_image(URL, _soup(""))["status"] == "fail"

    def test_invalid_url_fails(self):
        s = _soup('<meta property="og:image" content="not a url">')
        assert check_og_image(URL, s)["status"] == "fail"


class TestReadingTime:
    def test_word_count_simple(self):
        assert _word_count("one two three") == 3
        assert _word_count("don't can't won't") == 3

    def test_minutes_calculation(self):
        body = _soup("<article>" + " ".join(["word"] * 660) + "</article>")
        r = check_reading_time(URL, body)
        # 660 / 220 wpm = 3 min
        assert r["value"] == 3
        assert r["status"] == "pass"

    def test_thin_content_fails(self):
        body = _soup("<article>" + " ".join(["word"] * 100) + "</article>")
        assert check_reading_time(URL, body)["status"] == "fail"

    def test_light_content_warns(self):
        body = _soup("<article>" + " ".join(["word"] * 400) + "</article>")
        assert check_reading_time(URL, body)["status"] == "warning"

    def test_substantial_passes(self):
        body = _soup("<article>" + " ".join(["word"] * 800) + "</article>")
        assert check_reading_time(URL, body)["status"] == "pass"


class TestInternalLinks:
    def test_pass(self):
        body = _soup(
            '<article>'
            '<a href="/a">A</a><a href="/b">B</a><a href="/c">C</a>'
            '<a href="https://other.com/x">ext</a>'
            '</article>'
        )
        r = check_internal_links(URL, body, URL)
        assert r["value"] == 3
        assert r["status"] == "pass"

    def test_under_two_warns(self):
        body = _soup('<article><a href="/a">A</a></article>')
        assert check_internal_links(URL, body, URL)["status"] == "warning"

    def test_two_links_warns(self):
        body = _soup('<article><a href="/a">A</a><a href="/b">B</a></article>')
        assert check_internal_links(URL, body, URL)["status"] == "warning"

    def test_skips_anchors_and_mailto(self):
        body = _soup(
            '<article><a href="#top">t</a><a href="mailto:x@y.com">m</a></article>'
        )
        assert check_internal_links(URL, body, URL)["value"] == 0


class TestH2Structure:
    def test_zero_fails(self):
        assert check_h2_structure(URL, _soup("<article><h1>T</h1></article>"))["status"] == "fail"

    def test_one_warns(self):
        body = _soup("<article><h2>A</h2></article>")
        assert check_h2_structure(URL, body)["status"] == "warning"

    def test_two_passes(self):
        body = _soup("<article><h2>A</h2><h2>B</h2></article>")
        assert check_h2_structure(URL, body)["status"] == "pass"


# ─── End-to-end audit ────────────────────────────────────────────────────────
_FULL_HTML = """
<html><head>
<title>Test Post</title>
<meta property="article:published_time" content="2026-01-15T10:00:00Z">
<meta property="article:modified_time" content="2026-02-01T10:00:00Z">
<meta property="article:section" content="Engineering">
<meta property="og:image" content="https://e.com/cover.jpg">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<script type="application/ld+json">
{
  "@type": "BlogPosting",
  "headline": "Hello",
  "author": {"name": "Jane Doe"},
  "datePublished": "2026-01-15",
  "dateModified": "2026-02-01",
  "image": "https://e.com/cover.jpg"
}
</script>
</head><body>
<article>
  <a rel="author" href="/u/jane">Jane Doe</a>
  <h1>Hello</h1>
  <h2>Section 1</h2>
  <p>__BODY__</p>
  <h2>Section 2</h2>
  <h2>Section 3</h2>
  <a href="/a">A</a><a href="/b">B</a><a href="/c">C</a><a href="/d">D</a>
</article>
</body></html>
""".replace("__BODY__", " ".join(["word"] * 800))


_BARE_HTML = "<html><body><p>nothing here</p></body></html>"


def _mock_resp(html: str, url: str = URL):
    m = MagicMock()
    m.text = html
    m.url = url
    m.status_code = 200
    return m


class TestEndToEnd:
    def test_full_post_scores_high(self):
        with patch("tools.blog_audit.fetch_html", return_value=_mock_resp(_FULL_HTML)), \
             patch("tools.blog_audit.validate_public_url", return_value=URL):
            out = audit_blog_post(URL)
        assert out["ok"] is True
        assert out["score"] >= 90, f"expected ≥90, got {out['score']}: {out['counts']}"
        assert out["counts"]["fail"] == 0

    def test_bare_page_fails_most(self):
        with patch("tools.blog_audit.fetch_html", return_value=_mock_resp(_BARE_HTML)), \
             patch("tools.blog_audit.validate_public_url", return_value=URL):
            out = audit_blog_post(URL)
        assert out["ok"] is True
        # Author, published_date, article_schema, og_image, reading_time -> fail (5)
        assert out["counts"]["fail"] >= 5
        assert out["score"] < 25

    def test_fetch_error_returns_error_shape(self):
        from tools._common import ToolFetchError
        with patch("tools.blog_audit.fetch_html", side_effect=ToolFetchError("boom")), \
             patch("tools.blog_audit.validate_public_url", return_value=URL):
            out = audit_blog_post(URL)
        assert out["ok"] is False
        assert "error" in out
        assert out["url"] == URL

    def test_invalid_url_returns_error_shape(self):
        with patch("tools.blog_audit.validate_public_url", side_effect=ValueError("bad")):
            out = audit_blog_post("http://internal/x")
        assert out["ok"] is False
        assert out["error"] == "bad"
