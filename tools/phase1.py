"""
Phase 1 SEO Tools — No API required
1.  Robots.txt Checker
2.  HTTP Status Checker
3.  Redirect Checker
4.  Canonical Checker
5.  Title Tag Checker
6.  Meta Description Checker
7.  H1/H2 Heading Checker
8.  Image Alt Text Checker
9.  Word Count Checker
10. Broken Link Checker
11. Internal Linking Analyzer
12. XML Sitemap Validator
13. Structured Data / Schema Checker
14. Hreflang Checker
15. TTFB Checker
"""

import json
import logging
import re
import threading
import time
import xml.etree.ElementTree as ET

import requests
from concurrent.futures import ThreadPoolExecutor

from tools._phase_runner import run_phase
from typing import Any
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

from core.security import (
    public_hostname,
    safe_requests_get,
    safe_requests_head,
    validate_public_url,
)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; SEOAuditBot/1.0)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

_PAGE_TTL = 30 * 60  # 30 minutes
_ROBOTS_TTL = 60 * 60  # 1 hour
_CACHE_MAX = 200  # max entries before oldest is evicted

_robots_cache: dict[str, tuple] = {}  # url → (RobotFileParser|None, timestamp)
_page_cache: dict[str, tuple] = {}  # key → (resp, soup, timestamp)
_page_cache_lock = threading.Lock()
_robots_cache_lock = threading.Lock()


def _cache_set(cache: dict, lock: threading.Lock, key: str, value: tuple) -> None:
    """Thread-safe cache insert with LRU eviction at _CACHE_MAX entries."""
    with lock:
        if key not in cache and len(cache) >= _CACHE_MAX:
            cache.pop(next(iter(cache)))
        cache[key] = value


def _cache_get(cache: dict, lock: threading.Lock, key: str) -> tuple | None:
    """Thread-safe cache read."""
    with lock:
        return cache.get(key)


# ── Shared fetch ────────────────────────────────────────────────────────
def fetch_page(url: str, follow_redirects: bool = True) -> tuple:
    """Returns (response, soup). Cached per URL with 30-minute TTL."""
    key = f"{url}|{follow_redirects}"
    cached = _cache_get(_page_cache, _page_cache_lock, key)
    if cached and (time.time() - cached[2]) < _PAGE_TTL:
        return cached[0], cached[1]
    try:
        url = validate_public_url(url)
        if follow_redirects:
            resp = safe_requests_get(url, headers=HEADERS, timeout=8)
        else:
            # safe_requests_head with allow_redirects=False — URL already SSRF-validated above.
            # We use HEAD to avoid downloading the body when we only need status/headers,
            # but fall back to GET if HEAD is not allowed (405).
            try:
                resp = safe_requests_head(url, headers=HEADERS, timeout=8, allow_redirects=False)
                if resp.status_code == 405:
                    resp = safe_requests_get(url, headers=HEADERS, timeout=8, allow_redirects=False)
            except (requests.RequestException, OSError) as exc:
                logger.warning("HEAD request failed for %s, falling back to GET: %s", url, exc)
                resp = safe_requests_get(url, headers=HEADERS, timeout=8, allow_redirects=False)
        soup = (
            BeautifulSoup(resp.text, "html.parser")
            if "text/html" in resp.headers.get("Content-Type", "")
            else None
        )
        _cache_set(_page_cache, _page_cache_lock, key, (resp, soup, time.time()))
        return resp, soup
    except (requests.RequestException, OSError) as exc:
        logger.warning("fetch_page failed for %s: %s", url, exc)
        _cache_set(_page_cache, _page_cache_lock, key, (None, None, time.time()))
        return None, None


def result(
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


# ══════════════════════════════════════════════════════════════════════════════
# 1. Robots.txt Checker
# ══════════════════════════════════════════════════════════════════════════════
def robots_check(url: str) -> dict:
    parsed = urlparse(url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    robots_url = base + "/robots.txt"

    cached = _cache_get(_robots_cache, _robots_cache_lock, base)
    if not cached or (time.time() - cached[1]) > _ROBOTS_TTL:
        try:
            # Fetch via safe_requests_get so every redirect hop is re-validated
            # against the SSRF allowlist — RobotFileParser.read() does its own
            # internal urllib fetch that bypasses our security wrapper.
            r = safe_requests_get(robots_url, timeout=8, headers=HEADERS)
            rp = RobotFileParser()
            rp.set_url(robots_url)
            rp.parse(r.text.splitlines())
            _cache_set(_robots_cache, _robots_cache_lock, base, (rp, time.time()))
        except (requests.RequestException, OSError, ValueError) as exc:
            logger.warning("robots_check fetch failed for %s: %s", robots_url, exc)
            _cache_set(_robots_cache, _robots_cache_lock, base, (None, time.time()))

    cached = _cache_get(_robots_cache, _robots_cache_lock, base)
    rp = cached[0] if cached else None
    if rp is None:
        return result(url, "robots", "warning", None, "Could not fetch robots.txt")

    allowed = rp.can_fetch("*", url)
    googlebot = rp.can_fetch("Googlebot", url)
    crawl_delay = rp.crawl_delay("*")

    status = "pass" if (allowed and googlebot) else "fail"
    msg = "Allowed by robots.txt" if allowed else "Blocked by robots.txt"
    return result(
        url,
        "robots",
        status,
        {"allowed": allowed, "googlebot": googlebot},
        msg,
        {"robots_url": robots_url, "crawl_delay": crawl_delay},
    )


# ══════════════════════════════════════════════════════════════════════════════
# 2. HTTP Status Checker
# ══════════════════════════════════════════════════════════════════════════════
def http_status_check(url: str) -> dict:
    resp, _ = fetch_page(url, follow_redirects=False)
    if resp is None:
        return result(url, "http_status", "error", None, "Request failed")

    code = resp.status_code
    if code == 200:
        s, msg = "pass", f"HTTP {code} OK"
    elif code in (301, 302, 307, 308):
        s, msg = "warning", f"HTTP {code} Redirect"
    elif code == 404:
        s, msg = "fail", f"HTTP {code} Not Found"
    elif code == 410:
        s, msg = "fail", f"HTTP {code} Gone"
    elif code >= 500:
        s, msg = "fail", f"HTTP {code} Server Error"
    else:
        s, msg = "warning", f"HTTP {code}"

    return result(
        url,
        "http_status",
        s,
        code,
        msg,
        {
            "content_type": resp.headers.get("Content-Type", ""),
            "content_length": resp.headers.get("Content-Length", ""),
        },
    )


# ══════════════════════════════════════════════════════════════════════════════
# 3. Redirect Checker
# ══════════════════════════════════════════════════════════════════════════════
def redirect_check(url: str) -> dict:
    try:
        resp = safe_requests_get(url, headers=HEADERS, timeout=8)
        chain = [r.url for r in resp.history] + [resp.url]
        hops = len(resp.history)

        if hops == 0:
            s, msg = "pass", "No redirect"
        elif hops == 1:
            s, msg = "warning", f"1 redirect → {resp.url}"
        else:
            s, msg = "fail", f"Redirect chain: {hops} hops"

        loop = len(set(chain)) < len(chain)
        if loop:
            s, msg = "fail", "Redirect loop detected"

        return result(
            url,
            "redirect",
            s,
            chain,
            msg,
            {
                "hops": hops,
                "final_url": resp.url,
                "loop": loop,
                "codes": [r.status_code for r in resp.history],
            },
        )
    except (requests.RequestException, OSError) as e:
        logger.warning("redirect_check failed for %s: %s", url, e)
        return result(url, "redirect", "error", None, str(e))


# ══════════════════════════════════════════════════════════════════════════════
# 4. Canonical Checker
# ══════════════════════════════════════════════════════════════════════════════
def canonical_check(url: str) -> dict:
    resp, soup = fetch_page(url)
    if not soup:
        return result(url, "canonical", "error", None, "Could not fetch page")

    tag = soup.find("link", rel="canonical")
    if not tag:
        return result(url, "canonical", "warning", None, "No canonical tag found")

    canonical = tag.get("href", "").strip()
    if not canonical:
        return result(url, "canonical", "warning", None, "Canonical tag is empty")

    matches = canonical.rstrip("/") == url.rstrip("/")
    if matches:
        s, msg = "pass", "Canonical points to self"
    else:
        s, msg = "warning", f"Canonical → {canonical}"

    return result(
        url,
        "canonical",
        s,
        canonical,
        msg,
        {"self_referencing": matches, "canonical_url": canonical},
    )


# ══════════════════════════════════════════════════════════════════════════════
# 5. Title Tag Checker
# ══════════════════════════════════════════════════════════════════════════════
def title_check(url: str) -> dict:
    resp, soup = fetch_page(url)
    if not soup:
        return result(url, "title", "error", None, "Could not fetch page")

    tag = soup.find("title")
    title = tag.get_text(strip=True) if tag else ""
    length = len(title)

    if not title:
        s, msg = "fail", "Missing title tag"
    elif length < 30:
        s, msg = "warning", f"Title too short ({length} chars)"
    elif length > 60:
        s, msg = "warning", f"Title too long ({length} chars)"
    else:
        s, msg = "pass", f"Good title ({length} chars)"

    return result(url, "title", s, title, msg, {"length": length, "optimal": 30 <= length <= 60})


# ══════════════════════════════════════════════════════════════════════════════
# 6. Meta Description Checker
# ══════════════════════════════════════════════════════════════════════════════
def meta_description_check(url: str) -> dict:
    resp, soup = fetch_page(url)
    if not soup:
        return result(url, "meta_description", "error", None, "Could not fetch page")

    tag = soup.find("meta", attrs={"name": lambda n: n and n.lower() == "description"})
    desc = tag.get("content", "").strip() if tag else ""
    length = len(desc)

    if not desc:
        s, msg = "fail", "Missing meta description"
    elif length < 70:
        s, msg = "warning", f"Too short ({length} chars)"
    elif length > 160:
        s, msg = "warning", f"Too long ({length} chars)"
    else:
        s, msg = "pass", f"Good length ({length} chars)"

    return result(
        url, "meta_description", s, desc, msg, {"length": length, "optimal": 70 <= length <= 160}
    )


# ══════════════════════════════════════════════════════════════════════════════
# 7. H1 / H2 Heading Checker
# ══════════════════════════════════════════════════════════════════════════════
def heading_check(url: str) -> dict:
    resp, soup = fetch_page(url)
    if not soup:
        return result(url, "headings", "error", None, "Could not fetch page")

    h1s = [h.get_text(strip=True) for h in soup.find_all("h1")]
    h2s = [h.get_text(strip=True) for h in soup.find_all("h2")]
    h3s = [h.get_text(strip=True) for h in soup.find_all("h3")]

    issues = []
    if len(h1s) == 0:
        issues.append("Missing H1")
    if len(h1s) > 1:
        issues.append(f"Multiple H1s ({len(h1s)})")
    if len(h2s) == 0:
        issues.append("No H2 tags")

    s = "fail" if "Missing H1" in issues else "warning" if issues else "pass"
    msg = (
        " | ".join(issues)
        if issues
        else f"Good structure: {len(h1s)} H1, {len(h2s)} H2, {len(h3s)} H3"
    )

    return result(
        url,
        "headings",
        s,
        {"h1": h1s, "h2": h2s[:5], "h3": h3s[:5]},
        msg,
        {"h1_count": len(h1s), "h2_count": len(h2s), "h3_count": len(h3s), "issues": issues},
    )


# ══════════════════════════════════════════════════════════════════════════════
# 8. Image Alt Text Checker
# ══════════════════════════════════════════════════════════════════════════════
def image_alt_check(url: str) -> dict:
    resp, soup = fetch_page(url)
    if not soup:
        return result(url, "image_alt", "error", None, "Could not fetch page")

    images = soup.find_all("img")
    total = len(images)
    missing_alt = [img.get("src", "") for img in images if not img.get("alt", "").strip()]

    if total == 0:
        return result(url, "image_alt", "pass", {}, "No images found")

    pct_missing = round(len(missing_alt) / total * 100, 1)
    s = "fail" if pct_missing > 30 else "warning" if pct_missing > 0 else "pass"
    msg = (
        f"{len(missing_alt)}/{total} images missing alt text"
        if missing_alt
        else f"All {total} images have alt text"
    )

    return result(
        url,
        "image_alt",
        s,
        {"missing": missing_alt[:10]},
        msg,
        {"total": total, "missing_count": len(missing_alt), "pct_missing": pct_missing},
    )


# ══════════════════════════════════════════════════════════════════════════════
# 9. Word Count Checker
# ══════════════════════════════════════════════════════════════════════════════
def word_count_check(url: str) -> dict:
    resp, soup = fetch_page(url)
    if not soup:
        return result(url, "word_count", "error", None, "Could not fetch page")

    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()

    text = soup.get_text(separator=" ")
    words = [w for w in text.split() if len(w) > 1]
    count = len(words)

    if count < 300:
        s, msg = "fail", f"Thin content ({count} words)"
    elif count < 600:
        s, msg = "warning", f"Below average ({count} words)"
    elif count > 2500:
        s, msg = "warning", f"Very long ({count} words)"
    else:
        s, msg = "pass", f"Good length ({count} words)"

    return result(url, "word_count", s, count, msg, {"optimal_min": 600, "optimal_max": 2500})


# ══════════════════════════════════════════════════════════════════════════════
# 10. Broken Link Checker
# ══════════════════════════════════════════════════════════════════════════════
def broken_link_check(url: str) -> dict:
    resp, soup = fetch_page(url)
    if not soup:
        return result(url, "broken_links", "error", None, "Could not fetch page")

    base = f"{urlparse(url).scheme}://{urlparse(url).netloc}"
    anchors = soup.find_all("a", href=True)
    links = []
    for a in anchors:
        href = a["href"].strip()
        if href.startswith("#") or href.startswith("mailto:") or href.startswith("tel:"):
            continue
        full = urljoin(base, href) if not href.startswith("http") else href
        links.append(full)
        if len(links) >= 30:  # cap at 30 unique links
            break

    links = list(dict.fromkeys(links))  # dedupe

    def _check(link):
        try:
            r = safe_requests_head(link, headers=HEADERS, timeout=5)
            if r.status_code in (404, 410, 400, 403):
                return {"url": link, "status": r.status_code}
        except (requests.RequestException, OSError) as exc:
            logger.warning("broken_link_check failed for %s: %s", link, exc)
            return {"url": link, "status": "timeout"}
        return None

    broken = [
        r
        for r in run_phase(links, _check, max_workers=10, preserve_order=False)
        if r
    ]

    s = "fail" if broken else "pass"
    msg = f"{len(broken)} broken link(s) found" if broken else f"All {len(links)} links OK"
    return result(
        url,
        "broken_links",
        s,
        broken,
        msg,
        {"total_checked": len(links), "broken_count": len(broken)},
    )


# ══════════════════════════════════════════════════════════════════════════════
# 11. Internal Linking Analyzer
# ══════════════════════════════════════════════════════════════════════════════
def internal_links_check(url: str) -> dict:
    resp, soup = fetch_page(url)
    if not soup:
        return result(url, "internal_links", "error", None, "Could not fetch page")

    domain = urlparse(url).netloc
    anchors = soup.find_all("a", href=True)

    internal = []
    external = []
    nofollow = []

    for a in anchors:
        href = a.get("href", "").strip()
        if not href or href.startswith("#"):
            continue
        full = urljoin(url, href)
        if urlparse(full).netloc == domain:
            internal.append({"url": full, "text": a.get_text(strip=True)[:60]})
            if "nofollow" in (a.get("rel") or []):
                nofollow.append(full)
        elif href.startswith("http"):
            external.append(full)

    s = "warning" if len(internal) < 3 else "pass"
    msg = f"{len(internal)} internal, {len(external)} external links"
    return result(
        url,
        "internal_links",
        s,
        {"internal": internal[:20], "external": external[:10]},
        msg,
        {
            "internal_count": len(internal),
            "external_count": len(external),
            "nofollow_count": len(nofollow),
        },
    )


# ══════════════════════════════════════════════════════════════════════════════
# 12. XML Sitemap Validator
# ══════════════════════════════════════════════════════════════════════════════
def sitemap_validate(sitemap_url: str) -> dict:
    try:
        sitemap_url = validate_public_url(sitemap_url)
    except ValueError as e:
        return result(sitemap_url, "sitemap", "error", None, f"SSRF guard blocked sitemap URL: {e}")

    try:
        resp = safe_requests_get(sitemap_url, headers=HEADERS, timeout=8)
        resp.raise_for_status()
    except (requests.RequestException, OSError) as e:
        logger.warning("sitemap_validate fetch failed for %s: %s", sitemap_url, e)
        return result(sitemap_url, "sitemap", "error", None, f"Cannot fetch sitemap: {e}")

    issues = []
    urls: list[str] = []
    parse_warning = ""

    # Try strict XML parse first; fall back to lxml recovery, then regex
    try:
        root = ET.fromstring(resp.content)
        ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
        locs = root.findall(".//sm:loc", ns)
        urls = [loc.text.strip() for loc in locs if loc.text]
    except ET.ParseError as xml_err:
        # Try lxml in recovery mode (tolerates common malformed XML like
        # unescaped &)
        try:
            from lxml import etree as lxml_et

            parser = lxml_et.XMLParser(recover=True, resolve_entities=False, no_network=True, huge_tree=False)
            root_lxml = lxml_et.fromstring(resp.content, parser=parser)
            urls = [
                loc.text.strip()
                for loc in root_lxml.iter("{http://www.sitemaps.org/schemas/sitemap/0.9}loc")
                if loc.text
            ]
            parse_warning = f"Sitemap has minor XML issues (auto-recovered): {xml_err}"
        except (ValueError, AttributeError, ImportError) as exc:
            logger.warning("lxml recovery failed for sitemap %s: %s", sitemap_url, exc)
            # Last resort: regex extraction
            import re as _re

            urls = _re.findall(r"<loc>\s*(https?://[^\s<]+)\s*</loc>", resp.text)
            # If no URLs found and response looks like HTML, it's a missing
            # sitemap (not malformed XML)
            body = resp.text.lower()
            if len(urls) == 0 and ("<html" in body or "<!doctype" in body):
                return result(
                    sitemap_url,
                    "sitemap",
                    "warning",
                    None,
                    "No sitemap.xml found at this URL — server returned an HTML page (likely a 404 redirect). "
                    "Add a sitemap via your CMS or submit one in Google Search Console.",
                )
            parse_warning = (
                f"Sitemap XML is malformed — extracted {len(urls)} URLs via fallback: {xml_err}"
            )

    if parse_warning:
        issues.append(parse_warning)

    duplicates = len(urls) - len(set(urls))
    if duplicates:
        issues.append(f"{duplicates} duplicate URLs")

    http_urls = [u for u in urls if u.startswith("http://")]
    if http_urls:
        issues.append(f"{len(http_urls)} HTTP (non-HTTPS) URLs")

    trailing = [u for u in urls if u.endswith(" ")]
    if trailing:
        issues.append(f"{len(trailing)} URLs with trailing spaces")

    if len(urls) > 50000:
        issues.append("Sitemap exceeds 50,000 URL limit")

    s = "fail" if issues else "pass"
    msg = " | ".join(issues) if issues else f"Valid sitemap with {len(urls)} URLs"
    return result(
        sitemap_url,
        "sitemap",
        s,
        {"url_count": len(urls), "issues": issues},
        msg,
        {
            "duplicate_count": duplicates,
            "http_count": len([u for u in urls if u.startswith("http://")]),
        },
    )


# ══════════════════════════════════════════════════════════════════════════════
# 13. Structured Data / Schema Checker
# ══════════════════════════════════════════════════════════════════════════════
def schema_check(url: str) -> dict:
    resp, soup = fetch_page(url)
    if not soup:
        return result(url, "schema", "error", None, "Could not fetch page")

    schemas_found = []
    errors = []

    # JSON-LD
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
            t = data.get("@type", "Unknown") if isinstance(data, dict) else "Multiple"
            schemas_found.append({"format": "JSON-LD", "type": t})
        except json.JSONDecodeError as e:
            errors.append(f"Invalid JSON-LD: {e}")

    # Microdata
    micro = soup.find_all(attrs={"itemtype": True})
    for m in micro:
        schemas_found.append({"format": "Microdata", "type": m.get("itemtype", "")})

    # Open Graph
    og_tags = soup.find_all("meta", property=lambda p: p and p.startswith("og:"))
    if og_tags:
        schemas_found.append({"format": "Open Graph", "type": f"{len(og_tags)} tags"})

    # Twitter Card
    tw_tags = soup.find_all("meta", attrs={"name": lambda n: n and n.startswith("twitter:")})
    if tw_tags:
        schemas_found.append({"format": "Twitter Card", "type": f"{len(tw_tags)} tags"})

    s = "fail" if not schemas_found else "warning" if errors else "pass"
    msg = f"{len(schemas_found)} schema(s) found" if schemas_found else "No structured data found"
    if errors:
        msg += f" | {len(errors)} error(s)"

    return result(
        url,
        "schema",
        s,
        schemas_found,
        msg,
        {"errors": errors, "types": [sc["type"] for sc in schemas_found]},
    )


# ══════════════════════════════════════════════════════════════════════════════
# 14. Hreflang Checker
# ══════════════════════════════════════════════════════════════════════════════
def hreflang_check(url: str) -> dict:
    resp, soup = fetch_page(url)
    if not soup:
        return result(url, "hreflang", "error", None, "Could not fetch page")

    tags = soup.find_all("link", rel="alternate", hreflang=True)
    if not tags:
        return result(
            url,
            "hreflang",
            "warning",
            [],
            "No hreflang tags found",
            {"note": "Only needed for multilingual sites"},
        )

    entries = [{"lang": t.get("hreflang", ""), "url": t.get("href", "")} for t in tags]
    langs = [e["lang"] for e in entries]
    issues = []

    if "x-default" not in langs:
        issues.append("Missing x-default hreflang")
    dupes = [lang for lang in langs if langs.count(lang) > 1]
    if dupes:
        issues.append(f"Duplicate lang codes: {set(dupes)}")

    s = "fail" if issues else "pass"
    msg = " | ".join(issues) if issues else f"{len(entries)} hreflang tags, including x-default"

    return result(
        url,
        "hreflang",
        s,
        entries,
        msg,
        {"lang_count": len(entries), "languages": langs, "issues": issues},
    )


# ══════════════════════════════════════════════════════════════════════════════
# 15. TTFB Checker
# ══════════════════════════════════════════════════════════════════════════════
def ttfb_check(url: str) -> dict:
    try:
        start = time.time()
        resp = safe_requests_get(url, headers=HEADERS, timeout=8, stream=True)
        # Read first byte
        for _ in resp.iter_content(1):
            break
        ttfb_ms = round((time.time() - start) * 1000)
        total_ms = round((time.time() - start) * 1000)

        if ttfb_ms < 200:
            s, msg = "pass", f"Excellent TTFB: {ttfb_ms}ms"
        elif ttfb_ms < 500:
            s, msg = "pass", f"Good TTFB: {ttfb_ms}ms"
        elif ttfb_ms < 800:
            s, msg = "warning", f"Slow TTFB: {ttfb_ms}ms"
        else:
            s, msg = "fail", f"Very slow TTFB: {ttfb_ms}ms"

        return result(
            url,
            "ttfb",
            s,
            ttfb_ms,
            msg,
            {
                "ttfb_ms": ttfb_ms,
                "server": resp.headers.get("Server", ""),
                "cache": resp.headers.get("X-Cache", ""),
                "total_ms": total_ms,
            },
        )
    except (requests.RequestException, OSError) as e:
        logger.warning("ttfb_check failed for %s: %s", url, e)
        return result(url, "ttfb", "error", None, str(e))


# ══════════════════════════════════════════════════════════════════════════════
# 16. Readability Score  (textstat — free, no API)
# ══════════════════════════════════════════════════════════════════════════════
def readability_check(url: str) -> dict:
    try:
        import textstat
    except ImportError:
        return result(
            url, "readability", "error", None, "textstat not installed — run: pip install textstat"
        )
    _, soup = fetch_page(url)
    if not soup:
        return result(url, "readability", "error", None, "Could not fetch page")
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()
    text = soup.get_text(separator=" ", strip=True)
    if len(text.split()) < 50:
        return result(url, "readability", "warning", None, "Too little text to score")
    fk = round(textstat.textstat.flesch_kincaid_grade(text), 1)
    ease = round(textstat.textstat.flesch_reading_ease(text), 1)
    s = "pass" if fk <= 10 else "warning" if fk <= 14 else "fail"
    msg = f"Flesch-Kincaid grade {fk} | Reading ease {ease}/100"
    return result(url, "readability", s, {"fk_grade": fk, "ease": ease}, msg)


# ══════════════════════════════════════════════════════════════════════════════
# 17. Domain Age  (python-whois — free)
# ══════════════════════════════════════════════════════════════════════════════
def domain_age_check(url: str) -> dict:
    try:
        from datetime import datetime as _dt

        import whois as _whois
    except ImportError:
        return result(
            url,
            "domain_age",
            "error",
            None,
            "python-whois not installed — run: pip install python-whois",
        )
    domain = public_hostname(url)
    try:
        w = _whois.whois(domain)
        created = w.get("creation_date")
        if isinstance(created, list):
            created = created[0]
        if not created:
            return result(url, "domain_age", "warning", None, "Creation date unavailable")
        age_days = (_dt.now() - created).days
        age_yrs = round(age_days / 365, 1)
        expiry = w.get("expiration_date")
        if isinstance(expiry, list):
            expiry = expiry[0]
        s = "pass" if age_yrs >= 2 else "warning" if age_yrs >= 1 else "fail"
        created_str = created.strftime("%Y-%m-%d") if hasattr(created, "strftime") else created
        msg = f"Domain age: {age_yrs} years | Created: {created_str}"
        return result(
            url,
            "domain_age",
            s,
            {"age_years": age_yrs, "age_days": age_days},
            msg,
            {"expiry": str(expiry), "registrar": str(w.get("registrar") or "")},
        )
    except Exception as e:
        logger.warning("domain_age_check failed for %s: %s", url, e)
        return result(url, "domain_age", "error", None, f"WHOIS lookup failed: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# 18. SSL / TLS — local cert check (no external API, no quota)
# ══════════════════════════════════════════════════════════════════════════════
def ssl_check(url: str) -> dict:
    import socket as _sock
    import ssl as _ssl
    from datetime import datetime as _dt, timezone as _tz

    if not url.startswith("https"):
        return result(url, "ssl", "fail", None, "Page not served over HTTPS — switch to HTTPS")
    domain = urlparse(url).netloc.split(":")[0]
    try:
        ctx = _ssl.create_default_context()
        with ctx.wrap_socket(
            _sock.create_connection((domain, 443), timeout=8), server_hostname=domain
        ) as s:
            cert = s.getpeercert() or {}
        expiry_raw = cert.get("notAfter", "")
        expiry_str = str(expiry_raw) if expiry_raw else ""
        expiry = _dt.strptime(expiry_str, "%b %d %H:%M:%S %Y %Z") if expiry_str else None
        days_left = (expiry - _dt.now(_tz.utc).replace(tzinfo=None)).days if expiry else None
        if days_left is not None and days_left < 14:
            return result(
                url,
                "ssl",
                "fail",
                expiry_str,
                f"SSL cert expires in {days_left} days — renew immediately",
            )
        if days_left is not None and days_left < 30:
            return result(
                url,
                "ssl",
                "warning",
                expiry_str,
                f"SSL cert expires in {days_left} days — renew soon",
            )
        msg = "Valid SSL cert" + (
            f", expires {expiry.strftime('%Y-%m-%d')} ({days_left}d)" if expiry else ""
        )
        return result(url, "ssl", "pass", expiry_str, msg)
    except _ssl.SSLCertVerificationError as e:
        return result(url, "ssl", "fail", None, f"SSL cert invalid: {e}")
    except (OSError, ValueError) as e:
        logger.warning("ssl_check failed for %s: %s", url, e)
        return result(url, "ssl", "error", None, f"SSL check failed: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# 19. DNS Health  (dnspython — SPF / DMARC / MX)
# ══════════════════════════════════════════════════════════════════════════════
def dns_health_check(url: str) -> dict:
    try:
        import dns.resolver as _dns
    except ImportError:
        return result(
            url, "dns_health", "error", None, "dnspython not installed — run: pip install dnspython"
        )
    domain = public_hostname(url)
    issues = []
    details = {}

    def _txt(name):
        try:
            return [r.to_text().strip('"') for r in _dns.resolve(name, "TXT")]
        except Exception as exc:
            logger.warning("DNS TXT lookup failed for %s: %s", name, exc)
            return []

    def _mx():
        try:
            return [str(r.exchange) for r in _dns.resolve(domain, "MX")]
        except Exception as exc:
            logger.warning("DNS MX lookup failed for %s: %s", domain, exc)
            return []

    with ThreadPoolExecutor(max_workers=3) as ex:
        spf_f = ex.submit(_txt, domain)
        dmarc_f = ex.submit(_txt, f"_dmarc.{domain}")
        mx_f = ex.submit(_mx)
        spf_records = [r for r in spf_f.result() if r.startswith("v=spf1")]
        dmarc_records = [r for r in dmarc_f.result() if r.startswith("v=DMARC1")]
        mx = mx_f.result()

    details["spf"] = spf_records[0][:80] if spf_records else None
    details["dmarc"] = dmarc_records[0][:80] if dmarc_records else None
    details["mx"] = mx[:3]
    if not mx:
        issues.append("No MX records")

    if not spf_records:
        issues.append("SPF record missing")
    if not dmarc_records:
        issues.append("DMARC record missing")

    s = "fail" if len(issues) >= 2 else "warning" if issues else "pass"
    msg = "DNS OK — SPF + DMARC + MX present" if not issues else "; ".join(issues)
    return result(url, "dns_health", s, {"issues": len(issues)}, msg, details)


# ══════════════════════════════════════════════════════════════════════════════
# 21. Open Graph / Twitter Card Checker
# ══════════════════════════════════════════════════════════════════════════════
def og_check(url: str) -> dict:
    _, soup = fetch_page(url)
    if soup is None:
        return result(url, "og_tags", "error", None, "Could not fetch page")

    og = {}
    twitter = {}
    for tag in soup.find_all("meta"):
        prop = (tag.get("property") or "").lower()
        name = (tag.get("name") or "").lower()
        content = tag.get("content", "")
        if prop.startswith("og:"):
            og[prop[3:]] = content
        elif name.startswith("twitter:"):
            twitter[name[8:]] = content

    issues = []
    required_og = ["title", "description", "image", "url", "type"]
    missing_og = [k for k in required_og if not og.get(k)]
    if missing_og:
        issues.append(f"Missing og:{','.join(missing_og)}")
    if not twitter.get("card"):
        issues.append("Missing twitter:card")

    s = "pass" if not issues else "warning" if len(og) >= 3 else "fail"
    msg = f"OG: {len(og)} tags · Twitter: {len(twitter)} tags" if not issues else "; ".join(issues)
    return result(
        url,
        "og_tags",
        s,
        {"og_count": len(og), "twitter_count": len(twitter)},
        msg,
        {"og": og, "twitter": twitter, "missing": missing_og},
    )


# ══════════════════════════════════════════════════════════════════════════════
# 22. Mixed Content Checker  (HTTP resources on HTTPS pages)
# ══════════════════════════════════════════════════════════════════════════════
def mixed_content_check(url: str) -> dict:
    if not url.lower().startswith("https://"):
        return result(
            url, "mixed_content", "warning", None, "Page not served over HTTPS — mixed content N/A"
        )

    _, soup = fetch_page(url)
    if soup is None:
        return result(url, "mixed_content", "error", None, "Could not fetch page")

    insecure = []
    for tag, attr in [
        ("img", "src"),
        ("script", "src"),
        ("link", "href"),
        ("iframe", "src"),
        ("video", "src"),
        ("audio", "src"),
        ("source", "src"),
    ]:
        for el in soup.find_all(tag):
            v = el.get(attr, "")
            if v.lower().startswith("http://"):
                insecure.append({"tag": tag, "url": v[:100]})

    if not insecure:
        return result(url, "mixed_content", "pass", 0, "No mixed content detected")
    s = "fail" if len(insecure) > 3 else "warning"
    return result(
        url,
        "mixed_content",
        s,
        len(insecure),
        f"{len(insecure)} insecure resource(s) on HTTPS page",
        {"insecure": insecure[:20]},
    )


# ══════════════════════════════════════════════════════════════════════════════
# 23. Meta Robots / X-Robots-Tag Checker
# ══════════════════════════════════════════════════════════════════════════════
def meta_robots_check(url: str) -> dict:
    resp, soup = fetch_page(url)
    if soup is None or resp is None:
        return result(url, "meta_robots", "error", None, "Could not fetch page")

    meta_robots = ""
    tag = soup.find("meta", attrs={"name": "robots"})
    if tag:
        meta_robots = (tag.get("content", "") or "").lower()
    x_robots = (resp.headers.get("X-Robots-Tag") or "").lower()
    combined = f"{meta_robots} {x_robots}".strip()

    flags = []
    for k in ["noindex", "nofollow", "noarchive", "nosnippet", "noimageindex"]:
        if k in combined:
            flags.append(k)

    if "noindex" in flags:
        return result(
            url,
            "meta_robots",
            "fail",
            combined,
            "⛔ Page blocked from indexing (noindex)",
            {"meta": meta_robots, "header": x_robots, "flags": flags},
        )
    if flags:
        return result(
            url,
            "meta_robots",
            "warning",
            combined,
            f"Restrictive directives: {','.join(flags)}",
            {"meta": meta_robots, "header": x_robots, "flags": flags},
        )
    return result(
        url,
        "meta_robots",
        "pass",
        combined or "default",
        "Indexing allowed — no restrictive directives",
        {"meta": meta_robots, "header": x_robots},
    )


# ══════════════════════════════════════════════════════════════════════════════
# 24. Favicon Checker
# ══════════════════════════════════════════════════════════════════════════════
def favicon_check(url: str) -> dict:
    _, soup = fetch_page(url)
    if soup is None:
        return result(url, "favicon", "error", None, "Could not fetch page")

    parsed = urlparse(url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    found = {}
    for link in soup.find_all("link"):
        rel = " ".join(link.get("rel", [])).lower()
        href = link.get("href", "")
        if not href:
            continue
        if "icon" in rel:
            full = urljoin(url, href)
            if "apple-touch-icon" in rel:
                found["apple"] = full
            elif "shortcut" in rel or rel.strip() == "icon":
                found["favicon"] = full

    if not found.get("favicon"):
        # Fallback check on /favicon.ico — best-effort, ignore network errors.
        try:
            r = safe_requests_head(base + "/favicon.ico", timeout=5)
            if r.status_code == 200:
                found["favicon"] = base + "/favicon.ico"
        except Exception as e:
            logger.debug("favicon fallback check failed for %s: %s", base, e)

    issues = []
    if not found.get("favicon"):
        issues.append("No favicon")
    if not found.get("apple"):
        issues.append("No apple-touch-icon")

    s = "pass" if not issues else "warning" if len(issues) == 1 else "fail"
    msg = "Favicon + apple-touch-icon present" if not issues else "; ".join(issues)
    return result(url, "favicon", s, len(found), msg, found)


# ══════════════════════════════════════════════════════════════════════════════
# 23-b. HTTPS Enforcement — does HTTP redirect to HTTPS?
# ══════════════════════════════════════════════════════════════════════════════
def https_enforcement_check(url: str) -> dict:
    parsed   = urlparse(url)
    http_url = f"http://{parsed.netloc}{parsed.path or '/'}"
    try:
        resp     = safe_requests_head(http_url, timeout=8)
        final    = resp.url if hasattr(resp, "url") else http_url
        enforced = final.startswith("https://")
        s   = "pass" if enforced else "fail"
        msg = "HTTP → HTTPS redirect enforced" if enforced else "HTTP does not redirect to HTTPS"
        return result(url, "https_enforcement", s, enforced, msg,
                      {"http_url": http_url, "final_url": final})
    except (requests.RequestException, OSError) as e:
        logger.warning("https_enforcement_check failed for %s: %s", url, e)
        return result(url, "https_enforcement", "error", None, f"Check error: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# 23-c. Security Headers — HSTS, CSP, X-Frame-Options, etc.
# ══════════════════════════════════════════════════════════════════════════════
def security_headers_check(url: str) -> dict:
    HEADERS = {
        "Strict-Transport-Security": "HSTS",
        "X-Frame-Options":           "X-Frame-Options",
        "X-Content-Type-Options":    "X-Content-Type-Options",
        "Content-Security-Policy":   "CSP",
        "Referrer-Policy":           "Referrer-Policy",
    }
    try:
        resp    = safe_requests_head(url, timeout=8)
        h       = {k.lower(): v for k, v in resp.headers.items()}
        present = [lbl for hdr, lbl in HEADERS.items() if hdr.lower() in h]
        missing = [lbl for hdr, lbl in HEADERS.items() if hdr.lower() not in h]
        s   = "pass" if not missing else "warning" if len(missing) <= 2 else "fail"
        msg = f"{len(present)}/{len(HEADERS)} security headers present"
        if missing:
            msg += f" — missing: {', '.join(missing[:2])}"
        return result(url, "security_headers", s, {"present": present, "missing": missing}, msg,
                      {"checked": list(HEADERS.values())})
    except (requests.RequestException, OSError) as e:
        logger.warning("security_headers_check failed for %s: %s", url, e)
        return result(url, "security_headers", "error", None, f"Header check error: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# 23-d. SPF Record
# ══════════════════════════════════════════════════════════════════════════════
def spf_check(url: str) -> dict:
    try:
        import dns.resolver as _dns
    except ImportError:
        return result(url, "spf", "warning", None,
                      "dnspython not installed — run: pip install dnspython")
    domain = public_hostname(url)
    try:
        txt = [r.to_text().strip('"') for r in _dns.resolve(domain, "TXT")]
        spf = next((r for r in txt if r.startswith("v=spf1")), None)
        if spf:
            return result(url, "spf", "pass", spf[:80], "SPF record found")
        return result(url, "spf", "fail", None, "No SPF record — email spoofing risk")
    except Exception as e:
        logger.warning("spf_check failed for %s: %s", url, e)
        return result(url, "spf", "error", None, f"SPF lookup error: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# 23-e. DMARC Record
# ══════════════════════════════════════════════════════════════════════════════
def dmarc_check(url: str) -> dict:
    try:
        import dns.resolver as _dns
    except ImportError:
        return result(url, "dmarc", "warning", None,
                      "dnspython not installed — run: pip install dnspython")
    domain = public_hostname(url)
    try:
        txt   = [r.to_text().strip('"') for r in _dns.resolve(f"_dmarc.{domain}", "TXT")]
        dmarc = next((r for r in txt if r.startswith("v=DMARC1")), None)
        if dmarc:
            policy = ("reject"     if "p=reject"     in dmarc else
                      "quarantine" if "p=quarantine" in dmarc else "none")
            s   = "pass" if policy == "reject" else "warning"
            return result(url, "dmarc", s, dmarc[:80], f"DMARC found — policy: {policy}",
                          {"policy": policy})
        return result(url, "dmarc", "fail", None, "No DMARC record found")
    except Exception as e:
        logger.warning("dmarc_check failed for %s: %s", url, e)
        return result(url, "dmarc", "error", None, f"DMARC lookup error: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# 23-f. MX Records
# ══════════════════════════════════════════════════════════════════════════════
def mx_records_check(url: str) -> dict:
    try:
        import dns.resolver as _dns
    except ImportError:
        return result(url, "mx_records", "warning", None,
                      "dnspython not installed — run: pip install dnspython")
    domain = public_hostname(url)
    try:
        mx = [str(r.exchange) for r in _dns.resolve(domain, "MX")]
        if mx:
            return result(url, "mx_records", "pass", mx[:3],
                          f"{len(mx)} MX record(s) found", {"records": mx[:5]})
        return result(url, "mx_records", "fail", [], "No MX records found")
    except Exception as e:
        logger.warning("mx_records_check failed for %s: %s", url, e)
        return result(url, "mx_records", "error", None, f"MX lookup error: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# Batch I — New checks
# ══════════════════════════════════════════════════════════════════════════════

def viewport_check(url: str) -> dict:
    """Check for mobile viewport meta tag."""
    resp, soup = fetch_page(url)
    if resp is None or soup is None:
        return result(url, "viewport", "error", None, "Could not fetch page")
    vp = soup.find("meta", attrs={"name": "viewport"})
    if vp:
        content = vp.get("content", "")
        has_width = "width=device-width" in content
        s = "pass" if has_width else "warning"
        msg = (f"Viewport: {content}" if has_width
               else f"Viewport missing width=device-width — current: {content}")
        return result(url, "viewport", s, {"content": content}, msg,
                      {"has_width_device": has_width})
    return result(url, "viewport", "fail", None,
                  'Missing <meta name="viewport"> — mobile rendering undefined',
                  {"found": False})


def lang_check(url: str) -> dict:
    """Check for html lang attribute."""
    resp, soup = fetch_page(url)
    if resp is None or soup is None:
        return result(url, "lang_attr", "error", None, "Could not fetch page")
    html_tag = soup.find("html")
    lang = html_tag.get("lang", "").strip() if html_tag else ""
    if lang:
        return result(url, "lang_attr", "pass", lang,
                      f'HTML lang attribute set: "{lang}"',
                      {"lang": lang})
    return result(url, "lang_attr", "fail", None,
                  "Missing lang attribute on <html> tag — affects accessibility and hreflang",
                  {"found": False})


def content_freshness_check(url: str) -> dict:
    """Check content freshness signals (Last-Modified header + in-page date meta)."""
    resp, soup = fetch_page(url)
    if resp is None or soup is None:
        return result(url, "content_freshness", "error", None, "Could not fetch page")
    last_modified = resp.headers.get("Last-Modified") or resp.headers.get("last-modified")
    date_signals = [
        ("meta[property='article:modified_time']", "content"),
        ("meta[property='article:published_time']", "content"),
        ("time[datetime]", "datetime"),
        ("meta[name='date']", "content"),
        ("meta[name='revised']", "content"),
    ]
    visible_date = None
    for selector, attr in date_signals:
        el = soup.select_one(selector)
        if el and el.get(attr):
            visible_date = el.get(attr)
            break
    has_signal = bool(last_modified or visible_date)
    if last_modified:
        msg = f"Last-Modified: {last_modified}"
    elif visible_date:
        msg = f"Published/modified date found: {visible_date[:40]}"
    else:
        msg = "No freshness signals — add Last-Modified header or article:modified_time meta"
    return result(url, "content_freshness", "pass" if has_signal else "warning",
                  last_modified or visible_date, msg,
                  {"last_modified": last_modified, "visible_date": visible_date})


def url_structure_check(url: str) -> dict:
    """Check URL structure quality: length, casing, params, slug cleanliness."""
    from urllib.parse import parse_qs
    issues = []
    parsed = urlparse(url)
    path = parsed.path
    params = parse_qs(parsed.query)
    if len(url) > 115:
        issues.append(f"URL length {len(url)} chars (target < 115)")
    if any(c.isupper() for c in path):
        issues.append("Uppercase letters in path")
    if len(params) > 3:
        issues.append(f"{len(params)} query params (crawl budget risk)")
    session_params = {"sid", "sessionid", "session_id", "phpsessid", "jsessionid"}
    found_session = session_params & {p.lower() for p in params}
    if found_session:
        issues.append(f"Session params in URL: {', '.join(sorted(found_session))}")
    slug_parts = [p for p in path.split("/") if p]
    if slug_parts:
        last_slug = slug_parts[-1]
        if re.search(r"\d{8,}", last_slug):
            issues.append("Long numeric ID in slug (consider readable slug)")
        if "_" in last_slug and "-" not in last_slug:
            issues.append("Underscores in URL slug (prefer hyphens)")
    s = "fail" if len(issues) > 2 else "warning" if issues else "pass"
    msg = "; ".join(issues) if issues else f"Clean URL structure ({len(url)} chars)"
    return result(url, "url_structure", s, {"issues": len(issues)}, msg,
                  {"issues": issues, "length": len(url), "params_count": len(params)})


def canonical_loop_check(url: str) -> dict:
    """Detect canonical redirect chains and loops. Warns when no canonical is set."""
    MAX_HOPS = 5
    visited = [url]
    current = url
    first_hop = True
    try:
        for _ in range(MAX_HOPS):
            resp, soup = fetch_page(current)
            if resp is None or soup is None:
                return result(url, "canonical_loop", "error", None,
                              f"Could not fetch {current}")
            tag = soup.find("link", rel="canonical")
            if not tag or not tag.get("href"):
                if first_hop:
                    return result(url, "canonical_loop", "warning", None,
                                  "No canonical tag found — add self-referencing canonical for clarity",
                                  {"suggestion": f'<link rel="canonical" href="{url}">'})
                # Chain terminates cleanly at an intermediate hop
                return result(url, "canonical_loop", "pass", None,
                              f"Canonical chain terminates at {current}", {"hops": visited})
            first_hop = False
            canon_url = tag["href"].strip()
            if not canon_url.startswith("http"):
                canon_url = urljoin(current, canon_url)
            if canon_url == current:
                if len(visited) == 1:
                    return result(url, "canonical_loop", "pass", canon_url,
                                  "Self-referencing canonical (correct)", {})
                chain = " → ".join(visited + [canon_url])
                return result(url, "canonical_loop", "warning", None,
                              f"Canonical chain ({len(visited)} hops): {chain}",
                              {"chain": visited + [canon_url]})
            if canon_url in visited:
                chain = " → ".join(visited + [canon_url])
                return result(url, "canonical_loop", "fail", None,
                              f"Canonical loop detected: {chain}",
                              {"loop": visited + [canon_url]})
            visited.append(canon_url)
            current = canon_url
        chain = " → ".join(visited)
        return result(url, "canonical_loop", "warning", None,
                      f"Canonical chain > {MAX_HOPS} hops: {chain}",
                      {"chain": visited})
    except (requests.RequestException, OSError, ValueError) as exc:
        return result(url, "canonical_loop", "error", None, str(exc))


def www_redirect_check(url: str) -> dict:
    """Check www / non-www redirect consistency."""
    parsed = urlparse(url)
    domain = parsed.netloc
    scheme = parsed.scheme
    has_www = domain.startswith("www.")
    alt_domain = domain[4:] if has_www else f"www.{domain}"
    alt_url = f"{scheme}://{alt_domain}/"
    try:
        resp, _ = fetch_page(alt_url)
    except (requests.RequestException, OSError, ValueError):
        resp = None
    if resp is None:
        return result(url, "www_redirect", "pass", None,
                      f"www variant ({alt_domain}) not reachable — no duplicate content risk",
                      {"tested_url": alt_url, "nxdomain": True})
    try:
        final_netloc = urlparse(resp.url).netloc
        is_consolidated = final_netloc == domain
        if is_consolidated:
            return result(url, "www_redirect", "pass", resp.url,
                          f"Consistent redirect: {alt_url} → {resp.url}",
                          {"tested_url": alt_url, "final_url": resp.url})
        if final_netloc == alt_domain:
            return result(url, "www_redirect", "warning", resp.url,
                          f"{alt_url} resolves independently — duplicate content risk",
                          {"tested_url": alt_url, "final_url": resp.url,
                           "status": resp.status_code})
        return result(url, "www_redirect", "pass", resp.url,
                      f"{alt_url} returned {resp.status_code}",
                      {"tested_url": alt_url, "status": resp.status_code})
    except Exception as exc:
        return result(url, "www_redirect", "error", None, str(exc))


def http2_check(url: str) -> dict:
    """Check HTTP/2 or HTTP/3 support via httpx."""
    try:
        import httpx
        with httpx.Client(http2=True, verify=True, timeout=10,
                          follow_redirects=True) as client:
            resp = client.get(url, headers=HEADERS)
            version = resp.http_version
        is_modern = version in ("HTTP/2", "HTTP/3")
        s = "pass" if is_modern else "warning"
        msg = (f"{version} — multiplexed connections enabled" if is_modern
               else f"HTTP/2 not detected ({version}) — upgrade for faster page loads")
        return result(url, "http2", s, version, msg, {"http_version": version})
    except ImportError:
        return result(url, "http2", "error", None, "httpx not installed")
    except Exception as exc:
        logger.warning("http2_check failed for %s: %s", url, exc)
        return result(url, "http2", "error", None, str(exc))


def render_blocking_check(url: str) -> dict:
    """Check for render-blocking JS and CSS in <head>.

    JS (no async/defer): >0 = warning, >2 = fail  — high impact on TBT/INP
    CSS (media=all/empty): >6 = warning, >12 = fail — lower impact, common in real sites
    """
    resp, soup = fetch_page(url)
    if resp is None or soup is None:
        return result(url, "render_blocking", "error", None, "Could not fetch page")
    head = soup.find("head") or soup
    blocking_scripts = [
        sc.get("src", "")[:100]
        for sc in head.find_all("script", src=True)
        if not sc.get("async") and not sc.get("defer") and sc.get("type") != "module"
    ]
    blocking_styles = [
        lk.get("href", "")[:100]
        for lk in head.find_all("link", rel="stylesheet")
        if not lk.get("media") or lk.get("media") in ("", "all")
    ]
    js_c = len(blocking_scripts)
    css_c = len(blocking_styles)
    total = js_c + css_c
    if js_c > 2 or css_c > 12:
        s = "fail"
    elif js_c > 0 or css_c > 6:
        s = "warning"
    else:
        s = "pass"
    if total:
        msg = (f"{total} render-blocking resources "
               f"({js_c} scripts without async/defer, {css_c} stylesheets)")
    else:
        msg = "No render-blocking resources detected"
    return result(url, "render_blocking", s, total, msg,
                  {"blocking_scripts": blocking_scripts[:5],
                   "blocking_styles": blocking_styles[:5],
                   "scripts": js_c, "stylesheets": css_c})


def image_optimization_check(url: str) -> dict:
    """Check image lazy loading, WebP/AVIF usage, missing dimensions, and LCP hint.

    Skips data: URIs (inline images) and aria-hidden decorative images from dim check.
    """
    resp, soup = fetch_page(url)
    if resp is None or soup is None:
        return result(url, "image_optimization", "error", None, "Could not fetch page")
    images = soup.find_all("img")
    if not images:
        return result(url, "image_optimization", "pass", 0, "No images found", {})
    total = len(images)
    # Content images only (skip data: URIs and decorative images for CLS check)
    content_imgs = [
        img for img in images
        if not img.get("src", "").startswith("data:")
        and img.get("aria-hidden") != "true"
        and img.get("role") != "presentation"
    ]
    lazy = sum(1 for img in images if img.get("loading") == "lazy")
    missing_dims = sum(
        1 for img in content_imgs
        if not img.get("width") or not img.get("height")
    )
    webp_img = sum(
        1 for img in images
        if ".webp" in img.get("src", "").lower()
        or ".avif" in img.get("src", "").lower()
    )
    webp_src = len(soup.find_all("source", type=re.compile(r"image/(webp|avif)")))
    modern = webp_img + webp_src
    has_fetchpriority = any(img.get("fetchpriority") == "high" for img in images)
    issues = []
    content_c = len(content_imgs)
    if content_c > 3 and lazy < content_c * 0.5:
        issues.append(f"Only {lazy}/{content_c} content images use lazy loading")
    if content_c > 0 and missing_dims > content_c * 0.3:
        issues.append(f"{missing_dims}/{content_c} images missing width/height (CLS risk)")
    if content_c > 3 and modern < content_c * 0.3:
        issues.append(f"Low WebP/AVIF usage ({modern}/{content_c} images)")
    if not has_fetchpriority and content_c > 0:
        issues.append("No fetchpriority=high on any image — consider marking the LCP image")
    s = "fail" if len(issues) > 2 else "warning" if issues else "pass"
    msg = ("; ".join(issues) if issues
           else (f"{content_c} images — lazy: {lazy}, "
                 f"modern format: {modern}, dims set: {content_c - missing_dims}"))
    return result(url, "image_optimization", s, total, msg,
                  {"total": total, "content_images": content_c, "lazy_loaded": lazy,
                   "modern_format": modern, "missing_dims": missing_dims,
                   "has_fetchpriority": has_fetchpriority})


# ══════════════════════════════════════════════════════════════════════════════
# Run all Phase 1 tools on a single URL
# ══════════════════════════════════════════════════════════════════════════════
TOOLS = [
    ("Robots.txt", robots_check),
    ("HTTP Status", http_status_check),
    ("Redirects", redirect_check),
    ("Canonical", canonical_check),
    ("Title Tag", title_check),
    ("Meta Description", meta_description_check),
    ("Headings", heading_check),
    ("Image Alt Text", image_alt_check),
    ("Word Count", word_count_check),
    ("Broken Links", broken_link_check),
    ("Internal Links", internal_links_check),
    ("Schema / LD+JSON", schema_check),
    ("Hreflang", hreflang_check),
    ("TTFB", ttfb_check),
    ("Readability", readability_check),
    ("Domain Age", domain_age_check),
    ("SSL Grade", ssl_check),
    ("DNS Health", dns_health_check),
    ("Viewport", viewport_check),
    ("Lang Attribute", lang_check),
    ("Content Freshness", content_freshness_check),
    ("URL Structure", url_structure_check),
    ("Canonical Loop", canonical_loop_check),
    ("WWW Redirect", www_redirect_check),
    ("HTTP/2", http2_check),
    ("Render Blocking", render_blocking_check),
    ("Image Optimization", image_optimization_check),
]


def audit_url(url: str) -> list[dict]:
    results = []
    for name, fn in TOOLS:
        try:
            results.append(fn(url))
        except Exception as e:
            logger.exception("audit_url tool %s failed for %s: %s", name, url, e)
            results.append(result(url, name.lower(), "error", None, str(e)))
    return results
