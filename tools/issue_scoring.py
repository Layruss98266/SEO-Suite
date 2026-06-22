"""Impact/effort scoring helper for audit results.

Inspired by DVR79's seo-technical-audit-dashboard. Annotates each
non-passing check with an ``impact`` (1-10), ``effort``
(``low|medium|high``), and computed ``priority`` so the SPA can surface a
"fix-next" list without re-implementing the scoring logic client-side.

Priority formula::

    priority = impact * status_weight / effort_rank

Higher = act on this first. Pass-status checks are excluded — we only
surface things worth fixing.

Pure transformation: no HTTP, no I/O, no mutation of the input dict.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

# Per-tool impact (1–10) and effort (low|medium|high) defaults.
# Easy to extend as audit checks evolve.
_SCORE_TABLE: dict[str, dict[str, Any]] = {
    "title":              {"impact": 9,  "effort": "low"},
    "meta_description":   {"impact": 7,  "effort": "low"},
    "canonical":          {"impact": 8,  "effort": "low"},
    "headings":           {"impact": 6,  "effort": "low"},
    # Batch I checks (viewport, lang, freshness, url, canonical loop, redirect, http2, perf):
    "viewport":           {"impact": 8,  "effort": "low"},
    "lang_attr":          {"impact": 5,  "effort": "low"},
    "content_freshness":  {"impact": 6,  "effort": "high"},
    "url_structure":      {"impact": 7,  "effort": "medium"},
    "canonical_loop":     {"impact": 9,  "effort": "medium"},
    "www_redirect":       {"impact": 6,  "effort": "low"},
    "http2":              {"impact": 5,  "effort": "medium"},
    "render_blocking":    {"impact": 8,  "effort": "medium"},
    "image_optimization": {"impact": 7,  "effort": "medium"},
    "dns_health":         {"impact": 9,  "effort": "low"},
    "image_alt":          {"impact": 6,  "effort": "medium"},
    "schema":             {"impact": 7,  "effort": "medium"},
    "broken_links":       {"impact": 9,  "effort": "medium"},
    "redirect":           {"impact": 8,  "effort": "medium"},
    "internal_links":     {"impact": 6,  "effort": "medium"},
    "ssl":                {"impact": 10, "effort": "medium"},
    "https_enforcement":  {"impact": 9,  "effort": "medium"},
    "security_headers":   {"impact": 6,  "effort": "low"},
    "lcp":                {"impact": 9,  "effort": "high"},
    "cls":                {"impact": 8,  "effort": "high"},
    "fcp":                {"impact": 7,  "effort": "high"},
    "inp":                {"impact": 7,  "effort": "high"},
    "robots":             {"impact": 10, "effort": "low"},
    "sitemap":            {"impact": 7,  "effort": "low"},
    "meta_robots":        {"impact": 9,  "effort": "low"},
    "hreflang":           {"impact": 5,  "effort": "high"},
    "og_tags":            {"impact": 5,  "effort": "low"},
    "readability":        {"impact": 4,  "effort": "high"},
    "word_count":         {"impact": 5,  "effort": "high"},
    "mixed_content":      {"impact": 8,  "effort": "medium"},
    # course / blog specific (from sibling modules):
    "course_schema":      {"impact": 8,  "effort": "medium"},
    "course_cta":         {"impact": 8,  "effort": "low"},
    "course_pricing":     {"impact": 7,  "effort": "low"},
    "blog_article_schema": {"impact": 7, "effort": "medium"},
    "blog_og_image":      {"impact": 6,  "effort": "low"},
}

# Unknown-tool fallback. Kept as a module-level constant so callers can
# read it for tests / debugging without re-deriving the values.
_DEFAULT_SCORE: dict[str, Any] = {"impact": 5, "effort": "medium"}

_EFFORT_RANK = {"low": 1, "medium": 2, "high": 3}
_STATUS_WEIGHT = {"fail": 1.0, "warning": 0.5, "pass": 0.0, "error": 0.7}


def _score_for(tool: str) -> dict[str, Any]:
    """Lookup table value or the default fallback."""
    return _SCORE_TABLE.get(tool, _DEFAULT_SCORE)


def score_issues(audit_result: dict) -> dict:
    """Annotate audit checks with impact/effort/priority.

    Takes a standard audit result dict (must have a ``results`` list of
    check dicts with ``tool`` + ``status`` + ``message``) and returns a
    NEW dict with::

        result["scored_issues"] = [
            {**original, "impact": int, "effort": str, "priority": float},
            ...
        ]
        result["summary"] = {
            "high_impact_count": int,   # impact >= 8
            "quick_wins_count":  int,   # impact >= 7 AND effort == "low"
        }

    Sorted by ``priority`` descending. Pass-status checks are excluded.
    Original ``results`` list is preserved untouched.
    """
    if not isinstance(audit_result, dict):
        # Defensive: return an empty wrapper rather than blow up on
        # unexpected shapes (e.g. a list slipped through upstream).
        return {
            "results": [],
            "scored_issues": [],
            "summary": {"high_impact_count": 0, "quick_wins_count": 0},
        }

    enriched = deepcopy(audit_result)
    checks = enriched.get("results") or []

    scored: list[dict[str, Any]] = []
    for check in checks:
        if not isinstance(check, dict):
            continue
        status = (check.get("status") or "").lower()
        if status == "pass":
            continue
        tool = check.get("tool") or ""
        score = _score_for(tool)
        impact = int(score["impact"])
        effort = str(score["effort"])
        effort_rank = _EFFORT_RANK.get(effort, 2)
        weight = _STATUS_WEIGHT.get(status, _STATUS_WEIGHT["error"])
        priority = round((impact * weight) / effort_rank, 3)

        annotated = dict(check)
        annotated["impact"] = impact
        annotated["effort"] = effort
        annotated["priority"] = priority
        scored.append(annotated)

    scored.sort(key=lambda r: r["priority"], reverse=True)

    high_impact = sum(1 for s in scored if s["impact"] >= 8)
    quick_wins = sum(
        1 for s in scored if s["impact"] >= 7 and s["effort"] == "low"
    )

    enriched["scored_issues"] = scored
    enriched["summary"] = {
        "high_impact_count": high_impact,
        "quick_wins_count": quick_wins,
    }
    return enriched
