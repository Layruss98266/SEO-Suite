"""Single-use-case runner routes — ``/api/usecase/*``.

Runs a single audit use case (e.g. ``crawlability``, ``on_page``,
``performance``) against either:

* a single URL,
* the first URL of a sitemap or domain crawl,
* or up to 20 URLs from an uploaded CSV/XLSX (``/run_bulk``).

These are the dashboard's "quick check" buttons — fast feedback for one URL
at a time, vs. the full-audit ``/api/audit/run`` which writes reports to
disk.
"""

from __future__ import annotations

import logging
import re
import tempfile
from pathlib import Path

from flask import Blueprint, jsonify, request

from app.state import CFG, _reject_unsafe
from core.auth import login_required

logger = logging.getLogger(__name__)

bp = Blueprint("runners", __name__)


# ── Helper ────────────────────────────────────────────────────────────────────

def _run_usecase_for_url(url: str, use_case: str, cfg: dict, keywords: str = "") -> dict:
    """Shared logic: run a use case against a single resolved URL."""
    from core.checker import build_gsc_service
    from core.seo_audit import audit_single_url, calc_seo_score

    gsc_service = None
    if cfg.get("gsc", {}).get("enabled"):
        try:
            gsc_service = build_gsc_service()
        except Exception:
            pass

    extra = {"keywords": keywords} if keywords else {}
    audit = audit_single_url(
        url, cfg, gsc_service=gsc_service, use_cases=[use_case], **extra
    )
    checks = audit.get("results", []) if isinstance(audit, dict) else list(audit)
    score = (
        audit.get("score", calc_seo_score(checks))
        if isinstance(audit, dict)
        else calc_seo_score(checks)
    )
    from tools.issue_scoring import score_issues

    payload = {
        "ok": True,
        "url": url,
        "use_case": use_case,
        "score": score,
        "passes": sum(1 for r in checks if r.get("status") == "pass"),
        "warnings": sum(1 for r in checks if r.get("status") == "warning"),
        "fails": sum(1 for r in checks if r.get("status") == "fail"),
        "results": checks,
    }
    # Annotate with impact/effort/priority so the SPA can render a
    # "fix-next" panel without re-implementing scoring client-side.
    scored = score_issues(payload)
    payload["scored_issues"] = scored.get("scored_issues", [])
    payload["summary"] = scored.get("summary", {})
    return payload


# ── Routes ────────────────────────────────────────────────────────────────────
@bp.route("/api/usecase/run", methods=["POST"])
@login_required
def api_usecase_run():
    """Run a single use case. Supports ``input_format``: url | domain | sitemap."""
    data = request.get_json(force=True) or {}
    raw_url = (data.get("url") or "").strip()
    use_case = (data.get("use_case") or "").strip()
    input_format = (data.get("input_format") or "url").strip()
    keywords = (data.get("keywords") or "").strip()

    if not raw_url:
        return jsonify({"ok": False, "error": "url required"}), 400
    if not use_case:
        return jsonify({"ok": False, "error": "use_case required"}), 400
    # Normalize scheme so bare domains like "example.com" work end-to-end.
    if raw_url and not raw_url.startswith("http"):
        raw_url = f"https://{raw_url}"
    if (rej := _reject_unsafe(raw_url)):
        return rej

    from core.checker import fetch_from_domain, fetch_sitemap_urls
    from core.seo_audit import USE_CASES

    if use_case not in USE_CASES:
        return jsonify({"ok": False, "error": f"Unknown use_case: {use_case}"}), 400

    try:
        if input_format == "sitemap":
            urls = fetch_sitemap_urls(raw_url)[:1]
            if not urls:
                return jsonify(
                    {
                        "ok": False,
                        "error": "Sitemap returned no valid URLs — check the URL and try again",
                    }
                ), 400
            target = urls[0]
        elif input_format == "domain":
            urls = fetch_from_domain(raw_url)[:1]
            if not urls:
                return jsonify(
                    {
                        "ok": False,
                        "error": "No crawlable URLs found for this domain — check the URL and try again",
                    }
                ), 400
            target = urls[0]
        else:
            target = raw_url

        return jsonify(_run_usecase_for_url(target, use_case, CFG, keywords))
    except Exception as e:
        logger.error("usecase/run error: %s", e, exc_info=True)
        return jsonify({"ok": False, "error": "An internal error occurred"}), 500


@bp.route("/api/usecase/run_bulk", methods=["POST"])
@login_required
def api_usecase_run_bulk():
    """Run a use case against all URLs from an uploaded CSV/XLSX (max 20 URLs)."""
    use_case = (request.form.get("use_case") or "").strip()
    keywords = (request.form.get("keywords") or "").strip()
    f = request.files.get("file")

    if not f or not f.filename:
        return jsonify({"ok": False, "error": "file required"}), 400
    if not re.search(r"\.(csv|xlsx)$", f.filename, re.IGNORECASE):
        return jsonify({"ok": False, "error": "Only .csv or .xlsx accepted"}), 400

    from core.seo_audit import USE_CASES

    if use_case not in USE_CASES:
        return jsonify({"ok": False, "error": f"Unknown use_case: {use_case}"}), 400

    try:
        suffix = ".csv" if f.filename.lower().endswith(".csv") else ".xlsx"
        tmp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                f.save(tmp.name)
                tmp_path = Path(tmp.name)
            from core.checker import load_from_csv_excel

            urls = load_from_csv_excel(tmp_path)[:20]
        finally:
            if tmp_path is not None:
                tmp_path.unlink(missing_ok=True)

        if not urls:
            return jsonify({"ok": False, "error": "No valid URLs found in file"}), 400

        all_results = []
        for u in urls:
            try:
                all_results.append(_run_usecase_for_url(u, use_case, CFG, keywords))
            except Exception as ue:
                all_results.append({"ok": False, "url": u, "error": str(ue)})

        # Aggregate: return summary + per-URL breakdown.
        ok_results = [r for r in all_results if r.get("ok")]
        avg_score = (
            round(sum(r["score"] for r in ok_results) / len(ok_results))
            if ok_results
            else 0
        )
        # Merge checks (first URL's checks for display, summary stats across all).
        first = ok_results[0] if ok_results else {}
        return jsonify(
            {
                "ok": True,
                "url": f"{len(urls)} URLs",
                "use_case": use_case,
                "score": avg_score,
                "passes": sum(r.get("passes", 0) for r in ok_results),
                "warnings": sum(r.get("warnings", 0) for r in ok_results),
                "fails": sum(r.get("fails", 0) for r in ok_results),
                "results": first.get("results", []),
                "bulk": all_results,
            }
        )
    except Exception as e:
        logger.error("usecase/run_bulk error: %s", e, exc_info=True)
        return jsonify({"ok": False, "error": "An internal error occurred"}), 500


def register(app) -> None:
    app.register_blueprint(bp)
