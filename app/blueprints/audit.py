"""Audit routes — ``/api/audit/*``.

Owns the SEO audit workflow: run/cancel/pause/resume, the long-lived SSE
progress stream, the live partial-CSV export for the dashboard's "running
audit" view, the partial HTML/XLSX report saved on cancellation, and the
single-phase runner used by the dashboard's individual-phase buttons.

Concurrency:
* At most one audit run at a time (``_lock`` + ``_audit_status["running"]``).
* Per-URL work is parallel via a ``ThreadPoolExecutor`` whose size is
  controlled by the request's ``workers`` field (clamped 1-8).
* Cancellation flags are checked twice per URL — once before submit and once
  before result accumulation — so an in-flight task can be skipped.
"""

from __future__ import annotations

import csv as _csv
import io as _io
import json
import logging
import queue
import threading
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import as_completed as _ac
from datetime import datetime
from urllib.parse import urlparse

from flask import Blueprint, Response, jsonify, request

from app.metrics import record_audit_event
from app.state import (
    CFG,
    MAX_AUDIT_RESULTS,
    REPORTS_DIR,
    _audit_cancel,
    _audit_full_results,
    _audit_partial,
    _audit_paused,
    _audit_queue,
    _audit_status,
    _audit_subscribers,
    _broadcast_audit,
    _int,
    _lock,
    _norm_url,
    _reject_unsafe,
    _safe_public_url_list,
    _safe_upload_path,
    _subscribe,
    _unsubscribe,
)
from core.auth import login_required
from core.checker import (
    build_gsc_service,
    crawl_site,
    fetch_from_domain,
    fetch_sitemap_urls,
    filter_urls,
    load_config,
    load_from_csv_excel,
)
from core.security import is_safe_url
from core.seo_audit import audit_single_url, generate_excel_report, generate_html_report

logger = logging.getLogger(__name__)

bp = Blueprint("audit", __name__)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _save_partial_audit_report() -> tuple[str, str]:
    """Save a partial audit HTML+Excel from full results collected so far.

    Returns ``(html_filename, xlsx_filename)`` — empty strings on
    failure / no data.
    """
    with _lock:
        snapshot = list(_audit_full_results)
    if not snapshot:
        return "", ""
    try:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        stem = f"seo_audit_{ts}_partial"
        html_path = REPORTS_DIR / f"{stem}.html"
        excel_path = REPORTS_DIR / f"{stem}.xlsx"
        json_path = REPORTS_DIR / f"{stem}.json"
        html_path.write_text(generate_html_report(snapshot, [], ts), encoding="utf-8")
        xlsx_ok = False
        try:
            generate_excel_report(snapshot, excel_path)
            xlsx_ok = True
        except Exception as _xe:
            logger.warning("Partial Excel report failed (non-fatal): %s", _xe)
        try:
            sidecar = {
                "avg_score": round(sum(a["score"] for a in snapshot) / len(snapshot)),
                "total_issues": sum(len(a.get("issues", [])) for a in snapshot),
                "total_warnings": sum(len(a.get("warnings", [])) for a in snapshot),
                "urls": len(snapshot),
            }
            json_path.write_text(json.dumps(sidecar), encoding="utf-8")
        except Exception:
            pass
        return html_path.name, (excel_path.name if xlsx_ok else "")
    except Exception as exc:
        logger.warning("Partial audit report save failed: %s", exc)
        return "", ""


# ── Run ───────────────────────────────────────────────────────────────────────
@bp.route("/api/audit/run", methods=["POST"])
@login_required
def api_audit_run():
    with _lock:
        running = _audit_status.get("running", False)
    if running:
        return jsonify({"error": "Already running"}), 400

    try:
        data = request.get_json(force=True) or {}
    except Exception:
        return jsonify({"error": "Invalid JSON in request body"}), 400

    input_type = data.get("input_type", "sitemap")
    raw = data.get("input", "").strip()
    if not raw:
        return jsonify({"error": "No URL or sitemap provided"}), 400
    if input_type in ("sitemap", "domain", "crawl"):
        raw = _norm_url(raw)
        ok, reason = is_safe_url(raw)
        if not ok:
            return jsonify({"error": f"URL refused: {reason}"}), 400
    pattern = data.get("pattern", "")
    limit = _int(data, "limit", 10, 1, 500)
    keywords = data.get("keywords", [])
    use_cases = data.get("use_cases", None)
    tasks = data.get("tasks", None)
    workers = _int(data, "workers", 3, 1, 8)

    estimated_total = limit
    # Clear partial buffers and cancel event BEFORE flipping running=True, all
    # inside the lock. Previously _audit_cancel.clear() ran before the lock,
    # so a 400 early-return (already running) would silently clear the cancel
    # event for the active run, preventing it from being cancelled.
    with _lock:
        if _audit_status["running"]:
            return jsonify({"error": "Already running"}), 400
        _audit_partial.clear()
        _audit_full_results.clear()
        _audit_cancel.clear()
        _audit_status.update({"running": True, "total": estimated_total, "done": 0})
    _audit_paused.set()

    current_cfg = load_config()
    cfg_with_kw = {**current_cfg, "track_keywords": keywords}

    def run():
        try:
            # Fetch URLs inside the thread — keeps the HTTP response fast.
            if input_type == "sitemap":
                urls = fetch_sitemap_urls(raw)
            elif input_type == "domain":
                urls = fetch_from_domain(raw)
            elif input_type == "crawl":
                urls = crawl_site(
                    raw,
                    max_pages=limit,
                    max_depth=_int(data, "crawl_depth", 2, 1, 20),
                )
            elif input_type in ("paste", "list"):
                urls = _safe_public_url_list(raw)
            else:  # csv / xlsx — raw is the uploaded file path
                safe = _safe_upload_path(raw)
                if safe is None:
                    _audit_queue.put(
                        {
                            "type": "error",
                            "message": "CSV path must point to an uploaded file in data/uploads/",
                        }
                    )
                    return
                urls = load_from_csv_excel(str(safe))

            urls = filter_urls(urls, pattern)[:limit]
            if not urls:
                _audit_queue.put(
                    {
                        "type": "error",
                        "message": "No URLs found — check your sitemap URL or filter pattern",
                    }
                )
                return

            with _lock:
                _audit_status["total"] = len(urls)

            from tools.phase3 import audit_site as p3_site

            gsc_service = (
                build_gsc_service() if current_cfg.get("gsc", {}).get("enabled") else None
            )
            audits = []
            p3_site_data = []

            if gsc_service and urls:
                _p = urlparse(urls[0])
                site_url = f"{_p.scheme}://{_p.netloc}/" if _p.netloc else ""
                p3_site_data = p3_site(gsc_service, site_url, urls[:5])

            i_counter = {"n": 0}

            def _audit_one(u):
                if _audit_cancel.is_set():
                    return None
                _audit_paused.wait()
                if _audit_cancel.is_set():
                    return None
                return audit_single_url(
                    u, cfg_with_kw, gsc_service, use_cases=use_cases, tasks=tasks
                )

            with ThreadPoolExecutor(max_workers=workers) as _ex:
                fut_to_url = {_ex.submit(_audit_one, u): u for u in urls}
                for fut in _ac(fut_to_url):
                    if _audit_cancel.is_set():
                        _ex.shutdown(wait=False, cancel_futures=True)
                        break
                    url = fut_to_url[fut]
                    try:
                        audit = fut.result()
                    except Exception as ex:
                        logger.error("audit error %s: %s", url, ex)
                        audit = None
                    if audit is None:
                        continue
                    audits.append(audit)
                    with _lock:
                        # Bounded live state — past MAX_AUDIT_RESULTS new
                        # entries stop accumulating to keep memory flat on
                        # huge sitemaps.
                        if len(_audit_partial) < MAX_AUDIT_RESULTS:
                            _audit_partial.append(
                                {
                                    "url": url,
                                    "score": audit.get("score", 0),
                                    "issues": len(audit.get("issues", [])),
                                    "warnings": len(audit.get("warnings", [])),
                                }
                            )
                        if len(_audit_full_results) < MAX_AUDIT_RESULTS:
                            _audit_full_results.append(audit)
                    i_counter["n"] += 1
                    i = i_counter["n"]
                    # Slim per-result payload — drawer needs tool/status/message/value.
                    slim_results = [
                        {
                            "tool": r.get("tool"),
                            "status": r.get("status"),
                            "message": r.get("message", ""),
                            "value": r.get("value"),
                            "details": r.get("details") or {},
                        }
                        for r in audit.get("results", [])
                    ]
                    _audit_queue.put(
                        {
                            "type": "progress",
                            "num": i,
                            "total": len(urls),
                            "url": url,
                            "score": audit.get("score", 0),
                            "issues": len(audit.get("issues", [])),
                            "warnings": len(audit.get("warnings", [])),
                            "results": slim_results,
                            "counts": audit.get("counts", {}),
                        }
                    )
                    with _lock:
                        _audit_status["done"] = i

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            html_path = REPORTS_DIR / f"seo_audit_{timestamp}.html"
            excel_path = REPORTS_DIR / f"seo_audit_{timestamp}.xlsx"
            _json_path = REPORTS_DIR / f"seo_audit_{timestamp}.json"

            # Write HTML first — it is the primary file. JSON and Excel are
            # companions; they must not be written before HTML so a crash
            # between writes cannot leave orphaned sidecars without a matching
            # HTML.
            html_content = generate_html_report(audits, p3_site_data, timestamp)
            html_path.write_text(html_content, encoding="utf-8")

            xlsx_ok = False
            try:
                generate_excel_report(audits, excel_path)
                xlsx_ok = True
            except Exception as _xe:
                logger.error("Excel report failed (non-fatal): %s", _xe)

            try:
                _sidecar = {
                    "avg_score": round(sum(a["score"] for a in audits) / len(audits))
                    if audits
                    else 0,
                    "total_issues": sum(len(a.get("issues", [])) for a in audits),
                    "total_warnings": sum(len(a.get("warnings", [])) for a in audits),
                    "urls": len(audits),
                }
                _json_path.write_text(json.dumps(_sidecar), encoding="utf-8")
            except Exception as _je:
                logger.warning("JSON sidecar write failed: %s", _je)

            _audit_queue.put(
                {
                    "type": "done",
                    "report": str(html_path),
                    "xlsx": str(excel_path) if xlsx_ok else "",
                }
            )
            record_audit_event("completed")
        except Exception as e:
            logger.error("Audit thread error: %s", e, exc_info=True)
            _audit_queue.put({"type": "error", "message": str(e)})
            record_audit_event("error")
        finally:
            with _lock:
                _audit_status["running"] = False

    record_audit_event("started")
    threading.Thread(target=run, daemon=True).start()
    return jsonify({"total": estimated_total, "started": True, "workers": workers})


# ── SSE stream ────────────────────────────────────────────────────────────────
@bp.route("/api/audit/stream")
@login_required
def api_audit_stream():
    """Long-lived SSE stream of audit progress (rate-limit-exempt via register)."""
    sub = _subscribe(_audit_subscribers)
    if sub is None:
        return jsonify({"error": "Too many concurrent SSE connections"}), 503

    def gen():
        try:
            while True:
                try:
                    msg = sub.get(timeout=30)
                    yield f"data: {json.dumps(msg)}\n\n"
                    if msg.get("type") in ("done", "error", "cancelled"):
                        break
                except queue.Empty:
                    yield 'data: {"type":"ping"}\n\n'
        finally:
            _unsubscribe(_audit_subscribers, sub)

    return Response(
        gen(),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── Cancel / pause / resume / partial ─────────────────────────────────────────
@bp.route("/api/audit/cancel", methods=["POST"])
@login_required
def api_audit_cancel():
    _audit_cancel.set()
    _audit_paused.set()  # unblock thread so it can see the cancel flag
    html_name, xlsx_name = _save_partial_audit_report()
    with _lock:
        done = _audit_status.get("done", 0)
    _broadcast_audit(
        {
            "type": "cancelled",
            "report": html_name,
            "xlsx": xlsx_name,
            "done": done,
        }
    )
    record_audit_event("cancelled")
    return jsonify({"cancelled": True})


@bp.route("/api/audit/pause", methods=["POST"])
@login_required
def api_audit_pause():
    with _lock:
        running = _audit_status.get("running", False)
    if not running:
        return jsonify({"error": "Not running"}), 400
    _audit_paused.clear()
    _audit_queue.put({"type": "paused"})
    return jsonify({"paused": True})


@bp.route("/api/audit/resume", methods=["POST"])
@login_required
def api_audit_resume():
    _audit_paused.set()
    _audit_queue.put({"type": "resumed"})
    return jsonify({"resumed": True})


@bp.route("/api/audit/partial")
@login_required
def api_audit_partial():
    """Return completed-so-far audit results as CSV for mid-run export."""
    with _lock:
        rows = list(_audit_partial)
    if not rows:
        return jsonify({"error": "No results yet"}), 404
    buf = _io.StringIO()
    w = _csv.writer(buf)
    header = ["URL", "Score", "Issues", "Warnings"]
    w.writerow(header)
    for r in rows:
        # Pad short rows so a cancelled/partial run can't emit a ragged CSV
        # that misaligns columns in Excel/pandas (AUDIT_LOG C9).
        row = [r.get("url", ""), r.get("score", ""), r.get("issues", ""), r.get("warnings", "")]
        if len(row) < len(header):
            row = row + [""] * (len(header) - len(row))
        w.writerow(row)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return buf.getvalue(), 200, {
        "Content-Type": "text/csv",
        "Content-Disposition": f"attachment; filename=audit_partial_{ts}.csv",
    }


# ── Single-phase runner ───────────────────────────────────────────────────────
@bp.route("/api/audit/phase/<int:phase_num>", methods=["POST"])
@login_required
def api_audit_single_phase(phase_num: int):
    """Run a single audit phase (1-4) against a URL and return results immediately."""
    if phase_num not in (1, 2, 3, 4):
        return jsonify({"ok": False, "error": "phase must be 1, 2, 3, or 4"}), 400
    data = request.get_json(force=True) or {}
    url = _norm_url((data.get("url") or "").strip())
    if not url:
        return jsonify({"ok": False, "error": "url required"}), 400
    if (rej := _reject_unsafe(url)):
        return rej

    results = []
    try:
        if phase_num == 1:
            from tools.phase1 import (
                broken_link_check,
                canonical_check,
                heading_check,
                http_status_check,
                image_alt_check,
                internal_links_check,
                meta_description_check,
                redirect_check,
                robots_check,
                schema_check,
                sitemap_validate,
                title_check,
                word_count_check,
            )

            fns = [
                robots_check,
                http_status_check,
                redirect_check,
                canonical_check,
                title_check,
                meta_description_check,
                heading_check,
                image_alt_check,
                word_count_check,
                broken_link_check,
                internal_links_check,
                sitemap_validate,
                schema_check,
            ]
            with ThreadPoolExecutor(max_workers=6) as ex:
                futs = [ex.submit(fn, url) for fn in fns]
                results = [f.result() for f in futs]

        elif phase_num == 2:
            api_key = CFG.get("pagespeed_api_key", "")
            if not api_key:
                return jsonify(
                    {
                        "ok": False,
                        "error": "PageSpeed API key not set — go to Settings → Performance",
                    }
                ), 400
            from tools.phase2 import audit_url as p2_audit

            results = p2_audit(url, api_key=api_key)

        elif phase_num == 3:
            gsc_cfg = CFG.get("gsc", {})
            if not gsc_cfg.get("enabled"):
                return jsonify(
                    {
                        "ok": False,
                        "error": "GSC not enabled — go to Settings → Indexing & Crawling",
                    }
                ), 400
            svc = build_gsc_service()
            parsed = urlparse(url)
            site_url = f"{parsed.scheme}://{parsed.netloc}/"

            from tools.phase3 import (
                clicks_impressions,
                coverage_errors,
                ctr_analyzer,
                position_tracker,
                sitemaps_status,
                top_queries,
            )

            fns = [
                lambda: clicks_impressions(url, svc, site_url),
                lambda: top_queries(url, svc, site_url),
                lambda: position_tracker(url, svc, site_url),
                lambda: ctr_analyzer(svc, site_url),
                lambda: coverage_errors(svc, site_url),
                lambda: sitemaps_status(svc, site_url),
            ]
            with ThreadPoolExecutor(max_workers=3) as ex:
                results = [f.result() for f in [ex.submit(fn) for fn in fns]]

        elif phase_num == 4:
            from tools.phase4 import backlink_check, domain_authority, keyword_rank_tracker

            fns = []
            dfs_login = CFG.get("dataforseo_login", "")
            dfs_pass = CFG.get("dataforseo_password", "")
            moz_id = CFG.get("moz_access_id", "")
            moz_sec = CFG.get("moz_secret_key", "")
            keywords = data.get("keywords") or CFG.get("track_keywords", [])
            if dfs_login or moz_id:
                fns.append(
                    lambda: backlink_check(
                        url,
                        dataforseo_login=dfs_login,
                        dataforseo_password=dfs_pass,
                    )
                )
            if moz_id:
                fns.append(lambda: domain_authority(url, moz_id, moz_sec))
            serpapi_key = CFG.get("serpapi_key", "")
            if keywords and (serpapi_key or dfs_login):
                fns.append(
                    lambda: keyword_rank_tracker(
                        url,
                        keywords,
                        serpapi_key=serpapi_key,
                        dataforseo_login=dfs_login,
                        dataforseo_password=dfs_pass,
                    )
                )
            if not fns:
                return jsonify(
                    {
                        "ok": False,
                        "error": "Phase 4 requires at least one of: DataForSEO, Moz, or SerpAPI credentials",
                    }
                ), 400
            with ThreadPoolExecutor(max_workers=min(len(fns), 8)) as ex:
                results = [f.result() for f in [ex.submit(fn) for fn in fns]]

        from core.seo_audit import calc_seo_score

        score = calc_seo_score(results)
        issues = [r for r in results if r.get("status") in ("fail", "error")]
        warnings = [r for r in results if r.get("status") == "warning"]
        passed = [r for r in results if r.get("status") == "pass"]
        return jsonify(
            {
                "ok": True,
                "url": url,
                "phase": phase_num,
                "score": score,
                "results": results,
                "counts": {
                    "pass": len(passed),
                    "warning": len(warnings),
                    "fail": len(issues),
                },
            }
        )

    except Exception as exc:
        logger.error("audit_phase_%d error: %s", phase_num, exc, exc_info=True)
        return jsonify({"ok": False, "error": "An internal error occurred"}), 500


__all__ = ["bp", "register", "_save_partial_audit_report"]


def register(app, limiter) -> None:
    """Register the blueprint and rate-limit / exempt routes appropriately."""
    app.register_blueprint(bp)
    limiter.limit("10 per hour")(app.view_functions["audit.api_audit_run"])
    limiter.exempt(app.view_functions["audit.api_audit_stream"])
