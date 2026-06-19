"""Cross-URL duplicate-content detector.

Scans a batch of URLs and surfaces pages that share the same
``<title>``, ``<meta name="description">`` or first ``<h1>``.

Useful for catching templating bugs (e.g. every product page renders
the same H1) and thin/duplicated content at site-wide scale, rather
than per-page like ``serp_snippet_preview`` does.

Inspired by https://github.com/DVR79/seo-technical-audit-dashboard
but generalised — works on any list of URLs.
"""

from __future__ import annotations

import logging
import re
from collections import defaultdict

import requests
from bs4 import BeautifulSoup

from core.security import is_safe_url
from tools._common import ToolFetchError, fetch_html
from tools._phase_runner import run_phase

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}

MAX_URLS_HARD_CAP = 100
_WS_RUN = re.compile(r"\s+")


def _normalise(value: str) -> str:
    """Strip, lowercase, collapse runs of whitespace."""
    if not value:
        return ""
    return _WS_RUN.sub(" ", value.strip().lower())


def _extract(url: str) -> dict:
    """Fetch one URL and pull title / meta description / first H1.

    Returns ``{"url", "ok", "title", "description", "h1"}``. On any failure
    (SSRF reject, network, parse) returns ``ok=False`` with empty fields so
    the caller can count failures without short-circuiting the batch.
    """
    ok_safe, _ = is_safe_url(url)
    if not ok_safe:
        return {"url": url, "ok": False, "title": "", "description": "", "h1": ""}

    try:
        resp = fetch_html(url, headers=HEADERS)
        # lxml is XXE-safe for HTML (entities not resolved by default)
        soup = BeautifulSoup(resp.text, "lxml")

        title_tag = soup.find("title")
        title = title_tag.get_text(strip=True) if title_tag else ""

        desc_tag = soup.find("meta", attrs={"name": "description"}) or soup.find(
            "meta", attrs={"name": "Description"}
        )
        description = ""
        if desc_tag:
            val = desc_tag.get("content", "")
            if isinstance(val, list | tuple):
                val = " ".join(str(v) for v in val)
            description = str(val or "").strip()

        h1_tag = soup.find("h1")
        h1 = h1_tag.get_text(strip=True) if h1_tag else ""

        return {
            "url": url,
            "ok": True,
            "title": title,
            "description": description,
            "h1": h1,
        }
    except (ToolFetchError, requests.RequestException, OSError, ValueError) as exc:
        logger.warning("duplicate_detector fetch failed for %s: %s", url, exc)
        return {"url": url, "ok": False, "title": "", "description": "", "h1": ""}


def scan_duplicates(urls: list[str], max_urls: int = 100) -> dict:
    """Group URLs that share a normalised title / description / H1.

    Args:
        urls: list of URLs to scan.
        max_urls: hard cap on inputs (also bounded by ``MAX_URLS_HARD_CAP``).

    Returns:
        ``{"ok", "scanned", "failed", "groups", "summary"}`` — see module docs.
    """
    cap = min(max(1, int(max_urls)), MAX_URLS_HARD_CAP)
    bounded = list(urls)[:cap]

    if not bounded:
        return {
            "ok": True,
            "scanned": 0,
            "failed": 0,
            "groups": [],
            "summary": {
                "total_dup_titles": 0,
                "total_dup_descriptions": 0,
                "total_dup_h1s": 0,
            },
        }

    results = run_phase(bounded, _extract, max_workers=8)

    scanned = sum(1 for r in results if r["ok"])
    failed = len(results) - scanned

    # Build value -> [urls] buckets per field
    buckets: dict[str, dict[str, list[str]]] = {
        "title": defaultdict(list),
        "description": defaultdict(list),
        "h1": defaultdict(list),
    }
    # Preserve display value (first non-empty raw form per normalised key)
    display: dict[str, dict[str, str]] = {"title": {}, "description": {}, "h1": {}}

    for r in results:
        if not r["ok"]:
            continue
        for field in ("title", "description", "h1"):
            raw = r[field]
            norm = _normalise(raw)
            if not norm:
                continue
            buckets[field][norm].append(r["url"])
            display[field].setdefault(norm, raw)

    groups: list[dict] = []
    for field, by_value in buckets.items():
        for norm_value, urls_for_value in by_value.items():
            if len(urls_for_value) >= 2:
                groups.append(
                    {
                        "type": field,
                        "value": display[field].get(norm_value, norm_value),
                        "urls": urls_for_value,
                        "count": len(urls_for_value),
                    }
                )

    groups.sort(key=lambda g: g["count"], reverse=True)

    summary = {
        "total_dup_titles": sum(1 for g in groups if g["type"] == "title"),
        "total_dup_descriptions": sum(1 for g in groups if g["type"] == "description"),
        "total_dup_h1s": sum(1 for g in groups if g["type"] == "h1"),
    }

    return {
        "ok": True,
        "scanned": scanned,
        "failed": failed,
        "groups": groups,
        "summary": summary,
    }
