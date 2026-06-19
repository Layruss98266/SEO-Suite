"""
Page-Type Auto-Detector — classify a URL as course / blog / product / generic.

Combines four weighted signal families into a single confidence score so
downstream audit modules (course_audit, blog_audit, product_audit) can pick
the right rule set automatically:

  1. JSON-LD schema  (highest weight) — Course / Product / Article|BlogPosting|NewsArticle
  2. URL path patterns                 — /course, /blog, /product, /shop, /p/, ...
  3. Page-structure heuristics         — pricing + enroll CTA + curriculum, byline + <time>, add-to-cart, etc.
  4. OG type meta                      — og:type=article|product|...

Inspired by DVR79's seo-technical-audit-dashboard.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from core.security import validate_public_url
from tools._common import fetch_html, safe_error

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}

# ─── Signal weights ──────────────────────────────────────────────────────────
W_SCHEMA = 0.40        # JSON-LD @type match — strongest signal
W_OG_TYPE = 0.20       # og:type meta
W_URL_PATTERN = 0.20   # URL slug
W_STRUCT_STRONG = 0.15 # strong structural signal (price element, add-to-cart, etc.)
W_STRUCT_WEAK = 0.07   # weaker individual structural signals

THRESHOLD = 0.40       # winning type needs at least this much weight

# Type → URL fragments
_URL_PATTERNS: dict[str, tuple[str, ...]] = {
    "course": ("/course", "/courses", "/training", "/learn"),
    "blog":   ("/blog", "/news", "/post", "/article", "/articles"),
    "product": ("/product", "/products", "/shop", "/p/", "/item"),
}

# Schema.org @type → page type
_SCHEMA_TYPES: dict[str, str] = {
    "course":       "course",
    "product":      "product",
    "article":      "blog",
    "blogposting":  "blog",
    "newsarticle":  "blog",
}

# og:type → page type
_OG_MAP: dict[str, str] = {
    "article":   "blog",
    "product":   "product",
    "course":    "course",
}


def _iter_jsonld_types(soup: BeautifulSoup) -> list[str]:
    """Pull every @type string out of every JSON-LD <script> on the page."""
    found: list[str] = []
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = script.string or script.get_text() or ""
        raw = raw.strip()
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except (ValueError, TypeError):
            continue
        for node in _walk(data):
            t = node.get("@type")
            if isinstance(t, str):
                found.append(t.lower())
            elif isinstance(t, list):
                found.extend(str(x).lower() for x in t if isinstance(x, str))
    return found


def _walk(node: Any):
    """Yield every dict in a nested JSON-LD blob (handles @graph + arrays)."""
    if isinstance(node, dict):
        yield node
        for v in node.values():
            yield from _walk(v)
    elif isinstance(node, list):
        for item in node:
            yield from _walk(item)


def _structural_signals(soup: BeautifulSoup) -> list[tuple[str, str, float]]:
    """Return (type, signal_name, weight) tuples for structural heuristics."""
    sigs: list[tuple[str, str, float]] = []
    text_lower = soup.get_text(" ", strip=True).lower()[:20000]

    # ── Product signals ──────────────────────────────────────────────────────
    if soup.find("meta", attrs={"itemprop": "price"}) or soup.find(attrs={"itemprop": "price"}):
        sigs.append(("product", "structure:itemprop=price", W_STRUCT_STRONG))
    if re.search(r"add\s+to\s+(cart|bag|basket)", text_lower):
        sigs.append(("product", "structure:add-to-cart", W_STRUCT_STRONG))
    if re.search(r"\b(buy\s+now|in\s+stock|out\s+of\s+stock)\b", text_lower):
        sigs.append(("product", "structure:purchase-cta", W_STRUCT_WEAK))

    # ── Course signals ───────────────────────────────────────────────────────
    has_price_token = bool(re.search(r"[$€£¥]\s?\d", text_lower)) or "price" in text_lower
    has_curriculum = bool(re.search(r"\b(curriculum|syllabus|modules?|lessons?)\b", text_lower))
    has_enroll = bool(re.search(r"\b(enroll|enrol|register now|start learning|join (the )?course)\b", text_lower))
    has_duration = bool(re.search(r"\b\d+\s+(hours?|weeks?|days?|months?)\b", text_lower))
    course_hits = sum([has_price_token, has_curriculum, has_enroll, has_duration])
    if course_hits >= 3:
        sigs.append(("course", "structure:price+curriculum+enroll+duration", W_STRUCT_STRONG))
    elif has_curriculum and has_enroll:
        sigs.append(("course", "structure:curriculum+enroll", W_STRUCT_WEAK))

    # ── Blog signals ─────────────────────────────────────────────────────────
    has_byline = bool(
        soup.find(attrs={"rel": "author"})
        or soup.find("address")
        or soup.find(attrs={"class": re.compile(r"\b(byline|author)\b", re.I)})
    )
    time_tag = soup.find("time")
    has_time = bool(time_tag and (time_tag.get("datetime") or time_tag.get_text(strip=True)))
    has_comments = bool(
        soup.find(id=re.compile(r"comments?", re.I))
        or soup.find(attrs={"class": re.compile(r"\bcomments?\b", re.I)})
    )
    blog_hits = sum([has_byline, has_time, has_comments])
    if blog_hits >= 2:
        sigs.append(("blog", "structure:byline+time+comments", W_STRUCT_STRONG))
    elif has_byline or has_time:
        sigs.append(("blog", "structure:byline-or-time", W_STRUCT_WEAK))

    return sigs


def detect_page_type(url: str, *, html: str | None = None) -> dict:
    """Classify a URL by content shape.

    Returns:
        {
          "url": str,
          "type": "course" | "blog" | "product" | "generic",
          "confidence": float,   # 0.0–1.0
          "signals": [           # ordered, highest-weight first
            {"name": "schema:Course", "weight": 0.4},
            {"name": "url-pattern:/course/", "weight": 0.2},
            ...
          ],
          "ok": True,
        }

    Pass ``html=...`` to skip the HTTP fetch (used by tests).
    """
    try:
        url = validate_public_url(url)
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}

    final_url = url
    if html is None:
        try:
            resp = fetch_html(url, headers=HEADERS)
            html = resp.text
            final_url = resp.url
        except (requests.RequestException, OSError, ValueError) as exc:
            logger.warning("page_type fetch failed for %s: %s", url, exc)
            return {"ok": False, "error": safe_error(exc)}

    soup = BeautifulSoup(html or "", "lxml")

    # accumulator: type -> [(signal_name, weight), ...]
    bucket: dict[str, list[tuple[str, float]]] = {"course": [], "blog": [], "product": []}

    # 1. JSON-LD schema
    for t in _iter_jsonld_types(soup):
        target = _SCHEMA_TYPES.get(t)
        if target:
            bucket[target].append((f"schema:{t}", W_SCHEMA))

    # 2. URL pattern
    path = (urlparse(final_url).path or "").lower()
    for ptype, patterns in _URL_PATTERNS.items():
        for pat in patterns:
            if pat in path:
                bucket[ptype].append((f"url-pattern:{pat}", W_URL_PATTERN))
                break  # one URL signal per type is enough

    # 3. OG type meta
    og_tag = soup.find("meta", attrs={"property": "og:type"})
    if og_tag:
        og_val = (og_tag.get("content") or "").strip().lower()
        # og:type uses values like "article", "product", "video.movie"
        for key, target in _OG_MAP.items():
            if og_val == key or og_val.startswith(key + "."):
                bucket[target].append((f"og:type={og_val}", W_OG_TYPE))
                break

    # 4. Structural heuristics
    for ptype, name, weight in _structural_signals(soup):
        bucket[ptype].append((name, weight))

    # Score each type — cap at 1.0
    scores = {p: min(sum(w for _, w in sigs), 1.0) for p, sigs in bucket.items()}
    winner = max(scores, key=scores.get)  # type: ignore[arg-type]
    winning_score = scores[winner]

    if winning_score >= THRESHOLD:
        chosen = winner
        confidence = round(winning_score, 3)
        signals_out = sorted(bucket[chosen], key=lambda x: -x[1])
    else:
        chosen = "generic"
        # Surface whatever weak signals we saw so callers can debug
        all_sigs = [(n, w) for sigs in bucket.values() for n, w in sigs]
        signals_out = sorted(all_sigs, key=lambda x: -x[1])
        confidence = round(winning_score, 3)

    return {
        "ok": True,
        "url": final_url,
        "type": chosen,
        "confidence": confidence,
        "signals": [{"name": n, "weight": round(w, 3)} for n, w in signals_out],
    }
