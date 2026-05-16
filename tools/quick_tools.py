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


# ─── Tool: robots.txt Tester ─────────────────────────────────────────────────

def robots_tester(url: str) -> dict:
    """
    Fetch and analyse a live robots.txt file.
    Parses all User-agent blocks, Disallow/Allow directives, Crawl-delay, and
    Sitemap declarations. Surfaces common issues like full-block of * or Googlebot,
    missing Sitemap, conflicting rules, and crawl-delay on *.
    """
    from urllib.parse import urlparse as _up
    from urllib.robotparser import RobotFileParser

    try:
        url = validate_public_url(url)
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}

    parsed = _up(url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    robots_url = base.rstrip("/") + "/robots.txt"

    try:
        resp = safe_requests_get(robots_url, headers=HEADERS, timeout=TIMEOUT)
    except Exception as exc:
        return {"ok": False, "error": f"Could not fetch robots.txt: {exc}"}

    status_code = resp.status_code
    if status_code == 404:
        return {
            "ok": True, "url": robots_url, "status_code": 404,
            "content": "", "agents": [], "sitemaps": [],
            "issues": [{"level": "warning", "message": "robots.txt not found (HTTP 404) — all crawlers are allowed by default"}],
            "summary": {"total_agents": 0, "has_sitemap": False, "googlebot_blocked": False, "all_blocked": False},
        }
    if status_code >= 400:
        return {"ok": False, "error": f"HTTP {status_code} from {robots_url}"}

    content = resp.text or ""
    lines = content.splitlines()

    # Parse manually so we get per-agent data (RobotFileParser collapses them)
    agents: list[dict] = []
    current_agents: list[str] = []
    current_disallows: list[str] = []
    current_allows: list[str] = []
    current_delay: str | None = None
    sitemaps: list[str] = []
    issues: list[dict] = []

    def _flush():
        if current_agents:
            for ua in current_agents:
                agents.append({
                    "user_agent": ua,
                    "disallows": list(current_disallows),
                    "allows": list(current_allows),
                    "crawl_delay": current_delay,
                })

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if ":" not in stripped:
            continue
        key, _, val = stripped.partition(":")
        key = key.strip().lower()
        val = val.strip()

        if key == "user-agent":
            # Starting a new block? flush previous if we already have directives
            if current_disallows or current_allows or current_delay:
                _flush()
                current_agents = []
                current_disallows = []
                current_allows = []
                current_delay = None
            current_agents.append(val)
        elif key == "disallow":
            current_disallows.append(val)
        elif key == "allow":
            current_allows.append(val)
        elif key == "crawl-delay":
            current_delay = val
        elif key == "sitemap":
            sitemaps.append(val)

    _flush()

    # ── Issue detection ─────────────────────────────────────────────────────
    ua_map = {a["user_agent"].lower(): a for a in agents}

    # 1. Full block of everything
    star_agent = ua_map.get("*")
    all_blocked = bool(star_agent and "/" in star_agent["disallows"] and not star_agent["allows"])
    if all_blocked:
        issues.append({"level": "error", "message": "Disallow: / for * blocks ALL crawlers from the entire site"})

    # 2. Googlebot blocked
    googlebot_blocked = False
    for ua_key in ("googlebot", "google", "googlebot-image", "googlebot-mobile"):
        ag = ua_map.get(ua_key)
        if ag and "/" in ag["disallows"] and not ag["allows"]:
            googlebot_blocked = True
            issues.append({"level": "error", "message": f"Googlebot is fully blocked by User-agent: {ag['user_agent']} / Disallow: /"})
            break

    # 3. Missing sitemap declaration
    if not sitemaps:
        issues.append({"level": "warning", "message": "No Sitemap: directive found — add Sitemap: https://yourdomain.com/sitemap.xml"})

    # 4. Crawl-delay on *
    if star_agent and star_agent.get("crawl_delay"):
        try:
            delay_val = float(star_agent["crawl_delay"])
            if delay_val > 10:
                issues.append({"level": "warning", "message": f"Crawl-delay: {delay_val} for * is very high — Googlebot ignores crawl-delay but other bots may slow significantly"})
        except (ValueError, TypeError):
            issues.append({"level": "warning", "message": f"Invalid Crawl-delay value: {star_agent['crawl_delay']!r}"})

    # 5. Duplicate user-agent blocks
    ua_names = [a["user_agent"].lower() for a in agents]
    dup_uas = {ua for ua in ua_names if ua_names.count(ua) > 1}
    for dup in dup_uas:
        issues.append({"level": "warning", "message": f"Duplicate User-agent block: {dup}"})

    # 6. Disallow empty string (allows everything — redundant)
    for ag in agents:
        if "" in ag["disallows"] and len(ag["disallows"]) == 1:
            issues.append({"level": "info", "message": f"Disallow: (empty) for {ag['user_agent']} explicitly allows all — this is the default and can be removed"})

    # 7. Validate sitemap URLs are on same domain or are public
    for sm in sitemaps:
        sm_parsed = _up(sm)
        if sm_parsed.scheme not in ("http", "https"):
            issues.append({"level": "error", "message": f"Sitemap URL has invalid scheme: {sm}"})

    if not issues:
        issues.append({"level": "info", "message": "No issues detected — robots.txt looks good"})

    # Use RobotFileParser for the allow/block verdict on the target URL
    rp = RobotFileParser()
    rp.set_url(robots_url)
    rp.parse(lines)
    star_allowed = rp.can_fetch("*", url)
    googlebot_allowed = rp.can_fetch("Googlebot", url)

    return {
        "ok": True,
        "url": robots_url,
        "target_url": url,
        "status_code": status_code,
        "content": content[:8000],  # cap raw content to avoid bloating the response
        "agents": agents,
        "sitemaps": sitemaps,
        "issues": issues,
        "verdicts": {
            "star_allowed": star_allowed,
            "googlebot_allowed": googlebot_allowed,
        },
        "summary": {
            "total_agents": len(agents),
            "has_sitemap": bool(sitemaps),
            "googlebot_blocked": googlebot_blocked,
            "all_blocked": all_blocked,
            "issue_count": len([i for i in issues if i["level"] in ("error", "warning")]),
        },
    }


# ─── Tool: hreflang Validator ────────────────────────────────────────────────

def hreflang_validator(url: str) -> dict:
    """
    Fetch a page, extract hreflang tags, validate them, and optionally
    check each alternate URL for reachability (HTTP status).
    Surfaces: missing x-default, duplicate lang codes, relative URLs,
    and unreachable alternates.
    """
    from urllib.parse import urlparse as _up, urljoin as _uj
    from concurrent.futures import ThreadPoolExecutor

    try:
        url = validate_public_url(url)
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}

    try:
        resp = safe_requests_get(url, headers=HEADERS, timeout=TIMEOUT)
    except Exception as exc:
        return {"ok": False, "error": f"Could not fetch page: {exc}"}

    if resp.status_code >= 400:
        return {"ok": False, "error": f"HTTP {resp.status_code} from {url}"}

    from bs4 import BeautifulSoup as _BS
    soup = _BS(resp.text, "html.parser")

    # Collect from <link rel="alternate" hreflang="..."> in <head>
    # and HTTP Link headers
    link_tags = soup.find_all("link", rel="alternate", hreflang=True)
    entries_raw = [
        {"lang": t.get("hreflang", "").strip(), "url": t.get("href", "").strip(), "source": "html"}
        for t in link_tags
    ]

    # Also check HTTP Link header (some sites use header instead of HTML)
    link_header = resp.headers.get("Link", "")
    if link_header and "hreflang=" in link_header:
        for part in link_header.split(","):
            part = part.strip()
            href_match = re.search(r'<([^>]+)>', part)
            lang_match = re.search(r'hreflang=["\']?([^;"\'>\s]+)', part)
            if href_match and lang_match:
                entries_raw.append({
                    "lang": lang_match.group(1),
                    "url": href_match.group(1),
                    "source": "http_header",
                })

    if not entries_raw:
        return {
            "ok": True, "url": url, "entries": [], "issues": [
                {"level": "info", "message": "No hreflang tags found — only needed for multilingual sites"}
            ],
            "summary": {"total": 0, "has_x_default": False, "duplicate_langs": [], "unreachable_count": 0},
        }

    # Resolve relative URLs
    for e in entries_raw:
        if e["url"] and not e["url"].startswith("http"):
            e["url"] = _uj(url, e["url"])

    # Validate reachability (check HTTP status for each alternate URL, cap at 15 URLs)
    def _check_url(entry: dict) -> dict:
        alt_url = entry.get("url", "")
        if not alt_url:
            return {**entry, "status": None, "reachable": False, "redirect_to": None}
        try:
            validate_public_url(alt_url)  # SSRF guard
            r = safe_requests_get(alt_url, headers=HEADERS, timeout=8, allow_redirects=True)
            redirect_to = r.url if r.url != alt_url else None
            return {**entry, "status": r.status_code, "reachable": r.status_code < 400, "redirect_to": redirect_to}
        except Exception:
            return {**entry, "status": None, "reachable": False, "redirect_to": None}

    check_entries = entries_raw[:15]
    with ThreadPoolExecutor(max_workers=min(len(check_entries), 6)) as ex:
        entries = list(ex.map(_check_url, check_entries))

    # Add remaining entries unchecked if truncated
    for e in entries_raw[15:]:
        entries.append({**e, "status": None, "reachable": None, "redirect_to": None})

    # ── Issue detection ─────────────────────────────────────────────────────
    issues: list[dict] = []
    langs = [e["lang"] for e in entries]

    # 1. Missing x-default
    if "x-default" not in langs:
        issues.append({"level": "warning", "message": "Missing x-default hreflang — add one pointing to the default language fallback URL"})

    # 2. Duplicate lang codes
    dup_langs = sorted({lang for lang in langs if langs.count(lang) > 1})
    if dup_langs:
        issues.append({"level": "error", "message": f"Duplicate lang codes: {', '.join(dup_langs)} — each language must appear only once"})

    # 3. Self-referencing — the page itself should declare itself
    page_parsed = _up(url)
    page_norm = f"{page_parsed.scheme}://{page_parsed.netloc}{page_parsed.path}".rstrip("/")
    has_self = any(
        (_up(e["url"]).scheme + "://" + _up(e["url"]).netloc + _up(e["url"]).path).rstrip("/") == page_norm
        for e in entries if e["url"]
    )
    if not has_self:
        issues.append({"level": "warning", "message": "This page does not declare itself as an alternate — add hreflang for its own language pointing to its own URL"})

    # 4. Unreachable alternates
    unreachable = [e for e in entries if e["reachable"] is False]
    for e in unreachable:
        issues.append({"level": "error", "message": f"Alternate URL unreachable ({e.get('status','no response')}): {e['url']}"})

    # 5. Redirect loops or unexpected redirects
    redirected = [e for e in entries if e.get("redirect_to")]
    for e in redirected:
        issues.append({"level": "warning", "message": f"Alternate URL {e['url']} redirects to {e['redirect_to']} — use the canonical destination directly"})

    # 6. Relative URLs (already resolved above but flag as warning)
    for e in entries_raw:
        if e.get("url") and not e["url"].startswith("http"):
            issues.append({"level": "error", "message": f"Relative URL in hreflang: {e['url']} — must be absolute"})

    if not issues:
        issues.append({"level": "info", "message": "No issues found — hreflang tags look correct"})

    return {
        "ok": True,
        "url": url,
        "entries": entries,
        "issues": issues,
        "summary": {
            "total": len(entries),
            "has_x_default": "x-default" in langs,
            "duplicate_langs": dup_langs,
            "unreachable_count": len(unreachable),
            "redirected_count": len(redirected),
        },
    }
