"""
Blog-Post Audit Tool.

Runs a set of content-specific SEO checks tailored to article / blog pages —
the kind of checks a generic on-page audit doesn't bother with. Output mirrors
the standard SEO Suite audit shape used by `core.seo_audit` so it plugs into
the existing drawer / report UI without any glue code.

Inspired by DVR79's seo-technical-audit-dashboard. Generic, no vendor lock-in.

Checks
------
1.  blog_author             — rel=author link OR <address class=author> OR JSON-LD author
2.  blog_published_date     — <time datetime>, article:published_time, or JSON-LD datePublished
3.  blog_updated_date       — article:modified_time or JSON-LD dateModified (warning if absent)
4.  blog_category           — article:section, breadcrumb category, or rel=tag link
5.  blog_article_schema     — JSON-LD Article/BlogPosting/NewsArticle with required fields
6.  blog_og_image           — og:image present, valid URL, ≥1200x630 recommended
7.  blog_reading_time       — body word count at 220 wpm
8.  blog_internal_links     — internal links inside the main content
9.  blog_h2_structure       — at least 2 H2 headings in the body
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from core.security import validate_public_url
from tools._common import ToolFetchError, fetch_html, safe_error

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}

# Words per minute used to derive reading time.
WPM = 220

# Word-count thresholds for blog_reading_time.
_WC_PASS = 600
_WC_WARN = 300
_WC_FAIL = 150

# Recommended OG image dimensions.
_OG_W = 1200
_OG_H = 630

# Article schema types we accept.
_ARTICLE_TYPES = {"article", "blogposting", "newsarticle"}

# Required JSON-LD fields for a well-formed article.
_ARTICLE_REQUIRED = ("headline", "author", "datePublished", "image")


# ─── Result helper (mirrors tools/phase1.py:result so the shape is identical) ──
def _result(
    url: str,
    tool: str,
    status: str,
    value: Any,
    message: str,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "url": url,
        "tool": tool,
        "status": status,
        "value": value,
        "message": message,
        "details": details or {},
    }


# ─── JSON-LD helpers ───────────────────────────────────────────────────────────
def _iter_jsonld(soup: BeautifulSoup):
    """Yield each parsed JSON-LD object (flattens @graph arrays)."""
    for script in soup.find_all("script", type="application/ld+json"):
        raw = (script.string or script.get_text() or "").strip()
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            continue
        nodes = data if isinstance(data, list) else [data]
        for node in nodes:
            if not isinstance(node, dict):
                continue
            graph = node.get("@graph")
            if isinstance(graph, list):
                for g in graph:
                    if isinstance(g, dict):
                        yield g
            else:
                yield node


def _types(node: dict) -> set[str]:
    """Return @type values as a lowercased set (handles list or string)."""
    t = node.get("@type")
    if isinstance(t, str):
        return {t.lower()}
    if isinstance(t, list):
        return {str(x).lower() for x in t}
    return set()


def _find_article_nodes(soup: BeautifulSoup) -> list[dict]:
    return [n for n in _iter_jsonld(soup) if _types(n) & _ARTICLE_TYPES]


# ─── Body / main-content selection ─────────────────────────────────────────────
def _main_content(soup: BeautifulSoup):
    """Return the soup node that most likely holds the article body."""
    for sel in ("article", "main"):
        node = soup.find(sel)
        if node:
            return node
    for cls in ("post-content", "entry-content", "article-content", "blog-post", "content"):
        node = soup.find(attrs={"class": re.compile(rf"\b{cls}\b", re.I)})
        if node:
            return node
    return soup.body or soup


def _visible_text(node) -> str:
    # Strip noise so the word count reflects real prose.
    clone = BeautifulSoup(str(node), "html.parser")
    for tag in clone(["script", "style", "noscript", "nav", "footer", "header", "aside", "form"]):
        tag.decompose()
    return " ".join(clone.get_text(separator=" ").split())


def _word_count(text: str) -> int:
    return len(re.findall(r"\b[\w'-]+\b", text))


# ─── Date parsing ──────────────────────────────────────────────────────────────
def _parse_iso(value: str) -> bool:
    if not value:
        return False
    v = value.strip()
    try:
        from datetime import datetime
        datetime.fromisoformat(v.replace("Z", "+00:00"))
        return True
    except (ValueError, TypeError, OverflowError):
        pass
    # Accept bare YYYY-MM-DD too.
    return bool(re.match(r"^\d{4}-\d{2}-\d{2}$", v))


# ══════════════════════════════════════════════════════════════════════════════
# Individual checks
# ══════════════════════════════════════════════════════════════════════════════
def check_author(url: str, soup: BeautifulSoup, article_nodes: list[dict]) -> dict:
    sources: list[str] = []
    author_name = ""

    rel_author = soup.find("a", rel=lambda v: v and "author" in (v if isinstance(v, list) else [v]))
    if rel_author and rel_author.get_text(strip=True):
        sources.append("rel=author")
        author_name = rel_author.get_text(strip=True)

    addr = soup.find("address", attrs={"class": re.compile(r"\bauthor\b", re.I)})
    if addr and addr.get_text(strip=True):
        sources.append("<address class=author>")
        author_name = author_name or addr.get_text(strip=True)

    for node in article_nodes:
        a = node.get("author")
        if isinstance(a, dict):
            name = a.get("name") or ""
        elif isinstance(a, list) and a:
            first = a[0]
            name = first.get("name") if isinstance(first, dict) else str(first)
        elif isinstance(a, str):
            name = a
        else:
            name = ""
        if name:
            sources.append("JSON-LD author")
            author_name = author_name or name
            break

    if sources:
        return _result(url, "blog_author", "pass", author_name,
                       f"Author byline found ({sources[0]})",
                       {"sources": sources, "author": author_name})
    return _result(url, "blog_author", "fail", None,
                   "No author byline (rel=author, <address class=author>, or JSON-LD)")


def check_published_date(url: str, soup: BeautifulSoup, article_nodes: list[dict]) -> dict:
    candidates: list[tuple[str, str]] = []

    for t in soup.find_all("time", attrs={"datetime": True}):
        candidates.append(("<time datetime>", t.get("datetime", "").strip()))

    meta = soup.find("meta", attrs={"property": "article:published_time"})
    if meta and meta.get("content"):
        candidates.append(("og article:published_time", meta.get("content", "").strip()))

    for node in article_nodes:
        v = node.get("datePublished")
        if isinstance(v, str) and v:
            candidates.append(("JSON-LD datePublished", v.strip()))
            break

    for source, raw in candidates:
        if _parse_iso(raw):
            return _result(url, "blog_published_date", "pass", raw,
                           f"Published date found ({source})", {"source": source})

    if candidates:
        return _result(url, "blog_published_date", "warning",
                       candidates[0][1],
                       "Published date present but not a parseable ISO-8601 value",
                       {"raw": candidates[0][1]})
    return _result(url, "blog_published_date", "fail", None,
                   "No published date (<time>, article:published_time, or JSON-LD)")


def check_updated_date(url: str, soup: BeautifulSoup, article_nodes: list[dict]) -> dict:
    meta = soup.find("meta", attrs={"property": "article:modified_time"})
    if meta and meta.get("content"):
        raw = meta.get("content", "").strip()
        if _parse_iso(raw):
            return _result(url, "blog_updated_date", "pass", raw,
                           "Updated date found (article:modified_time)",
                           {"source": "og article:modified_time"})
    for node in article_nodes:
        v = node.get("dateModified")
        if isinstance(v, str) and _parse_iso(v):
            return _result(url, "blog_updated_date", "pass", v,
                           "Updated date found (JSON-LD dateModified)",
                           {"source": "JSON-LD dateModified"})
    return _result(url, "blog_updated_date", "warning", None,
                   "No updated date — search engines reward fresh content signals")


def check_category(url: str, soup: BeautifulSoup) -> dict:
    meta = soup.find("meta", attrs={"property": "article:section"})
    if meta and meta.get("content", "").strip():
        return _result(url, "blog_category", "pass", meta.get("content").strip(),
                       "Category found (article:section)",
                       {"source": "og article:section"})

    crumb = soup.find(attrs={"class": re.compile(r"\b(breadcrumb|breadcrumbs)\b", re.I)})
    if crumb:
        links = [a.get_text(strip=True) for a in crumb.find_all("a") if a.get_text(strip=True)]
        if links:
            return _result(url, "blog_category", "pass", links[-1],
                           "Category found (breadcrumb)",
                           {"source": "breadcrumb", "trail": links})

    tag_link = soup.find("a", rel=lambda v: v and "tag" in (v if isinstance(v, list) else [v]))
    if tag_link and tag_link.get_text(strip=True):
        return _result(url, "blog_category", "pass", tag_link.get_text(strip=True),
                       "Category found (rel=tag link)", {"source": "rel=tag"})

    return _result(url, "blog_category", "warning", None,
                   "No category, breadcrumb, or tag — categorisation helps topical relevance")


def check_article_schema(url: str, article_nodes: list[dict]) -> dict:
    if not article_nodes:
        return _result(url, "blog_article_schema", "fail", None,
                       "No JSON-LD Article / BlogPosting / NewsArticle schema found")

    node = article_nodes[0]
    missing = [f for f in _ARTICLE_REQUIRED if not node.get(f)]
    types = sorted({t for n in article_nodes for t in _types(n)} & _ARTICLE_TYPES)

    if missing:
        return _result(url, "blog_article_schema", "warning", types,
                       f"Article schema present ({', '.join(types)}) but missing: {', '.join(missing)}",
                       {"types": types, "missing": missing})
    return _result(url, "blog_article_schema", "pass", types,
                   f"Valid article schema: {', '.join(types)}",
                   {"types": types})


def check_og_image(url: str, soup: BeautifulSoup) -> dict:
    img = soup.find("meta", attrs={"property": "og:image"})
    src = img.get("content", "").strip() if img else ""
    if not src:
        return _result(url, "blog_og_image", "fail", None,
                       "Missing og:image — social shares will have no preview image")

    parsed = urlparse(src)
    valid = parsed.scheme in ("http", "https") and bool(parsed.netloc)
    if not valid:
        return _result(url, "blog_og_image", "fail", src,
                       "og:image URL is invalid (not absolute or wrong scheme)",
                       {"src": src})

    w_meta = soup.find("meta", attrs={"property": "og:image:width"})
    h_meta = soup.find("meta", attrs={"property": "og:image:height"})
    try:
        w = int(w_meta.get("content", "0")) if w_meta else 0
        h = int(h_meta.get("content", "0")) if h_meta else 0
    except (ValueError, TypeError):
        w, h = 0, 0

    details = {"src": src, "width": w, "height": h}

    if w and h and (w < _OG_W or h < _OG_H):
        return _result(url, "blog_og_image", "warning", src,
                       f"og:image is {w}×{h} — recommended ≥{_OG_W}×{_OG_H} for social cards",
                       details)
    if not w or not h:
        return _result(url, "blog_og_image", "warning", src,
                       "og:image present but dimensions not declared (add og:image:width/height)",
                       details)
    return _result(url, "blog_og_image", "pass", src,
                   f"og:image present ({w}×{h})", details)


def check_reading_time(url: str, body) -> dict:
    text = _visible_text(body)
    words = _word_count(text)
    minutes = max(1, round(words / WPM)) if words else 0

    details = {"words": words, "minutes": minutes, "wpm": WPM}

    if words < _WC_FAIL:
        return _result(url, "blog_reading_time", "fail", minutes,
                       f"Very thin content ({words} words, ~{minutes} min) — aim for {_WC_PASS}+",
                       details)
    if words < _WC_WARN:
        return _result(url, "blog_reading_time", "fail", minutes,
                       f"Thin content ({words} words, ~{minutes} min) — aim for {_WC_PASS}+",
                       details)
    if words < _WC_PASS:
        return _result(url, "blog_reading_time", "warning", minutes,
                       f"Light content ({words} words, ~{minutes} min) — {_WC_PASS}+ is more competitive",
                       details)
    return _result(url, "blog_reading_time", "pass", minutes,
                   f"Substantial content ({words:,} words, ~{minutes} min read)",
                   details)


def check_internal_links(url: str, body, page_url: str) -> dict:
    host = urlparse(page_url).netloc
    internal = 0
    examples: list[str] = []
    for a in body.find_all("a", href=True):
        href = a["href"].strip()
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        absolute = urljoin(page_url, href)
        if urlparse(absolute).netloc == host and absolute != page_url:
            internal += 1
            if len(examples) < 5:
                examples.append(absolute)

    details = {"internal_count": internal, "examples": examples}
    if internal < 2:
        return _result(url, "blog_internal_links", "warning", internal,
                       f"Only {internal} internal link(s) in body — add 2-3+ to spread link equity",
                       details)
    if internal < 3:
        return _result(url, "blog_internal_links", "warning", internal,
                       f"{internal} internal links — 3+ is the sweet spot",
                       details)
    return _result(url, "blog_internal_links", "pass", internal,
                   f"{internal} internal links in body content", details)


def check_h2_structure(url: str, body) -> dict:
    h2s = [h.get_text(strip=True) for h in body.find_all("h2") if h.get_text(strip=True)]
    n = len(h2s)
    details = {"count": n, "headings": h2s[:10]}
    if n == 0:
        return _result(url, "blog_h2_structure", "fail", n,
                       "No H2 headings — add subheadings to structure the article", details)
    if n == 1:
        return _result(url, "blog_h2_structure", "warning", n,
                       "Only 1 H2 heading — articles read better with 2+ subheadings", details)
    return _result(url, "blog_h2_structure", "pass", n,
                   f"{n} H2 subheadings structure the article", details)


# ══════════════════════════════════════════════════════════════════════════════
# Scoring (mirrors core.seo_audit conventions: pass=full, warn=half, fail/error=0)
# ══════════════════════════════════════════════════════════════════════════════
_WEIGHTS = {
    "blog_author":           10,
    "blog_published_date":   10,
    "blog_updated_date":      5,
    "blog_category":          6,
    "blog_article_schema":   15,
    "blog_og_image":          8,
    "blog_reading_time":     14,
    "blog_internal_links":   10,
    "blog_h2_structure":      8,
}


def _score(results: list[dict]) -> int:
    total = 0
    earned = 0.0
    for r in results:
        if r["status"] == "error":
            continue
        w = _WEIGHTS.get(r["tool"], 5)
        total += w
        if r["status"] == "pass":
            earned += w
        elif r["status"] == "warning":
            earned += w * 0.5
    return round(earned / total * 100) if total else 0


# ══════════════════════════════════════════════════════════════════════════════
# Public entry point
# ══════════════════════════════════════════════════════════════════════════════
def audit_blog_post(url: str) -> dict:
    """Run every blog-post check against a single URL.

    Returns the standard SEO Suite audit shape:
        {ok, url, score, results[], counts{pass,warning,fail,error}}
    or {ok: False, error, url} on fetch failure.
    """
    try:
        url = validate_public_url(url)
    except ValueError as exc:
        return {"ok": False, "error": str(exc), "url": url}

    try:
        resp = fetch_html(url, headers=HEADERS)
    except (ToolFetchError, requests.RequestException, OSError) as exc:
        logger.warning("audit_blog_post fetch failed for %s: %s", url, exc)
        return {"ok": False, "error": safe_error(exc), "url": url}

    final_url = resp.url or url
    # html.parser is the safe default — no XML entity resolution surface, no
    # network fetches. (lxml's XMLParser hardening lives on the XML side of
    # the codebase; BeautifulSoup over html.parser does not expose XXE.)
    soup = BeautifulSoup(resp.text, "html.parser")
    article_nodes = _find_article_nodes(soup)
    body = _main_content(soup)

    results: list[dict] = [
        check_author(final_url, soup, article_nodes),
        check_published_date(final_url, soup, article_nodes),
        check_updated_date(final_url, soup, article_nodes),
        check_category(final_url, soup),
        check_article_schema(final_url, article_nodes),
        check_og_image(final_url, soup),
        check_reading_time(final_url, body),
        check_internal_links(final_url, body, final_url),
        check_h2_structure(final_url, body),
    ]

    counts = {"pass": 0, "warning": 0, "fail": 0, "error": 0}
    for r in results:
        counts[r["status"]] = counts.get(r["status"], 0) + 1

    return {
        "ok": True,
        "url": final_url,
        "score": _score(results),
        "results": results,
        "counts": counts,
    }
