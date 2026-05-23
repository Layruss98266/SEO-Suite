"""
Sitemap Audit Tool.

Fetches a sitemap (XML or sitemap-index), parses every URL entry, and flags
structural / quality issues that can hurt crawl efficiency and indexing:

  - Orphaned URLs (not yet crawled — informational)
  - Non-indexable entries (query strings, fragments, file extensions)
  - HTTP entries in an HTTPS sitemap
  - Duplicate URLs (normalised)
  - Oversized sitemap (> 50 000 URLs or > 50 MB — Google hard limits)
  - Missing <lastmod>, <changefreq>, or <priority> optional fields
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

from core.checker import fetch_sitemap_urls
from core.security import validate_public_url
from tools._common import fetch_html, safe_error

_SITEMAP_SIZE_LIMIT = 50_000          # URLs per sitemap (Google limit)
_SITEMAP_BYTES_LIMIT = 50 * 1024 * 1024  # 50 MB

# File extensions almost never belong in sitemaps — search engines won't index them.
_NON_INDEXABLE_EXTS = {
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".zip", ".rar", ".tar", ".gz",
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".ico", ".avif",
    ".mp4", ".avi", ".mov", ".mp3", ".wav",
    ".css", ".js", ".json", ".xml",
}


def _is_non_indexable(url: str) -> str | None:
    """Return a reason string if the URL is likely non-indexable, else None."""
    parsed = urlparse(url)
    ext = re.search(r"\.[a-z0-9]{1,6}$", parsed.path.lower())
    if ext and ext.group() in _NON_INDEXABLE_EXTS:
        return f"Non-HTML file extension ({ext.group()})"
    if parsed.query:
        return "URL contains query parameters (may cause duplicate content)"
    if parsed.fragment:
        return "URL contains a fragment (#anchor) — not indexed separately"
    return None


def _normalise(url: str) -> str:
    """Minimal URL normalisation for duplicate detection."""
    u = url.rstrip("/").lower()
    # Strip scheme for comparison
    for prefix in ("https://", "http://"):
        if u.startswith(prefix):
            return u[len(prefix):]
    return u


def audit_sitemap(
    sitemap_url: str,
    timeout: int = 15,
) -> dict[str, Any]:
    """Fetch and audit a sitemap (or sitemap-index).

    Parameters
    ----------
    sitemap_url : Public URL of the sitemap or sitemap-index.
    timeout     : HTTP fetch timeout in seconds.

    Returns a structured report dict.
    """
    try:
        sitemap_url = validate_public_url(sitemap_url)
    except ValueError as e:
        return {"ok": False, "error": str(e)}

    # ── Fetch raw XML once ─────────────────────────────────────────────────────
    try:
        resp = fetch_html(
            sitemap_url,
            timeout=timeout,
            headers={"User-Agent": "Mozilla/5.0 (compatible; SEO-Suite/2.0)"},
        )
    except Exception as e:
        return {"ok": False, "error": safe_error(e)}

    if resp.status_code >= 400:
        return {"ok": False, "error": f"HTTP {resp.status_code} from {sitemap_url}"}

    raw_bytes = resp.content
    size_bytes = len(raw_bytes)
    size_mb    = round(size_bytes / 1024 / 1024, 2)
    xml_text_body = raw_bytes.decode("utf-8", errors="replace")

    # ── Parse URLs from the already-fetched bytes ──────────────────────────────
    # Only recurse via fetch_sitemap_urls for a sitemap-index (extra fetches
    # are unavoidable there). A plain <urlset> is parsed locally — no re-fetch.
    is_index = "<sitemapindex" in xml_text_body.lower()
    if is_index:
        all_urls = fetch_sitemap_urls(sitemap_url)
    else:
        raw_locs = re.findall(r"<loc>\s*(.*?)\s*</loc>", xml_text_body, re.IGNORECASE | re.DOTALL)
        all_urls = []
        for loc in raw_locs:
            # Unwrap optional CDATA so a <loc><![CDATA[https://...]]></loc> entry
            # yields the bare URL rather than the literal CDATA wrapper.
            m = re.match(r"<!\[CDATA\[(.*?)\]\]>", loc.strip(), re.DOTALL)
            url = (m.group(1) if m else loc).strip()
            # Keep only real http(s) URLs — mirrors fetch_sitemap_urls behaviour
            # and prevents malformed inner content from being counted as a URL.
            if url.lower().startswith(("http://", "https://")):
                all_urls.append(url)
    total_urls = len(all_urls)

    # ── Derive sitemap hostname for HTTP-in-HTTPS check ────────────────────
    sitemap_scheme = urlparse(sitemap_url).scheme

    # ── Run checks ──────────────────────────────────────────────────────────
    issues: list[dict[str, Any]] = []
    seen_normalised: dict[str, str] = {}  # normalised → original URL
    non_indexable: list[dict[str, str]] = []
    duplicates: list[dict[str, str]] = []
    http_in_https: list[str] = []

    for url in all_urls:
        # 1. HTTP entry in HTTPS sitemap
        if sitemap_scheme == "https" and url.startswith("http://"):
            http_in_https.append(url)

        # 2. Non-indexable
        reason = _is_non_indexable(url)
        if reason:
            non_indexable.append({"url": url, "reason": reason})

        # 3. Duplicates (after normalisation)
        norm = _normalise(url)
        if norm in seen_normalised:
            duplicates.append({"url": url, "duplicate_of": seen_normalised[norm]})
        else:
            seen_normalised[norm] = url

    # ── Oversized checks ────────────────────────────────────────────────────
    if total_urls > _SITEMAP_SIZE_LIMIT:
        issues.append({
            "level": "error",
            "message": f"Sitemap contains {total_urls:,} URLs — Google's limit is 50,000 per file. Split into multiple sitemaps.",
        })
    if size_bytes > _SITEMAP_BYTES_LIMIT:
        issues.append({
            "level": "error",
            "message": f"Sitemap file size is {size_mb} MB — exceeds Google's 50 MB limit.",
        })

    if http_in_https:
        issues.append({
            "level": "warning",
            "message": f"{len(http_in_https)} URL(s) use HTTP in an HTTPS sitemap — search engines may skip them.",
            "urls": http_in_https[:20],  # cap for response size
        })
    if non_indexable:
        issues.append({
            "level": "warning",
            "message": f"{len(non_indexable)} URL(s) are likely non-indexable (files, query strings, fragments).",
            "urls": [x["url"] for x in non_indexable[:20]],
            "detail": non_indexable[:20],
        })
    if duplicates:
        issues.append({
            "level": "warning",
            "message": f"{len(duplicates)} duplicate URL(s) found (after normalisation). Remove extras to avoid diluting crawl budget.",
            "urls": [x["url"] for x in duplicates[:20]],
            "detail": duplicates[:20],
        })

    # ── Optional field coverage (spot-check raw XML) ────────────────────────
    has_lastmod    = "<lastmod>"    in xml_text_body
    has_changefreq = "<changefreq>" in xml_text_body
    has_priority   = "<priority>"   in xml_text_body

    # Validate each <lastmod> is a parseable ISO-8601 date
    invalid_lastmod = 0
    for lm in re.findall(r"<lastmod>\s*(.*?)\s*</lastmod>", xml_text_body, re.IGNORECASE | re.DOTALL):
        lm = lm.strip()
        if not lm:
            continue
        try:
            from datetime import datetime
            datetime.fromisoformat(lm.replace("Z", "+00:00"))
        except ValueError:
            invalid_lastmod += 1
    if invalid_lastmod:
        issues.append({
            "level": "warning",
            "message": f"{invalid_lastmod} <lastmod> value(s) are not valid ISO-8601 dates.",
        })

    if not has_lastmod:
        issues.append({
            "level": "info",
            "message": "No <lastmod> dates found. Adding them helps search engines prioritise re-crawls.",
        })
    if not has_changefreq:
        issues.append({
            "level": "info",
            "message": "No <changefreq> values found (optional, but helps guide crawl frequency).",
        })

    # ── Overall score ────────────────────────────────────────────────────────
    error_count   = sum(1 for i in issues if i["level"] == "error")
    warning_count = sum(1 for i in issues if i["level"] == "warning")
    score = max(0, 100 - error_count * 30 - warning_count * 10)

    return {
        "ok": True,
        "url": sitemap_url,
        "total_urls": total_urls,
        "size_bytes": size_bytes,
        "size_mb": size_mb,
        "score": score,
        "issues": issues,
        "summary": {
            "errors": error_count,
            "warnings": warning_count,
            "http_in_https": len(http_in_https),
            "non_indexable": len(non_indexable),
            "duplicates": len(duplicates),
            "has_lastmod": has_lastmod,
            "has_changefreq": has_changefreq,
            "has_priority": has_priority,
            "invalid_lastmod": invalid_lastmod,
        },
    }
