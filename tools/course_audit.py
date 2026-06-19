"""
Course-page audit — generic (no vertical bias).

Scans a single course landing page for the eight buyer-relevant sections
(overview, outcomes, syllabus, instructor, schedule, pricing, FAQ, CTA),
validates Course JSON-LD, and checks mobile-friendliness. Returns the
standard SEO Suite audit shape so the result plugs into the existing
report drawer / score UI.

Inspired by DVR79/seo-technical-audit-dashboard.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

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

# ── Heading keyword patterns ─────────────────────────────────────────────────
_OUTCOMES_RE   = re.compile(r"\b(outcomes?|what\s+you(?:'|’)?ll\s+learn|objectives?|benefits|key\s+takeaways?)\b", re.I)
_SYLLABUS_RE   = re.compile(r"\b(syllabus|curriculum|modules?|topics?\s+covered|chapters?|course\s+content|lessons?)\b", re.I)
_INSTRUCTOR_RE = re.compile(r"\b(instructors?|trainers?|taught\s+by|teachers?|authors?|facilitators?|your\s+coach)\b", re.I)
_FAQ_RE        = re.compile(r"(\bFAQ(s)?\b|frequently\s+asked|questions?)", re.I)
_CTA_RE        = re.compile(r"\b(enroll|enrol|register|sign\s*up|buy\s+now|buy|start\s+now|book(?:\s+now)?|join\s+now|apply\s+now|add\s+to\s+cart|get\s+started|purchase)\b", re.I)

# Schedule signals: duration / start date / sessions
_DURATION_RE   = re.compile(r"\b\d+(?:\.\d+)?\s*\+?\s*(hours?|hrs?|days?|weeks?|months?|minutes?|mins?)\b", re.I)
_START_RE      = re.compile(r"\b(starts?|start\s+date|begins?|commences?|cohort|next\s+batch|enrollment\s+(?:opens?|closes?))\b", re.I)
_SESSION_RE    = re.compile(r"\b(sessions?|classes?|live\s+sessions?|schedule|timings?|\d{1,2}:\d{2}\s*(?:am|pm)?)\b", re.I)

# Price signals
_CURRENCY_RE   = re.compile(r"(?:[$£€¥₹])\s?\d|(?:USD|EUR|GBP|INR|AUD|CAD|JPY|CNY)\s?\d", re.I)
_FREE_RE       = re.compile(r"\b(free\s+(?:course|of\s+charge|enrollment)?|no\s+cost|complimentary)\b", re.I)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _result(tool: str, status: str, message: str, value: Any = None, **details) -> dict:
    return {
        "tool": tool,
        "status": status,
        "message": message,
        "value": value,
        "details": dict(details),
    }


def _headings_text(soup: BeautifulSoup) -> list[str]:
    return [h.get_text(" ", strip=True) for h in soup.find_all(["h1", "h2", "h3", "h4"])]


def _section_by_heading(soup: BeautifulSoup, pattern: re.Pattern, sources: tuple[str, ...] = ("h1", "h2", "h3", "h4")) -> str | None:
    """Return the matched heading text if any heading matches the pattern."""
    for tag in soup.find_all(list(sources)):
        text = tag.get_text(" ", strip=True)
        if text and pattern.search(text):
            return text
    return None


# ── Individual checks ────────────────────────────────────────────────────────

def check_overview(soup: BeautifulSoup) -> dict:
    h1 = soup.find("h1")
    h1_text = h1.get_text(" ", strip=True) if h1 else ""
    # Find a meaningful paragraph near the top (>= 40 chars)
    intro = ""
    for p in soup.find_all("p")[:30]:
        txt = p.get_text(" ", strip=True)
        if len(txt) >= 40:
            intro = txt
            break
    if h1_text and intro:
        return _result("course_overview", "pass",
                       f"H1 present and intro paragraph found ({len(intro)} chars).",
                       value={"h1": h1_text[:120], "intro_len": len(intro)})
    if h1_text and not intro:
        return _result("course_overview", "warning",
                       "H1 present but no substantial intro paragraph (≥40 chars) detected.",
                       value={"h1": h1_text[:120], "intro_len": 0})
    if intro and not h1_text:
        return _result("course_overview", "warning",
                       "Intro paragraph found but H1 is missing.",
                       value={"h1": "", "intro_len": len(intro)})
    return _result("course_overview", "fail",
                   "Missing both H1 and a meaningful intro paragraph.",
                   value={"h1": "", "intro_len": 0})


def check_outcomes(soup: BeautifulSoup) -> dict:
    match = _section_by_heading(soup, _OUTCOMES_RE)
    if match:
        return _result("course_outcomes", "pass",
                       f"Outcomes section found: '{match[:80]}'.", value=match)
    # Soft fallback — body text mentions outcomes terms
    body_txt = soup.get_text(" ", strip=True)[:5000]
    if _OUTCOMES_RE.search(body_txt):
        return _result("course_outcomes", "warning",
                       "Outcomes keywords mentioned in body but no dedicated heading.",
                       value=None)
    return _result("course_outcomes", "fail",
                   "No 'outcomes / what you'll learn / objectives / benefits' section detected.",
                   value=None)


def check_syllabus(soup: BeautifulSoup) -> dict:
    match = _section_by_heading(soup, _SYLLABUS_RE)
    if match:
        return _result("course_syllabus", "pass",
                       f"Syllabus/curriculum section found: '{match[:80]}'.", value=match)
    body_txt = soup.get_text(" ", strip=True)[:5000]
    if _SYLLABUS_RE.search(body_txt):
        return _result("course_syllabus", "warning",
                       "Syllabus keywords mentioned in body but no dedicated heading.",
                       value=None)
    return _result("course_syllabus", "fail",
                   "No 'syllabus / curriculum / modules / topics / chapters' section detected.",
                   value=None)


def check_instructor(soup: BeautifulSoup) -> dict:
    match = _section_by_heading(soup, _INSTRUCTOR_RE)
    if match:
        return _result("course_instructor", "pass",
                       f"Instructor section found: '{match[:80]}'.", value=match)
    # rel=author signal
    rel_author = soup.find(attrs={"rel": re.compile("author", re.I)})
    if rel_author:
        txt = rel_author.get_text(" ", strip=True) or rel_author.get("href", "")
        return _result("course_instructor", "pass",
                       "Author link (rel=author) present.", value=txt[:120])
    body_txt = soup.get_text(" ", strip=True)[:5000]
    if _INSTRUCTOR_RE.search(body_txt):
        return _result("course_instructor", "warning",
                       "Instructor keywords found in body but no heading or rel=author link.",
                       value=None)
    return _result("course_instructor", "fail",
                   "No instructor / trainer / author information detected.",
                   value=None)


def check_schedule(soup: BeautifulSoup) -> dict:
    body_txt = soup.get_text(" ", strip=True)
    signals = []
    duration = _DURATION_RE.search(body_txt)
    if duration:
        signals.append(f"duration: {duration.group(0)}")
    if _START_RE.search(body_txt):
        signals.append("start date / cohort")
    if _SESSION_RE.search(body_txt):
        signals.append("sessions / schedule")
    if signals:
        return _result("course_schedule", "pass",
                       f"Schedule signals found ({', '.join(signals)}).",
                       value=signals)
    return _result("course_schedule", "fail",
                   "No duration, start date, or session schedule detected.",
                   value=None)


def check_pricing(soup: BeautifulSoup) -> dict:
    # 1. Schema.org price markup
    price_meta = soup.find(attrs={"itemprop": "price"})
    if price_meta:
        val = price_meta.get("content") or price_meta.get_text(" ", strip=True)
        return _result("course_pricing", "pass",
                       f"Price found via itemprop='price': {val}.", value=val)
    # 2. Explicit "free"
    body_txt = soup.get_text(" ", strip=True)
    if _FREE_RE.search(body_txt):
        return _result("course_pricing", "pass",
                       "Course explicitly labelled as Free.", value="free")
    # 3. Currency + number in text
    cur_match = _CURRENCY_RE.search(body_txt)
    if cur_match:
        return _result("course_pricing", "pass",
                       f"Price-like text found: '{cur_match.group(0)}'.",
                       value=cur_match.group(0))
    # 4. Heading / element class hints
    price_class = soup.find(class_=re.compile(r"(price|pricing|cost|fee)", re.I))
    if price_class:
        return _result("course_pricing", "warning",
                       "Element with price-like class found but no concrete price value.",
                       value=None)
    return _result("course_pricing", "fail",
                   "No price, free label, or pricing block detected.",
                   value=None)


def check_faq(soup: BeautifulSoup) -> dict:
    match = _section_by_heading(soup, _FAQ_RE)
    if match:
        return _result("course_faq", "pass",
                       f"FAQ section found: '{match[:80]}'.", value=match)
    return _result("course_faq", "fail",
                   "No FAQ / 'frequently asked questions' section detected.",
                   value=None)


def check_cta(soup: BeautifulSoup) -> dict:
    candidates = soup.find_all(["a", "button", "input"])
    found = []
    for el in candidates:
        text = el.get_text(" ", strip=True) or el.get("value", "") or el.get("aria-label", "")
        if text and _CTA_RE.search(text):
            found.append(text[:60])
            if len(found) >= 5:
                break
    if found:
        return _result("course_cta", "pass",
                       f"{len(found)} call-to-action button/link found.",
                       value=found)
    return _result("course_cta", "fail",
                   "No enroll / register / sign-up / buy CTA detected.",
                   value=None)


def check_schema(soup: BeautifulSoup) -> dict:
    blocks = soup.find_all("script", attrs={"type": "application/ld+json"})
    course_block: dict | None = None
    for tag in blocks:
        raw = tag.string or tag.get_text() or ""
        if not raw.strip():
            continue
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            continue
        # walk
        candidates = []
        if isinstance(data, list):
            candidates.extend(data)
        elif isinstance(data, dict):
            candidates.append(data)
            graph = data.get("@graph")
            if isinstance(graph, list):
                candidates.extend(graph)
        for c in candidates:
            if not isinstance(c, dict):
                continue
            t = c.get("@type")
            types = t if isinstance(t, list) else [t]
            if any(isinstance(x, str) and x.lower() == "course" for x in types):
                course_block = c
                break
        if course_block:
            break

    if not course_block:
        return _result("course_schema", "fail",
                       "No JSON-LD with @type 'Course' found.", value=None)

    # Required-ish fields per Google Course rich result guidance
    required = ["name", "description", "provider"]
    missing = [f for f in required if not course_block.get(f)]
    if missing:
        return _result("course_schema", "warning",
                       f"Course schema present but missing recommended fields: {', '.join(missing)}.",
                       value=list(course_block.keys()), missing=missing)
    return _result("course_schema", "pass",
                   "Course JSON-LD present with required fields (name, description, provider).",
                   value=list(course_block.keys()))


def check_mobile_friendly(soup: BeautifulSoup) -> dict:
    """Viewport meta tag — basic mobile-readiness signal."""
    vp = soup.find("meta", attrs={"name": re.compile("^viewport$", re.I)})
    if not vp:
        return _result("mobile_friendly", "fail",
                       "Missing <meta name='viewport'> — page will not adapt to mobile screens.",
                       value=None)
    content = (vp.get("content") or "").lower()
    if "width=device-width" in content:
        return _result("mobile_friendly", "pass",
                       f"Viewport meta tag set correctly ({content}).", value=content)
    return _result("mobile_friendly", "warning",
                   f"Viewport meta tag present but missing 'width=device-width' ({content}).",
                   value=content)


# ── Orchestrator ─────────────────────────────────────────────────────────────

_CHECKS = (
    check_overview,
    check_outcomes,
    check_syllabus,
    check_instructor,
    check_schedule,
    check_pricing,
    check_faq,
    check_cta,
    check_schema,
    check_mobile_friendly,
)


def _score(results: list[dict]) -> int:
    """Equal weight per check. pass=1, warning=0.5, fail/error=0."""
    if not results:
        return 0
    earned = 0.0
    for r in results:
        s = r.get("status")
        if s == "pass":
            earned += 1.0
        elif s == "warning":
            earned += 0.5
    return round(earned / len(results) * 100)


def _build_soup(html: str) -> BeautifulSoup:
    """lxml parser with XXE-safe handling.

    BeautifulSoup with the `lxml` HTML parser does not resolve external
    entities — lxml's HTMLParser ignores DOCTYPE entity declarations by
    default — but we explicitly avoid `lxml-xml` (which would) to be safe.
    """
    return BeautifulSoup(html, "lxml")


def audit_course_page(url: str) -> dict:
    """Run all course-page checks against a single URL and return the
    standard SEO Suite audit shape:

        {
          "ok": True,
          "url": str,
          "score": int,
          "passes": int,
          "warnings": int,
          "fails": int,
          "results": [...],
        }

    On fetch error: ``{"ok": False, "error": <msg>, "url": url}``.
    """
    try:
        url = validate_public_url(url)
    except ValueError as exc:
        return {"ok": False, "error": str(exc), "url": url}

    try:
        resp = fetch_html(url, headers=HEADERS)
    except (requests.RequestException, OSError, ValueError, ToolFetchError) as exc:
        logger.warning("course_audit fetch failed for %s: %s", url, exc)
        return {"ok": False, "error": safe_error(exc), "url": url}

    if resp.status_code >= 400:
        return {"ok": False, "error": f"HTTP {resp.status_code} from {url}", "url": url}

    try:
        soup = _build_soup(resp.text or "")
    except Exception as exc:  # pragma: no cover — parser failure is rare
        logger.warning("course_audit parse failed for %s: %s", url, exc)
        return {"ok": False, "error": "Failed to parse HTML", "url": url}

    results: list[dict] = []
    for fn in _CHECKS:
        try:
            results.append(fn(soup))
        except Exception as exc:
            logger.warning("course_audit check %s crashed: %s", fn.__name__, exc)
            results.append(_result(fn.__name__.replace("check_", "course_"),
                                   "error",
                                   "Check failed unexpectedly.",
                                   value=None))

    passes   = sum(1 for r in results if r["status"] == "pass")
    warnings = sum(1 for r in results if r["status"] == "warning")
    fails    = sum(1 for r in results if r["status"] in ("fail", "error"))

    return {
        "ok": True,
        "url": resp.url,
        "score": _score(results),
        "passes": passes,
        "warnings": warnings,
        "fails": fails,
        "results": results,
    }
