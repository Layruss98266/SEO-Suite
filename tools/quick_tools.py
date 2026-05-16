"""
Quick analysis tools — lightweight, single-URL utilities.
Phase A: SERP Snippet Preview, Redirect Chain, HTTP Headers,
         Keyword Density, Code-to-Text Ratio, GZIP/Cache Headers
"""

import re
from typing import Any
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from core.security import safe_requests_get, validate_public_url

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}
TIMEOUT = 15


def _attr_text(tag, name: str, default: str = "") -> str:
    if not tag:
        return default
    value = tag.get(name, default)
    if value is None:
        return default
    if isinstance(value, list | tuple):
        return " ".join(str(item) for item in value).strip()
    return str(value).strip()


# ─── Tool 1: SERP Snippet Preview ────────────────────────────────────────────


def serp_snippet_preview(url: str) -> dict:
    """
    Fetch a URL and return data needed to render a Google-style SERP snippet.
    Returns: title, description, display_url, favicon_url, char counts, warnings.
    """
    try:
        url = validate_public_url(url)
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}

    try:
        resp = safe_requests_get(url, headers=HEADERS, timeout=TIMEOUT)
        final_url = resp.url
        soup = BeautifulSoup(resp.text, "lxml")

        title_tag = soup.find("title")
        title = title_tag.get_text(strip=True) if title_tag else ""

        desc_tag = (
            soup.find("meta", attrs={"name": "description"})
            or soup.find("meta", attrs={"name": "Description"})
            or soup.find("meta", attrs={"property": "og:description"})
        )
        description = _attr_text(desc_tag, "content")

        parsed = urlparse(final_url)
        breadcrumb_parts = [parsed.netloc] + [p for p in parsed.path.split("/") if p]
        display_url = " › ".join(breadcrumb_parts)

        favicon_url = f"{parsed.scheme}://{parsed.netloc}/favicon.ico"

        warnings = []
        if not title:
            warnings.append("Missing <title> tag")
        elif len(title) > 60:
            warnings.append(f"Title too long ({len(title)} chars, recommended ≤60)")
        elif len(title) < 30:
            warnings.append(f"Title too short ({len(title)} chars, recommended ≥30)")

        if not description:
            warnings.append("Missing meta description")
        elif len(description) > 160:
            warnings.append(f"Description too long ({len(description)} chars, recommended ≤160)")
        elif len(description) < 70:
            warnings.append(f"Description too short ({len(description)} chars, recommended ≥70)")

        og_title = ""
        og_desc = ""
        og_image = ""
        tw_title = ""
        tw_desc = ""
        tw_image = ""
        tw_card = ""

        og_t = soup.find("meta", attrs={"property": "og:title"})
        og_d = soup.find("meta", attrs={"property": "og:description"})
        og_i = soup.find("meta", attrs={"property": "og:image"})
        tw_t = soup.find("meta", attrs={"name": "twitter:title"})
        tw_d = soup.find("meta", attrs={"name": "twitter:description"})
        tw_i = soup.find("meta", attrs={"name": "twitter:image"})
        tw_c = soup.find("meta", attrs={"name": "twitter:card"})

        if og_t:
            og_title = _attr_text(og_t, "content")
        if og_d:
            og_desc = _attr_text(og_d, "content")
        if og_i:
            og_image = _attr_text(og_i, "content")
        if tw_t:
            tw_title = _attr_text(tw_t, "content")
        if tw_d:
            tw_desc = _attr_text(tw_d, "content")
        if tw_i:
            tw_image = _attr_text(tw_i, "content")
        if tw_c:
            tw_card = _attr_text(tw_c, "content")

        return {
            "ok": True,
            "url": final_url,
            "display_url": display_url,
            "favicon_url": favicon_url,
            "title": title,
            "title_len": len(title),
            "description": description,
            "desc_len": len(description),
            "og": {"title": og_title, "description": og_desc, "image": og_image},
            "twitter": {
                "title": tw_title,
                "description": tw_desc,
                "image": tw_image,
                "card": tw_card,
            },
            "warnings": warnings,
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ─── Tool 2: Redirect Chain Checker ──────────────────────────────────────────


def redirect_chain(url: str) -> dict:
    """Follow redirects manually and return each hop with status code and latency."""
    import time

    hops: list[dict[str, Any]] = []
    visited = set()
    session = requests.Session()
    session.max_redirects = 20

    try:
        current = validate_public_url(url)
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}

    try:
        while True:
            if current in visited:
                hops.append({"url": current, "status": None, "note": "Redirect loop detected"})
                break
            visited.add(current)

            t0 = time.time()
            resp = session.get(
                current, headers=HEADERS, timeout=TIMEOUT, allow_redirects=False, stream=True
            )
            latency = round((time.time() - t0) * 1000)

            hop: dict[str, Any] = {
                "url": current,
                "status": resp.status_code,
                "latency_ms": latency,
                "note": "",
            }

            if resp.status_code in (301, 302, 303, 307, 308):
                location = resp.headers.get("Location", "") or ""
                if location and not location.startswith("http"):
                    location = urljoin(current, location)
                try:
                    location = validate_public_url(location)
                except ValueError as exc:
                    hop["redirect_to"] = location
                    hop["note"] = f"Blocked unsafe redirect target: {exc}"
                    hops.append(hop)
                    break
                hop["redirect_to"] = location
                hop["type"] = {
                    301: "301 Permanent",
                    302: "302 Temporary",
                    303: "303 See Other",
                    307: "307 Temporary (method preserved)",
                    308: "308 Permanent (method preserved)",
                }.get(resp.status_code, str(resp.status_code))
                hops.append(hop)
                current = location
            else:
                hop["type"] = "Final"
                hops.append(hop)
                break

        issues = []
        if len(hops) > 3:
            issues.append(f"Long redirect chain ({len(hops)} hops) — each hop adds latency")
        if any(h.get("status") == 302 for h in hops[:-1]):
            issues.append("302 temporary redirect found — use 301 for permanent moves")
        if len(hops) > 1:
            first = str(hops[0]["url"])
            last = str(hops[-1]["url"])
            if first.startswith("http://") and last.startswith("https://"):
                pass  # HTTP→HTTPS is expected
            elif any(h.get("status") == 301 for h in hops) and len(hops) > 2:
                issues.append("Multiple 301s detected — consider consolidating")

        return {
            "ok": True,
            "hops": hops,
            "total_hops": len(hops),
            "issues": issues,
        }
    except Exception as e:
        return {"ok": False, "error": str(e), "hops": hops}


# ─── Tool 3: HTTP Headers Viewer ─────────────────────────────────────────────


def http_headers(url: str) -> dict:
    """Return all HTTP response headers with SEO-relevant annotations."""
    try:
        url = validate_public_url(url)
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}

    try:
        resp = safe_requests_get(url, headers=HEADERS, timeout=TIMEOUT)
        raw_headers: dict[str, str] = dict(resp.headers)

        SEO_RELEVANT = {
            "content-type": "Ensures correct MIME type is served",
            "x-robots-tag": "Server-level noindex/nofollow directive",
            "cache-control": "Controls browser & CDN caching",
            "expires": "Legacy cache expiry header",
            "last-modified": "Tells crawlers when content last changed",
            "etag": "Cache validation token",
            "content-encoding": "GZIP/Brotli compression indicator",
            "vary": "Affects caching for mobile/desktop variants",
            "link": "May contain rel=canonical or preload hints",
            "location": "Redirect destination",
            "strict-transport-security": "HTTPS enforcement (HSTS)",
            "x-content-type-options": "Security — prevents MIME sniffing",
            "server": "Server software (minor info-leak risk)",
            "cf-cache-status": "Cloudflare cache hit/miss",
            "age": "Seconds the object has been in a shared cache",
        }

        annotated: list[dict[str, Any]] = []
        for k, v in raw_headers.items():
            key_lower = k.lower()
            annotated.append(
                {
                    "name": k,
                    "value": v,
                    "note": SEO_RELEVANT.get(key_lower, ""),
                    "seo_relevant": key_lower in SEO_RELEVANT,
                }
            )

        annotated.sort(key=lambda x: (not x["seo_relevant"], x["name"].lower()))

        highlights = []
        rl = raw_headers.get("x-robots-tag", "").lower()
        if "noindex" in rl:
            highlights.append(
                {
                    "level": "error",
                    "msg": "x-robots-tag: noindex — page blocked from indexing at server level",
                }
            )
        if "nofollow" in rl:
            highlights.append(
                {
                    "level": "warn",
                    "msg": "x-robots-tag: nofollow — links on this page won't be followed",
                }
            )
        cc = raw_headers.get("cache-control", "")
        if not cc:
            highlights.append(
                {
                    "level": "warn",
                    "msg": "No Cache-Control header — browsers may not cache this resource",
                }
            )
        if "no-store" in cc.lower():
            highlights.append(
                {"level": "warn", "msg": "Cache-Control: no-store — page will never be cached"}
            )
        ce = raw_headers.get("content-encoding", "")
        if not ce:
            highlights.append(
                {
                    "level": "info",
                    "msg": "No content-encoding — GZIP/Brotli compression may not be enabled",
                }
            )

        return {
            "ok": True,
            "url": resp.url,
            "status": resp.status_code,
            "headers": annotated,
            "highlights": highlights,
            "total": len(annotated),
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ─── Tool 4: Keyword Density Checker ─────────────────────────────────────────

STOP_WORDS = {
    "a",
    "an",
    "the",
    "and",
    "or",
    "but",
    "in",
    "on",
    "at",
    "to",
    "for",
    "of",
    "with",
    "by",
    "from",
    "is",
    "are",
    "was",
    "were",
    "be",
    "been",
    "being",
    "have",
    "has",
    "had",
    "do",
    "does",
    "did",
    "will",
    "would",
    "could",
    "should",
    "may",
    "might",
    "shall",
    "can",
    "that",
    "this",
    "these",
    "those",
    "it",
    "its",
    "i",
    "you",
    "he",
    "she",
    "we",
    "they",
    "what",
    "which",
    "who",
    "how",
    "when",
    "where",
    "not",
    "no",
    "so",
    "if",
    "as",
    "up",
    "out",
    "about",
    "into",
    "than",
    "then",
    "also",
    "just",
    "more",
    "some",
    "any",
    "all",
    "very",
    "there",
    "their",
    "they're",
    "we're",
    "don't",
    "doesn't",
    "didn't",
    "it's",
    "i'm",
    "your",
    "our",
    "my",
    "his",
    "her",
}


def keyword_density(url: str, top_n: int = 20) -> dict:
    """Analyse visible text and return top N keywords with density %."""
    try:
        url = validate_public_url(url)
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}

    try:
        resp = safe_requests_get(url, headers=HEADERS, timeout=TIMEOUT)
        soup = BeautifulSoup(resp.text, "lxml")

        for tag in soup(["script", "style", "noscript", "nav", "footer", "header"]):
            tag.decompose()

        text = soup.get_text(separator=" ")
        words = re.findall(r"[a-zA-Z]{3,}", text.lower())
        words = [w for w in words if w not in STOP_WORDS]
        total = len(words)

        from collections import Counter

        counts = Counter(words)
        top = counts.most_common(top_n)

        results = [
            {
                "keyword": kw,
                "count": cnt,
                "density": round(cnt / total * 100, 2) if total else 0,
            }
            for kw, cnt in top
        ]

        title_tag = soup.find("title")
        h1_tags = soup.find_all("h1")
        title_text = title_tag.get_text(strip=True).lower() if title_tag else ""
        h1_text = " ".join(t.get_text(strip=True).lower() for t in h1_tags)

        for r in results:
            kw = r["keyword"]
            r["in_title"] = kw in title_text
            r["in_h1"] = kw in h1_text

        return {
            "ok": True,
            "url": resp.url,
            "total_words": total,
            "unique_words": len(counts),
            "top_keywords": results,
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ─── Tool 5: Code-to-Text Ratio ─────────────────────────────────────────


def code_to_text_ratio(url: str) -> dict:
    """Return the ratio of visible text to total HTML size."""
    try:
        url = validate_public_url(url)
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}

    try:
        resp = safe_requests_get(url, headers=HEADERS, timeout=TIMEOUT)
        html = resp.text
        html_size = len(html.encode("utf-8"))

        soup = BeautifulSoup(html, "lxml")
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        text = " ".join(soup.get_text(separator=" ").split())
        text_size = len(text.encode("utf-8"))

        ratio = round(text_size / html_size * 100, 1) if html_size else 0

        if ratio < 10:
            rating = "poor"
            advice = (
                "Very low text content. Add more meaningful copy or reduce inline scripts/styles."
            )
        elif ratio < 25:
            rating = "average"
            advice = "Text ratio is acceptable but could be improved by adding more content."
        else:
            rating = "good"
            advice = "Good text-to-code ratio."

        return {
            "ok": True,
            "url": resp.url,
            "html_bytes": html_size,
            "text_bytes": text_size,
            "ratio_pct": ratio,
            "rating": rating,
            "advice": advice,
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ─── Tool 6: GZIP / Cache Headers Checker ────────────────────────────────────


def compression_headers(url: str) -> dict:
    """Check GZIP/Brotli compression, Cache-Control, HSTS and related headers."""
    try:
        url = validate_public_url(url)
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}

    try:
        req_headers = {**HEADERS, "Accept-Encoding": "gzip, deflate, br"}
        resp = safe_requests_get(url, headers=req_headers, timeout=TIMEOUT)
        h = {k.lower(): v for k, v in resp.headers.items()}

        encoding = h.get("content-encoding", "none")
        cache_ctrl = h.get("cache-control", "")
        hsts = h.get("strict-transport-security", "")
        vary = h.get("vary", "")
        etag = h.get("etag", "")
        last_mod = h.get("last-modified", "")

        checks = [
            {
                "name": "GZIP / Brotli Compression",
                "pass": encoding.lower() not in ("none", "identity", ""),
                "value": encoding if encoding and encoding != "none" else "Not enabled",
                "advice": "Enable GZIP or Brotli on your server/CDN to reduce transfer size.",
            },
            {
                "name": "Cache-Control header",
                "pass": bool(cache_ctrl),
                "value": cache_ctrl or "Missing",
                "advice": "Add Cache-Control with max-age to leverage browser caching.",
            },
            {
                "name": "HSTS (HTTPS enforcement)",
                "pass": bool(hsts),
                "value": hsts or "Missing",
                "advice": "Add Strict-Transport-Security header to enforce HTTPS.",
            },
            {
                "name": "ETag / Last-Modified (conditional requests)",
                "pass": bool(etag or last_mod),
                "value": etag or last_mod or "Missing",
                "advice": "ETag or Last-Modified enables conditional requests, reducing bandwidth.",
            },
            {
                "name": "Vary header",
                "pass": bool(vary),
                "value": vary or "Missing",
                "advice": "Vary: Accept-Encoding ensures correct cached version is served.",
            },
        ]

        passed = sum(1 for c in checks if c["pass"])
        score = round(passed / len(checks) * 100)

        return {
            "ok": True,
            "url": resp.url,
            "status": resp.status_code,
            "checks": checks,
            "passed": passed,
            "total": len(checks),
            "score": score,
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}
