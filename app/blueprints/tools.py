"""SEO tool routes — ``/api/tools/*``.

Thin HTTP wrappers around the underlying modules in :mod:`tools`. Each route
performs request validation (URL normalisation, SSRF guard, integer clamping,
credential checks) before delegating to the tool function.

Groups (matching dashboard nav):

* **Quick tools** — SERP preview, redirect chain, HTTP headers, keyword
  density, code/text ratio, GZIP & cache
* **IndexNow** — submit + key generation
* **Sitemap / Schema** — audit + validation
* **Keyword research** — DataForSEO Labs
* **Bing Webmaster** — overview, inspect, submit
* **GSC opportunities + analytics** — opportunity scan, AI draft, position
  tracker, CTR analyzer, coverage errors, sitemaps status
* **Performance** — Lighthouse opportunity layer
* **AI assist** — explain audit, draft meta
* **Generators** — schema, robots.txt, sitemap, hreflang, meta tags
* **Diagnostics** — robots tester, hreflang validator, link health
* **Notifications** — test email/slack/teams

Most routes treat empty credentials as a 400 with a hint pointing the user at
the Settings UI; that keeps tools degrading gracefully when keys aren't
configured rather than blowing up at the API layer.
"""

from __future__ import annotations

import logging
import os


from flask import Blueprint, jsonify, request

from app.state import (
    CFG,
    _int,
    _norm_url,
    _reject_unsafe,
    _require_public_url,
)
from core.auth import login_required
from core.checker import build_gsc_service

logger = logging.getLogger(__name__)

bp = Blueprint("tools", __name__)


# ─── Quick tools ──────────────────────────────────────────────────────────────
@bp.route("/api/tools/serp_preview", methods=["POST"])
@login_required
def api_serp_preview():
    data = request.get_json(force=True) or {}
    url = _norm_url((data.get("url") or "").strip())
    if not url:
        return jsonify({"ok": False, "error": "url required"}), 400
    if (rej := _reject_unsafe(url)):
        return rej
    from tools.quick_tools import serp_snippet_preview

    return jsonify(serp_snippet_preview(url))


@bp.route("/api/tools/redirect_chain", methods=["POST"])
@login_required
def api_redirect_chain():
    data = request.get_json(force=True) or {}
    url = _norm_url((data.get("url") or "").strip())
    if not url:
        return jsonify({"ok": False, "error": "url required"}), 400
    if (rej := _reject_unsafe(url)):
        return rej
    from tools.quick_tools import redirect_chain

    return jsonify(redirect_chain(url))


@bp.route("/api/tools/http_headers", methods=["POST"])
@login_required
def api_http_headers():
    data = request.get_json(force=True) or {}
    url = _norm_url((data.get("url") or "").strip())
    if not url:
        return jsonify({"ok": False, "error": "url required"}), 400
    if (rej := _reject_unsafe(url)):
        return rej
    from tools.quick_tools import http_headers

    return jsonify(http_headers(url))


@bp.route("/api/tools/keyword_density", methods=["POST"])
@login_required
def api_keyword_density():
    data = request.get_json(force=True) or {}
    url = _norm_url((data.get("url") or "").strip())
    top_n = _int(data, "top_n", 20, 1, 500)
    if not url:
        return jsonify({"ok": False, "error": "url required"}), 400
    if (rej := _reject_unsafe(url)):
        return rej
    from tools.quick_tools import keyword_density

    return jsonify(keyword_density(url, top_n=top_n))


@bp.route("/api/tools/code_text_ratio", methods=["POST"])
@login_required
def api_code_text_ratio():
    data = request.get_json(force=True) or {}
    url = _norm_url((data.get("url") or "").strip())
    if not url:
        return jsonify({"ok": False, "error": "url required"}), 400
    if (rej := _reject_unsafe(url)):
        return rej
    from tools.quick_tools import code_to_text_ratio

    return jsonify(code_to_text_ratio(url))


@bp.route("/api/tools/compression", methods=["POST"])
@login_required
def api_compression():
    data = request.get_json(force=True) or {}
    url = _norm_url((data.get("url") or "").strip())
    if not url:
        return jsonify({"ok": False, "error": "url required"}), 400
    if (rej := _reject_unsafe(url)):
        return rej
    from tools.quick_tools import compression_headers

    return jsonify(compression_headers(url))


# ─── IndexNow ────────────────────────────────────────────────────────────────
@bp.route("/api/tools/indexnow_submit", methods=["POST"])
@login_required
def api_indexnow_submit():
    """Submit one or more URLs to IndexNow (Bing / Yandex)."""
    data = request.get_json(force=True) or {}
    raw_urls = data.get("urls") or data.get("url") or []
    if isinstance(raw_urls, str):
        raw_urls = [u.strip() for u in raw_urls.replace(",", "\n").splitlines() if u.strip()]
    if not raw_urls:
        return jsonify({"ok": False, "error": "urls required"}), 400

    key = (data.get("key") or CFG.get("indexnow_key", "")).strip()
    host = (data.get("host") or CFG.get("indexnow_host", "")).strip()
    if not key:
        return jsonify(
            {"ok": False, "error": "IndexNow API key required (set in Settings → indexnow_key)"}
        ), 400
    if not host:
        return jsonify(
            {"ok": False, "error": "Host required (set in Settings → indexnow_host)"}
        ), 400

    from tools.indexnow import submit_bulk, submit_url

    if len(raw_urls) == 1:
        return jsonify(submit_url(raw_urls[0], key, host))
    return jsonify(submit_bulk(raw_urls, key, host))


@bp.route("/api/tools/indexnow_generate_key", methods=["POST"])
@login_required
def api_indexnow_generate_key():
    """Generate a fresh IndexNow API key."""
    from tools.indexnow import generate_key

    return jsonify({"ok": True, "key": generate_key()})


# ─── Sitemap / Schema validation ─────────────────────────────────────────────
@bp.route("/api/tools/sitemap_audit", methods=["POST"])
@login_required
def api_sitemap_audit():
    """Fetch and audit a sitemap — checks structure, duplicates, size, HTTP links."""
    data = request.get_json(force=True) or {}
    url = _norm_url((data.get("url") or "").strip())
    if not url:
        return jsonify({"ok": False, "error": "url required"}), 400
    if (rej := _reject_unsafe(url)):
        return rej
    from tools.sitemap_audit import audit_sitemap

    return jsonify(audit_sitemap(url))


@bp.route("/api/tools/schema_validate", methods=["POST"])
@login_required
def api_schema_validate():
    """Fetch a URL, extract JSON-LD blocks, validate against Schema.org."""
    data = request.get_json(force=True) or {}
    url = _norm_url((data.get("url") or "").strip())
    if not url:
        return jsonify({"ok": False, "error": "url required"}), 400
    if (rej := _reject_unsafe(url)):
        return rej
    from tools.schema_validator import validate_url

    return jsonify(validate_url(url))


# ─── Keyword research ────────────────────────────────────────────────────────
@bp.route("/api/tools/keyword_research", methods=["POST"])
@login_required
def api_keyword_research():
    """DataForSEO Labs keyword research — related / suggestions / ideas."""
    data = request.get_json(force=True) or {}
    keywords = data.get("keywords") or []
    if isinstance(keywords, str):
        keywords = [k.strip() for k in keywords.split(",") if k.strip()]
    if not keywords:
        return jsonify({"ok": False, "error": "keywords required"}), 400
    mode = (data.get("mode") or "auto").strip()
    location_code = _int(data, "location_code", 2840, 1, 99999)
    language_code = (data.get("language_code") or "en").strip()
    limit = _int(data, "limit", 150, 1, 1000)

    login = CFG.get("dataforseo_login", "")
    password = CFG.get("dataforseo_password", "")

    from tools.keyword_research import research_keywords

    return jsonify(
        research_keywords(
            keywords,
            login,
            password,
            location_code=location_code,
            language_code=language_code,
            limit=limit,
            mode=mode,
        )
    )


# ─── Bing Webmaster ──────────────────────────────────────────────────────────
@bp.route("/api/tools/bing/overview", methods=["POST"])
@login_required
def api_bing_overview():
    """Full Bing Webmaster overview: traffic + crawl stats + sitemap status."""
    data = request.get_json(force=True) or {}
    site_url = _norm_url((data.get("site_url") or "").strip())
    api_key = (data.get("api_key") or CFG.get("bing_api_key", "")).strip()
    period = _int(data, "period", 2, 1, 3)
    if not site_url:
        return jsonify({"ok": False, "error": "site_url required"}), 400
    if (rej := _require_public_url(site_url, "site_url"))[1]:
        return rej[1]
    if not api_key:
        return jsonify(
            {"ok": False, "error": "Bing API key required (set in Settings → bing_api_key)"}
        ), 400
    from tools.bing_webmaster import site_overview

    return jsonify(site_overview(site_url, api_key, period=period))


@bp.route("/api/tools/bing/inspect", methods=["POST"])
@login_required
def api_bing_inspect():
    """Inspect a specific URL via Bing Webmaster API."""
    data = request.get_json(force=True) or {}
    page_url = _norm_url((data.get("url") or "").strip())
    site_url = _norm_url((data.get("site_url") or "").strip())
    api_key = (data.get("api_key") or CFG.get("bing_api_key", "")).strip()
    if not page_url or not site_url:
        return jsonify({"ok": False, "error": "url and site_url required"}), 400
    if (rej := _reject_unsafe(page_url)):
        return rej
    if (rej := _require_public_url(site_url, "site_url"))[1]:
        return rej[1]
    if not api_key:
        return jsonify({"ok": False, "error": "Bing API key required"}), 400
    from tools.bing_webmaster import inspect_url

    return jsonify(inspect_url(page_url, site_url, api_key))


@bp.route("/api/tools/bing/submit", methods=["POST"])
@login_required
def api_bing_submit():
    """Submit a URL to Bing for crawling."""
    data = request.get_json(force=True) or {}
    page_url = _norm_url((data.get("url") or "").strip())
    site_url = _norm_url((data.get("site_url") or "").strip())
    api_key = (data.get("api_key") or CFG.get("bing_api_key", "")).strip()
    if not page_url or not site_url:
        return jsonify({"ok": False, "error": "url and site_url required"}), 400
    if (rej := _reject_unsafe(page_url)):
        return rej
    if (rej := _require_public_url(site_url, "site_url"))[1]:
        return rej[1]
    if not api_key:
        return jsonify({"ok": False, "error": "Bing API key required"}), 400
    from tools.bing_webmaster import submit_url

    return jsonify(submit_url(page_url, site_url, api_key))


# ─── GSC opportunities + analytics ───────────────────────────────────────────
def _gsc_service_or_error():
    """Return (service, None) on success, or (None, (response, status)) on failure."""
    gsc_cfg = CFG.get("gsc", {})
    if not gsc_cfg.get("enabled"):
        return None, (
            jsonify(
                {
                    "ok": False,
                    "error": "Google Search Console not enabled — go to Settings → GSC",
                }
            ),
            400,
        )
    try:
        return build_gsc_service(), None
    except Exception as exc:
        return None, (jsonify({"ok": False, "error": f"GSC auth error: {exc}"}), 400)


@bp.route("/api/tools/gsc_opportunities", methods=["POST"])
@login_required
def api_gsc_opportunities():
    """Run GSC opportunity analysis: low-CTR pages, position decay, cannibalization."""
    data = request.get_json(force=True) or {}
    site_url = _norm_url((data.get("site_url") or "").strip())
    if not site_url:
        return jsonify({"ok": False, "error": "site_url required"}), 400
    if (rej := _require_public_url(site_url, "site_url"))[1]:
        return rej[1]
    svc, err = _gsc_service_or_error()
    if err:
        return err
    from tools.phase3 import gsc_opportunities

    try:
        return jsonify(gsc_opportunities(svc, site_url))
    except Exception as exc:
        logger.error("gsc_opportunities error: %s", exc, exc_info=True)
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.route("/api/tools/gsc_opp_ai_draft", methods=["POST"])
@login_required
def api_gsc_opp_ai_draft():
    """Fetch live metadata, get top GSC queries, and generate 3 CTR-optimized variants using Groq."""
    data = request.get_json(force=True) or {}
    url = _norm_url((data.get("url") or "").strip())
    site_url = _norm_url((data.get("site_url") or "").strip())

    if not url or not site_url:
        return jsonify({"ok": False, "error": "url and site_url required"}), 400
    if (rej := _reject_unsafe(url)):
        return rej
    if (rej := _require_public_url(site_url, "site_url"))[1]:
        return rej[1]

    gsc_cfg = CFG.get("gsc", {})
    if not gsc_cfg.get("enabled"):
        return jsonify(
            {"ok": False, "error": "Google Search Console not enabled — go to Settings → GSC"}
        ), 400

    groq_api_key = (CFG.get("groq_api_key", "") or os.getenv("GROQ_API_KEY", "")).strip()
    if not groq_api_key:
        return jsonify(
            {
                "ok": False,
                "error": "Groq API key required (Settings → groq_api_key or GROQ_API_KEY env)",
            }
        ), 400

    # 1. Fetch live page HTML and parse Title and Meta Description.
    from bs4 import BeautifulSoup

    from tools._common import fetch_html

    current_title = ""
    current_desc = ""
    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            )
        }
        resp = fetch_html(url, headers=headers)
        soup = BeautifulSoup(resp.text, "lxml")

        title_tag = soup.find("title")
        current_title = title_tag.get_text(strip=True) if title_tag else ""

        desc_tag = (
            soup.find("meta", attrs={"name": "description"})
            or soup.find("meta", attrs={"name": "Description"})
            or soup.find("meta", attrs={"property": "og:description"})
        )
        if desc_tag:
            val = desc_tag.get("content", "")
            if isinstance(val, list | tuple):
                current_desc = " ".join(str(item) for item in val).strip()
            else:
                current_desc = str(val).strip()
    except Exception as e:
        logger.warning("Failed to fetch live metadata for AI Optimizer: %s", e)

    # 2. Get top GSC queries for this URL.
    top_queries_list = []
    try:
        service = build_gsc_service()
        from tools.phase3 import top_queries

        queries_res = top_queries(url, service, site_url, top_n=10)
        if queries_res.get("status") == "pass" and isinstance(queries_res.get("value"), list):
            top_queries_list = [
                q["query"]
                for q in queries_res["value"]
                if isinstance(q, dict) and "query" in q
            ]
    except Exception as e:
        logger.warning("Failed to fetch top GSC queries for AI Optimizer: %s", e)

    # 3. Call Groq AI tag drafting helper.
    from tools.ai_assist import draft_meta

    try:
        res = draft_meta(url, current_title, current_desc, top_queries_list, groq_api_key)
        if not res.get("ok"):
            return jsonify({"ok": False, "error": res.get("error", "AI draft failed")}), 400

        return jsonify(
            {
                "ok": True,
                "url": url,
                "current_title": current_title,
                "current_description": current_desc,
                "top_queries": top_queries_list,
                "variants": res.get("variants", []),
                "model": res.get("model", ""),
            }
        )
    except Exception as exc:
        logger.error("gsc_opp_ai_draft error: %s", exc, exc_info=True)
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.route("/api/tools/gsc_position_tracker", methods=["POST"])
@login_required
def api_gsc_position_tracker():
    """Average position trend for a URL over the last 90 days."""
    data = request.get_json(force=True) or {}
    url = _norm_url((data.get("url") or "").strip())
    site_url = _norm_url((data.get("site_url") or "").strip())
    if not url or not site_url:
        return jsonify({"ok": False, "error": "url and site_url required"}), 400
    if (rej := _require_public_url(url, "url"))[1]:
        return rej[1]
    if (rej := _require_public_url(site_url, "site_url"))[1]:
        return rej[1]
    svc, err = _gsc_service_or_error()
    if err:
        return err
    from tools.phase3 import position_tracker

    try:
        return jsonify(position_tracker(url, svc, site_url))
    except Exception as exc:
        logger.error("gsc_position_tracker error: %s", exc, exc_info=True)
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.route("/api/tools/gsc_ctr_analyzer", methods=["POST"])
@login_required
def api_gsc_ctr_analyzer():
    """Find pages with high impressions but low CTR across the whole site."""
    data = request.get_json(force=True) or {}
    site_url = _norm_url((data.get("site_url") or "").strip())
    min_impressions = _int(data, "min_impressions", 100, 0, 1_000_000)
    if not site_url:
        return jsonify({"ok": False, "error": "site_url required"}), 400
    if (rej := _require_public_url(site_url, "site_url"))[1]:
        return rej[1]
    svc, err = _gsc_service_or_error()
    if err:
        return err
    from tools.phase3 import ctr_analyzer

    try:
        return jsonify(ctr_analyzer(svc, site_url, min_impressions=min_impressions))
    except Exception as exc:
        logger.error("gsc_ctr_analyzer error: %s", exc, exc_info=True)
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.route("/api/tools/gsc_coverage_errors", methods=["POST"])
@login_required
def api_gsc_coverage_errors():
    """Fetch coverage errors and indexing gaps from GSC sitemaps."""
    data = request.get_json(force=True) or {}
    site_url = _norm_url((data.get("site_url") or "").strip())
    if not site_url:
        return jsonify({"ok": False, "error": "site_url required"}), 400
    if (rej := _require_public_url(site_url, "site_url"))[1]:
        return rej[1]
    svc, err = _gsc_service_or_error()
    if err:
        return err
    from tools.phase3 import coverage_errors

    try:
        return jsonify(coverage_errors(svc, site_url))
    except Exception as exc:
        logger.error("gsc_coverage_errors error: %s", exc, exc_info=True)
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.route("/api/tools/gsc_sitemaps_status", methods=["POST"])
@login_required
def api_gsc_sitemaps_status():
    """List all sitemaps submitted to GSC with submission and indexing stats."""
    data = request.get_json(force=True) or {}
    site_url = _norm_url((data.get("site_url") or "").strip())
    if not site_url:
        return jsonify({"ok": False, "error": "site_url required"}), 400
    if (rej := _require_public_url(site_url, "site_url"))[1]:
        return rej[1]
    svc, err = _gsc_service_or_error()
    if err:
        return err
    from tools.phase3 import sitemaps_status

    try:
        return jsonify(sitemaps_status(svc, site_url))
    except Exception as exc:
        logger.error("gsc_sitemaps_status error: %s", exc, exc_info=True)
        return jsonify({"ok": False, "error": str(exc)}), 500


# ─── Notifications ───────────────────────────────────────────────────────────
@bp.route("/api/tools/notify_test", methods=["POST"])
@login_required
def api_notify_test():
    """Send a test notification via email, slack, or teams."""
    data = request.get_json(force=True) or {}
    channel = (data.get("channel") or "").strip().lower()
    if channel not in ("email", "slack", "teams"):
        return jsonify({"ok": False, "error": "channel must be email, slack, or teams"}), 400
    from core.notifier import NotificationService

    svc = NotificationService(CFG)
    try:
        if channel == "email":
            svc.send_email(
                "SEO Suite — test notification",
                "<h2>Test OK</h2><p>Your email notification is configured correctly.</p>",
            )
        elif channel == "slack":
            svc.send_slack("SEO Suite test notification: Slack is configured correctly.")
        else:
            svc.send_teams("SEO Suite test notification: Teams is configured correctly.")
        return jsonify({"ok": True, "message": f"Test {channel} sent successfully"})
    except Exception as exc:
        logger.error("notify_test error: %s", exc, exc_info=True)
        return jsonify({"ok": False, "error": str(exc)}), 500


# ─── Performance opportunities ───────────────────────────────────────────────
@bp.route("/api/tools/perf_opportunities", methods=["POST"])
@login_required
def api_perf_opportunities():
    """Run PageSpeed analysis and return prioritised Core Web Vitals fix plan."""
    data = request.get_json(force=True) or {}
    url = _norm_url((data.get("url") or "").strip())
    api_key = (data.get("api_key") or CFG.get("pagespeed_api_key", "")).strip()
    if not url:
        return jsonify({"ok": False, "error": "url required"}), 400
    if (rej := _reject_unsafe(url)):
        return rej
    if not api_key:
        return jsonify(
            {
                "ok": False,
                "error": "PageSpeed API key required (set in Settings → PageSpeed API Key)",
            }
        ), 400
    from tools.phase2 import performance_opportunities

    try:
        return jsonify(performance_opportunities(url, api_key))
    except Exception as exc:
        logger.error("perf_opportunities error: %s", exc, exc_info=True)
        return jsonify({"ok": False, "error": str(exc)}), 500


# ─── Groq AI assistance ──────────────────────────────────────────────────────
@bp.route("/api/tools/ai_explain", methods=["POST"])
@login_required
def api_ai_explain():
    """Explain audit results in plain English using Groq LLM."""
    data = request.get_json(force=True) or {}
    results = data.get("results") or data.get("audit_results") or []
    url = _norm_url((data.get("url") or "").strip())
    api_key = (
        data.get("api_key") or CFG.get("groq_api_key", "") or os.getenv("GROQ_API_KEY", "")
    ).strip()
    if not results:
        return jsonify({"ok": False, "error": "results required"}), 400
    if not api_key:
        return jsonify(
            {
                "ok": False,
                "error": "Groq API key required (Settings → groq_api_key or GROQ_API_KEY env)",
            }
        ), 400
    from tools.ai_assist import explain_audit

    try:
        return jsonify(explain_audit(results, api_key, url=url))
    except Exception as exc:
        logger.error("ai_explain error: %s", exc, exc_info=True)
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.route("/api/tools/ai_draft_meta", methods=["POST"])
@login_required
def api_ai_draft_meta():
    """Draft improved title + meta description variants using Groq LLM."""
    data = request.get_json(force=True) or {}
    url = _norm_url((data.get("url") or "").strip())
    current_title = (data.get("title") or "").strip()
    current_desc = (data.get("description") or "").strip()
    top_queries = data.get("top_queries") or []
    api_key = (
        data.get("api_key") or CFG.get("groq_api_key", "") or os.getenv("GROQ_API_KEY", "")
    ).strip()
    if not url:
        return jsonify({"ok": False, "error": "url required"}), 400
    if (rej := _reject_unsafe(url)):
        return rej
    if not api_key:
        return jsonify(
            {"ok": False, "error": "Groq API key required (Settings → groq_api_key)"}
        ), 400
    from tools.ai_assist import draft_meta

    try:
        return jsonify(draft_meta(url, current_title, current_desc, top_queries, api_key))
    except Exception as exc:
        logger.error("ai_draft_meta error: %s", exc, exc_info=True)
        return jsonify({"ok": False, "error": str(exc)}), 500


# ─── Generators ──────────────────────────────────────────────────────────────
@bp.route("/api/tools/schema_fields/<schema_type>")
@login_required
def api_schema_fields(schema_type):
    from tools.generators import get_schema_fields

    return jsonify(get_schema_fields(schema_type))


@bp.route("/api/tools/schema_generate", methods=["POST"])
@login_required
def api_schema_generate():
    data = request.get_json(force=True) or {}
    schema_type = (data.get("schema_type") or "").strip()
    form_data = data.get("data", {})
    if not schema_type:
        return jsonify({"ok": False, "error": "schema_type required"}), 400
    from tools.generators import generate_schema

    return jsonify(generate_schema(schema_type, form_data))


@bp.route("/api/tools/robots_txt", methods=["POST"])
@login_required
def api_robots_txt():
    data = request.get_json(force=True) or {}
    from tools.generators import generate_robots_txt

    return jsonify(generate_robots_txt(data))


@bp.route("/api/tools/sitemap_generate", methods=["POST"])
@login_required
def api_sitemap_generate():
    data = request.get_json(force=True) or {}
    from tools.generators import generate_sitemap

    return jsonify(generate_sitemap(data))


@bp.route("/api/tools/hreflang_generate", methods=["POST"])
@login_required
def api_hreflang_generate():
    data = request.get_json(force=True) or {}
    from tools.generators import generate_hreflang

    return jsonify(generate_hreflang(data))


@bp.route("/api/tools/meta_tags_generate", methods=["POST"])
@login_required
def api_meta_tags_generate():
    data = request.get_json(force=True) or {}
    from tools.generators import generate_meta_tags

    return jsonify(generate_meta_tags(data))


# ─── Diagnostics ─────────────────────────────────────────────────────────────
@bp.route("/api/tools/robots_tester", methods=["POST"])
@login_required
def api_robots_tester():
    """Fetch and analyse a live robots.txt — parse directives, detect issues, validate rules."""
    data = request.get_json(force=True) or {}
    url = _norm_url((data.get("url") or "").strip())
    if not url:
        return jsonify({"ok": False, "error": "url required"}), 400
    if (rej := _reject_unsafe(url)):
        return rej
    from tools.quick_tools import robots_tester

    return jsonify(robots_tester(url))


@bp.route("/api/tools/hreflang_validate", methods=["POST"])
@login_required
def api_hreflang_validate():
    """Fetch a page, extract hreflang tags, validate them, and check alternate URL reachability."""
    data = request.get_json(force=True) or {}
    url = _norm_url((data.get("url") or "").strip())
    if not url:
        return jsonify({"ok": False, "error": "url required"}), 400
    if (rej := _reject_unsafe(url)):
        return rej
    from tools.quick_tools import hreflang_validator

    return jsonify(hreflang_validator(url))


@bp.route("/api/tools/link_health", methods=["POST"])
@login_required
def api_link_health():
    """Fetch a page and probe every outbound link for broken (4xx/5xx) or redirect status."""
    data = request.get_json(force=True) or {}
    url = _norm_url((data.get("url") or "").strip())
    if not url:
        return jsonify({"ok": False, "error": "url required"}), 400
    if (rej := _reject_unsafe(url)):
        return rej
    from tools.quick_tools import broken_link_checker

    return jsonify(broken_link_checker(url))



def register(app) -> None:
    app.register_blueprint(bp)
