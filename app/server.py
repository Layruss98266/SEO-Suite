"""
SEO Suite — Flask app construction and all HTTP routes.

This module owns the Flask ``app`` instance, every ``@app.route`` handler, and
the rate limiter. Shared in-process state (SSE queues, run status, locks) and
the path/helper utilities live in :mod:`app.state`. Cross-cutting middleware
(security headers, CSRF, error handlers) lives in :mod:`app.middleware`.

``main.py`` imports ``app`` from here directly; ``app/__init__.create_app`` is
a thin factory that returns this same configured app for WSGI deployment.

A future incremental refactor will extract route groups into Flask blueprints
under ``app/blueprints/``. The state/middleware split here is the prerequisite
that makes that mechanical — every helper a route needs is already importable
from a small module instead of being tangled in this file.
"""

import json
import logging
import os
import queue
import re
import threading
from datetime import datetime
from urllib.parse import urlparse

from flask import Flask, Response, jsonify, request, session
from flask_cors import CORS
from werkzeug.utils import secure_filename

from app import state
from app.middleware import init_middleware
from app.state import (
    _broadcast_audit,
    _broadcast_index,
    CFG,
    CONFIG_PATH,
    DATA_DIR,
    ERROR_PREFIXES,
    ERROR_STATUSES,
    MAX_AUDIT_RESULTS,
    PROFILES_PATH,
    PROJECT_ROOT,
    REPORTS_DIR,
    STATIC_DIR,
    TEMPLATE_DIR,
    UPLOAD_DIR,
    _REPORT_STEM_RE,
    _audit_cancel,
    _audit_full_results,
    _audit_partial,
    _audit_paused,
    _audit_queue,
    _audit_status,
    _audit_subscribers,
    _cleanup_subscribers,
    _index_cancel,
    _index_paused,
    _index_queue,
    _index_status,
    _index_subscribers,
    _int,
    _last_index_run,
    _lock,
    _norm_url,
    _pdf_semaphore,
    _reject_unsafe,
    _replace_last_index_run,
    _require_public_url,
    _reset_last_index_run,
    _safe_public_url_list,
    _safe_report_path,
    _safe_upload_path,
    _sanitize_csv,
    _snapshot_last_index_run,
    _sub_lock,
    _subscribe,
    _unsubscribe,
    _update_last_index_run,
)

# Note: ``_audit_status``, ``_index_status``, and ``CFG`` are imported directly
# (not via ``state.X``) because routes only ever MUTATE them in place
# (``.update(...)``, ``.clear()``+``.update(...)``). Mutation preserves the
# dict identity, so all importers — including tests that monkey-patch
# ``server._audit_status`` — see the same object.
from core.auth import init_auth, login_required
from core.checker import (
    build_gsc_service,
    crawl_site,
    execute_and_save,
    fetch_from_domain,
    fetch_sitemap_urls,
    filter_urls,
    find_latest_report,
    load_config,
    load_from_csv_excel,
)
from core.security import is_safe_url, validate_public_url
from core.seo_audit import audit_single_url, generate_excel_report, generate_html_report

# ── Logging ───────────────────────────────────────────────────────────────────
# File logging is best-effort: on a read-only filesystem (e.g. a serverless
# host) the FileHandler is skipped so import never crashes. Stream logging
# always works and is what container/PaaS log collectors read anyway.
_log_handlers: list[logging.Handler] = [logging.StreamHandler()]
try:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    _log_handlers.insert(0, logging.FileHandler(DATA_DIR / "app.log", encoding="utf-8"))
except OSError:
    pass  # read-only FS — stream logging only
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=_log_handlers,
)
logger = logging.getLogger(__name__)

# ── App construction ──────────────────────────────────────────────────────────
app = Flask(__name__, template_folder=str(TEMPLATE_DIR), static_folder=str(STATIC_DIR))
init_auth(app)

# CORS origins are env-configurable so production deployments don't need a code
# change. Default is 8080 (the canonical port) — set CORS_ALLOWED_ORIGINS if
# you front the app on a different port.
_cors_origins = [
    o.strip()
    for o in os.getenv(
        "CORS_ALLOWED_ORIGINS",
        "http://localhost:8080,http://127.0.0.1:8080",
    ).split(",")
    if o.strip()
]
CORS(app, origins=_cors_origins, supports_credentials=True)
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024  # 10 MB upload cap

# Security headers, CSRF, error handlers, Jinja csrf_token global.
init_middleware(app)

# ── Sentry error tracking (Stage 1-D) ────────────────────────────────────────
# Opt-in: set SENTRY_DSN env var to activate. No-ops silently when absent so
# local / air-gapped installs are unaffected.
_sentry_dsn = os.getenv("SENTRY_DSN", "")
if _sentry_dsn:
    import sentry_sdk
    from sentry_sdk.integrations.flask import FlaskIntegration
    sentry_sdk.init(
        dsn=_sentry_dsn,
        integrations=[FlaskIntegration()],
        traces_sample_rate=0.05,           # capture 5 % of requests for perf
        environment=os.getenv("SEO_SUITE_ENV", "development"),
    )
    logger.info("Sentry error tracking enabled (env=%s)", os.getenv("SEO_SUITE_ENV", "development"))

# ── Rate limiting (Stage 1-B) ─────────────────────────────────────────────────
# In-memory store — no Redis dependency needed for single-server deployments.
# Limits apply per remote IP address.
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["240 per minute"],
    storage_uri="memory://",
)

# Start the SSE subscriber-cleanup thread now that state has been initialised.
threading.Thread(target=_cleanup_subscribers, daemon=True, name="sse-cleanup").start()




# ══════════════════════════════════════════════════════════════════════════════
# BLUEPRINTS — extracted route groups
# ══════════════════════════════════════════════════════════════════════════════
from app.blueprints import auth_views as _auth_bp
from app.blueprints import misc as _misc_bp
from app.blueprints import reports as _reports_bp
from app.blueprints import settings as _settings_bp
from app.blueprints import site as _site_bp

_site_bp.register(app, limiter)
_misc_bp.register(app)
_auth_bp.register(app, limiter)
_reports_bp.register(app)
_settings_bp.register(app, limiter)


@app.route("/api/index/run", methods=["POST"])
@login_required
@limiter.limit("10 per hour")
def api_index_run():
    # Quick reject without holding the lock — final atomic check happens below.
    if _index_status["running"]:
        return jsonify({"error": "Already running"}), 400

    try:
        data = request.get_json(force=True) or {}
    except Exception:
        return jsonify({"error": "Invalid JSON in request body"}), 400

    input_type = data.get("input_type", "sitemap")
    raw        = data.get("input", "").strip()
    if not raw:
        return jsonify({"error": "No URL or sitemap provided"}), 400
    # SSRF guard for URL-bearing input modes. CSV/list inputs are filesystem or
    # multi-URL — those URLs are checked individually downstream by Playwright,
    # which targets google.com (not the user-supplied host).
    if input_type in ("sitemap", "domain"):
        raw = _norm_url(raw)
        ok, reason = is_safe_url(raw)
        if not ok:
            return jsonify({"error": f"URL refused: {reason}"}), 400
    pattern    = data.get("pattern", "")
    # Clamp limit to [1, 500] so a client can't request a 999999-URL run that
    # ties up Playwright workers and disk.
    limit      = _int(data, "limit", 20, 1, 500)
    quiet      = data.get("quiet", False)
    headless   = data.get("headless", False)
    do_compare = data.get("compare", False)

    estimated_total = limit
    # Atomic check+set so a concurrent POST that snuck past the early check
    # can't also flip running=True and spawn a second worker thread.
    with _lock:
        if _index_status["running"]:
            return jsonify({"error": "Already running"}), 400
        _index_status.update({"running": True, "total": estimated_total, "done": 0})

    def run():
        try:
            # Fetch URLs inside the thread — keeps the HTTP response fast
            if input_type == "sitemap":
                urls = fetch_sitemap_urls(raw)
            elif input_type == "domain":
                urls = fetch_from_domain(raw)
            elif input_type == "csv":
                safe = _safe_upload_path(raw)
                if safe is None:
                    _index_queue.put({"type": "error",
                                      "message": "CSV path must point to an uploaded file in data/uploads/"})
                    return
                urls = load_from_csv_excel(str(safe))
            elif input_type in ("paste", "list"):
                # Comma-separated list of URLs pasted by the user.
                # _safe_public_url_list drops anything that fails SSRF check.
                urls = _safe_public_url_list(raw)
            else:  # 'multi' — treat as list of sitemaps OR URLs
                parts = [s.strip() for s in raw.split(",") if s.strip()]
                urls = []
                for p in parts:
                    if p.lower().endswith(".xml") or "sitemap" in p.lower():
                        urls += fetch_sitemap_urls(p)
                    elif p.startswith("http"):
                        urls.append(p)

            urls = filter_urls(urls, pattern)[:limit]
            if not urls:
                _index_queue.put({"type": "error", "message": "No URLs found — check your sitemap URL or filter pattern"})
                return

            with _lock:
                _index_status["total"] = len(urls)
            _reset_last_index_run()

            _index_cancel.clear()
            _index_paused.set()   # ensure not paused at start of run
            prev = find_latest_report() if do_compare else None
            _run_results: dict[str, str] = {}

            def cb(num, total, url, status):
                _index_paused.wait()   # block here while paused
                if _index_cancel.is_set():
                    return
                _run_results[url] = status
                _update_last_index_run(url, status)   # live update for cancel/partial export
                from core.checker import get_crawl_depth, get_priority_score, get_url_type
                _index_queue.put({"type": "progress", "num": num, "total": total, "url": url,
                                  "status": status, "priority": get_priority_score(url),
                                  "depth": get_crawl_depth(url), "url_type": get_url_type(url)})
                with _lock:
                    _index_status["done"] = num

            html = execute_and_save(urls, headless=headless, quiet=quiet,
                                    do_compare=do_compare, prev_report=prev, progress_cb=cb)
            _replace_last_index_run(_run_results)
            error_count = sum(1 for s in _run_results.values() if _is_error_status(s))
            _index_queue.put({"type": "done", "report": str(html), "error_count": error_count})
        except Exception as e:
            logger.error("Indexing thread error: %s", e, exc_info=True)
            _index_queue.put({"type": "error", "message": str(e)})
        finally:
            with _lock:
                _index_status["running"] = False

    threading.Thread(target=run, daemon=True).start()
    return jsonify({"total": estimated_total, "started": True})


def _is_error_status(status: str) -> bool:
    """True if a per-URL status string indicates a failure to verify indexing.
    Covers the exact tokens 'Error', 'Timeout', 'Other' and also 'GSC Error: …'
    and 'Error: …' prefixes returned by the checker on exceptions.
    """
    if not isinstance(status, str):
        return False
    if status in ERROR_STATUSES:
        return True
    return any(status.startswith(prefix) for prefix in ERROR_PREFIXES)


@app.route("/api/index/stream")
@limiter.exempt   # long-lived SSE connection — must not count against the rate cap
@login_required
def api_index_stream():
    sub = _subscribe(_index_subscribers)
    def gen():
        try:
            while True:
                try:
                    msg = sub.get(timeout=30)
                    yield f"data: {json.dumps(msg)}\n\n"
                    if msg.get("type") in ("done", "error", "cancelled"): break
                except queue.Empty:
                    yield 'data: {"type":"ping"}\n\n'
        finally:
            _unsubscribe(_index_subscribers, sub)
    return Response(gen(), mimetype="text/event-stream",
                    headers={"Cache-Control":"no-cache","X-Accel-Buffering":"no"})


# ══════════════════════════════════════════════════════════════════════════════
# ROUTES — SEO Audit
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/api/audit/run", methods=["POST"])
@login_required
@limiter.limit("10 per hour")
def api_audit_run():
    if _audit_status["running"]:
        return jsonify({"error":"Already running"}), 400

    try:
        data = request.get_json(force=True) or {}
    except Exception:
        return jsonify({"error": "Invalid JSON in request body"}), 400

    input_type = data.get("input_type","sitemap")
    raw        = data.get("input","").strip()
    if not raw:
        return jsonify({"error": "No URL or sitemap provided"}), 400
    if input_type in ("sitemap", "domain", "crawl"):
        raw = _norm_url(raw)
        ok, reason = is_safe_url(raw)
        if not ok:
            return jsonify({"error": f"URL refused: {reason}"}), 400
    pattern    = data.get("pattern","")
    limit      = _int(data, "limit", 10, 1, 500)
    keywords   = data.get("keywords",[])
    use_cases  = data.get("use_cases", None)
    tasks      = data.get("tasks", None)
    workers    = _int(data, "workers", 3, 1, 8)  # parallel URL audits

    # Estimate total immediately so the frontend can show a progress bar.
    # URL fetching happens inside the thread so this route returns in <50 ms.
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
    _audit_paused.set()   # ensure not paused at start of new run

    current_cfg = load_config()
    cfg_with_kw = {**current_cfg, "track_keywords": keywords}

    def run():
        try:
            # Fetch URLs inside the thread — keeps the HTTP response fast
            if input_type == "sitemap":
                urls = fetch_sitemap_urls(raw)
            elif input_type == "domain":
                urls = fetch_from_domain(raw)
            elif input_type == "crawl":
                urls = crawl_site(raw, max_pages=limit, max_depth=_int(data, "crawl_depth", 2, 1, 20))
            elif input_type in ("paste", "list"):
                urls = _safe_public_url_list(raw)
            else:  # csv / xlsx — raw is the uploaded file path
                safe = _safe_upload_path(raw)
                if safe is None:
                    _audit_queue.put({"type": "error",
                                      "message": "CSV path must point to an uploaded file in data/uploads/"})
                    return
                urls = load_from_csv_excel(str(safe))

            urls = filter_urls(urls, pattern)[:limit]
            if not urls:
                _audit_queue.put({"type": "error", "message": "No URLs found — check your sitemap URL or filter pattern"})
                return

            with _lock:
                _audit_status["total"] = len(urls)

            from core.seo_audit import generate_excel_report, generate_html_report
            from tools.phase3 import audit_site as p3_site

            gsc_service  = build_gsc_service() if current_cfg.get("gsc", {}).get("enabled") else None
            audits       = []
            p3_site_data = []

            if gsc_service and urls:
                _p           = urlparse(urls[0])
                site_url     = f"{_p.scheme}://{_p.netloc}/" if _p.netloc else ""
                p3_site_data = p3_site(gsc_service, site_url, urls[:5])

            from concurrent.futures import ThreadPoolExecutor
            from concurrent.futures import as_completed as _ac
            i_counter = {"n": 0}
            def _audit_one(u):
                if _audit_cancel.is_set():
                    return None
                _audit_paused.wait()   # block while paused
                if _audit_cancel.is_set():
                    return None
                return audit_single_url(u, cfg_with_kw, gsc_service,
                                        use_cases=use_cases, tasks=tasks)
            with ThreadPoolExecutor(max_workers=workers) as _ex:
                fut_to_url = {_ex.submit(_audit_one, u): u for u in urls}
                for fut in _ac(fut_to_url):
                    if _audit_cancel.is_set():
                        for f in fut_to_url: f.cancel()
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
                        # Bounded live state — past MAX_AUDIT_RESULTS new entries
                        # stop accumulating to keep memory flat on huge sitemaps.
                        if len(_audit_partial) < MAX_AUDIT_RESULTS:
                            _audit_partial.append({
                                "url":      url,
                                "score":    audit.get("score", 0),
                                "issues":   len(audit.get("issues", [])),
                                "warnings": len(audit.get("warnings", [])),
                            })
                        if len(_audit_full_results) < MAX_AUDIT_RESULTS:
                            _audit_full_results.append(audit)
                    i_counter["n"] += 1
                    i = i_counter["n"]
                    # Slim per-result payload — drawer needs tool/status/message/value
                    slim_results = [{"tool": r.get("tool"),
                                     "status": r.get("status"),
                                     "message": r.get("message",""),
                                     "value": r.get("value"),
                                     "details": r.get("details") or {}}
                                    for r in audit.get("results", [])]
                    _audit_queue.put({
                        "type": "progress", "num": i, "total": len(urls), "url": url,
                        "score":    audit.get("score", 0),
                        "issues":   len(audit.get("issues", [])),
                        "warnings": len(audit.get("warnings", [])),
                        "results":  slim_results,
                        "counts":   audit.get("counts", {}),
                    })
                    with _lock:
                        _audit_status["done"] = i

            timestamp  = datetime.now().strftime("%Y%m%d_%H%M%S")
            html_path  = REPORTS_DIR / f"seo_audit_{timestamp}.html"
            excel_path = REPORTS_DIR / f"seo_audit_{timestamp}.xlsx"
            _json_path = REPORTS_DIR / f"seo_audit_{timestamp}.json"

            # Write HTML first — it is the primary file.  JSON and Excel are
            # companions; they must not be written before HTML so a crash between
            # writes cannot leave orphaned sidecars without a matching HTML.
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
                    "avg_score":      round(sum(a["score"] for a in audits) / len(audits)) if audits else 0,
                    "total_issues":   sum(len(a["issues"])   for a in audits),
                    "total_warnings": sum(len(a["warnings"]) for a in audits),
                    "urls":           len(audits),
                }
                _json_path.write_text(json.dumps(_sidecar), encoding="utf-8")
            except Exception as _je:
                logger.warning("JSON sidecar write failed: %s", _je)

            _audit_queue.put({
                "type":  "done",
                "report": str(html_path),
                "xlsx":   str(excel_path) if xlsx_ok else "",
            })
        except Exception as e:
            logger.error("Audit thread error: %s", e, exc_info=True)
            _audit_queue.put({"type": "error", "message": str(e)})
        finally:
            with _lock:
                _audit_status["running"] = False

    threading.Thread(target=run, daemon=True).start()
    return jsonify({"total": estimated_total, "started": True, "workers": workers})

@app.route("/api/audit/stream")
@limiter.exempt   # long-lived SSE connection — must not count against the rate cap
@login_required
def api_audit_stream():
    sub = _subscribe(_audit_subscribers)
    def gen():
        try:
            while True:
                try:
                    msg = sub.get(timeout=30)
                    yield f"data: {json.dumps(msg)}\n\n"
                    if msg.get("type") in ("done", "error", "cancelled"): break
                except queue.Empty:
                    yield 'data: {"type":"ping"}\n\n'
        finally:
            _unsubscribe(_audit_subscribers, sub)
    return Response(gen(), mimetype="text/event-stream",
                    headers={"Cache-Control":"no-cache","X-Accel-Buffering":"no"})


# Reports / history / PDF routes live in app/blueprints/reports.py
# Settings / profiles / upload / compare routes live in app/blueprints/settings.py


# ══════════════════════════════════════════════════════════════════════════════
# ROUTES — Single Use-Case Runner
# ══════════════════════════════════════════════════════════════════════════════

def _run_usecase_for_url(url: str, use_case: str, cfg: dict, keywords: str = "") -> dict:
    """Shared logic: run a use case against a single resolved URL."""
    from core.checker import build_gsc_service
    from core.seo_audit import audit_single_url, calc_seo_score

    gsc_service = None
    if cfg.get("gsc", {}).get("enabled"):
        try: gsc_service = build_gsc_service()
        except Exception: pass

    extra = {"keywords": keywords} if keywords else {}
    audit  = audit_single_url(url, cfg, gsc_service=gsc_service, use_cases=[use_case], **extra)
    checks = audit.get("results", []) if isinstance(audit, dict) else list(audit)
    score  = audit.get("score", calc_seo_score(checks)) if isinstance(audit, dict) else calc_seo_score(checks)
    return {
        "ok": True, "url": url, "use_case": use_case,
        "score": score,
        "passes":   sum(1 for r in checks if r.get("status") == "pass"),
        "warnings": sum(1 for r in checks if r.get("status") == "warning"),
        "fails":    sum(1 for r in checks if r.get("status") == "fail"),
        "results":  checks,
    }


@app.route("/api/usecase/run", methods=["POST"])
@login_required
def api_usecase_run():
    """Run a single use-case. Supports input_format: url | domain | sitemap."""
    data         = request.get_json(force=True) or {}
    raw_url      = (data.get("url") or "").strip()
    use_case     = (data.get("use_case") or "").strip()
    input_format = (data.get("input_format") or "url").strip()
    keywords     = (data.get("keywords") or "").strip()

    if not raw_url:
        return jsonify({"ok": False, "error": "url required"}), 400
    if not use_case:
        return jsonify({"ok": False, "error": "use_case required"}), 400
    # Normalize scheme so bare domains like "example.com" work end-to-end
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
                return jsonify({
                    "ok": False,
                    "error": "Sitemap returned no valid URLs — check the URL and try again",
                }), 400
            target = urls[0]
        elif input_format == "domain":
            urls = fetch_from_domain(raw_url)[:1]
            if not urls:
                return jsonify({
                    "ok": False,
                    "error": "No crawlable URLs found for this domain — check the URL and try again",
                }), 400
            target = urls[0]
        else:
            target = raw_url

        return jsonify(_run_usecase_for_url(target, use_case, CFG, keywords))
    except Exception as e:
        logger.error("usecase/run error: %s", e, exc_info=True)
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/usecase/run_bulk", methods=["POST"])
@login_required
def api_usecase_run_bulk():
    """Run a use-case against all URLs from an uploaded CSV/XLSX (max 20 URLs)."""
    use_case = (request.form.get("use_case") or "").strip()
    keywords = (request.form.get("keywords") or "").strip()
    f        = request.files.get("file")

    if not f or not f.filename:
        return jsonify({"ok": False, "error": "file required"}), 400
    if not re.search(r'\.(csv|xlsx)$', f.filename, re.IGNORECASE):
        return jsonify({"ok": False, "error": "Only .csv or .xlsx accepted"}), 400

    from core.seo_audit import USE_CASES
    if use_case not in USE_CASES:
        return jsonify({"ok": False, "error": f"Unknown use_case: {use_case}"}), 400

    try:
        import tempfile
        suffix = ".csv" if f.filename.lower().endswith(".csv") else ".xlsx"
        tmp_path = None
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

        # Aggregate: return summary + per-url breakdown
        ok_results = [r for r in all_results if r.get("ok")]
        avg_score  = round(sum(r["score"] for r in ok_results) / len(ok_results)) if ok_results else 0
        # Merge checks (first URL's checks for display, summary stats across all)
        first = ok_results[0] if ok_results else {}
        return jsonify({
            "ok": True, "url": f"{len(urls)} URLs", "use_case": use_case,
            "score":    avg_score,
            "passes":   sum(r.get("passes",0)   for r in ok_results),
            "warnings": sum(r.get("warnings",0) for r in ok_results),
            "fails":    sum(r.get("fails",0)     for r in ok_results),
            "results":  first.get("results", []),
            "bulk":     all_results,
        })
    except Exception as e:
        logger.error("usecase/run_bulk error: %s", e, exc_info=True)
        return jsonify({"ok": False, "error": str(e)}), 500


# ══════════════════════════════════════════════════════════════════════════════
# ROUTES — Quick Tools (Phase A)
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/api/tools/serp_preview", methods=["POST"])
@login_required
def api_serp_preview():
    data = request.get_json(force=True) or {}
    url  = _norm_url((data.get("url") or "").strip())
    if not url:
        return jsonify({"ok": False, "error": "url required"}), 400
    if (rej := _reject_unsafe(url)): return rej
    from tools.quick_tools import serp_snippet_preview
    return jsonify(serp_snippet_preview(url))

@app.route("/api/tools/redirect_chain", methods=["POST"])
@login_required
def api_redirect_chain():
    data = request.get_json(force=True) or {}
    url  = _norm_url((data.get("url") or "").strip())
    if not url:
        return jsonify({"ok": False, "error": "url required"}), 400
    if (rej := _reject_unsafe(url)): return rej
    from tools.quick_tools import redirect_chain
    return jsonify(redirect_chain(url))

@app.route("/api/tools/http_headers", methods=["POST"])
@login_required
def api_http_headers():
    data = request.get_json(force=True) or {}
    url  = _norm_url((data.get("url") or "").strip())
    if not url:
        return jsonify({"ok": False, "error": "url required"}), 400
    if (rej := _reject_unsafe(url)): return rej
    from tools.quick_tools import http_headers
    return jsonify(http_headers(url))

@app.route("/api/tools/keyword_density", methods=["POST"])
@login_required
def api_keyword_density():
    data  = request.get_json(force=True) or {}
    url   = _norm_url((data.get("url") or "").strip())
    top_n = _int(data, "top_n", 20, 1, 500)
    if not url:
        return jsonify({"ok": False, "error": "url required"}), 400
    if (rej := _reject_unsafe(url)): return rej
    from tools.quick_tools import keyword_density
    return jsonify(keyword_density(url, top_n=top_n))

@app.route("/api/tools/code_text_ratio", methods=["POST"])
@login_required
def api_code_text_ratio():
    data = request.get_json(force=True) or {}
    url  = _norm_url((data.get("url") or "").strip())
    if not url:
        return jsonify({"ok": False, "error": "url required"}), 400
    if (rej := _reject_unsafe(url)): return rej
    from tools.quick_tools import code_to_text_ratio
    return jsonify(code_to_text_ratio(url))

@app.route("/api/tools/compression", methods=["POST"])
@login_required
def api_compression():
    data = request.get_json(force=True) or {}
    url  = _norm_url((data.get("url") or "").strip())
    if not url:
        return jsonify({"ok": False, "error": "url required"}), 400
    if (rej := _reject_unsafe(url)): return rej
    from tools.quick_tools import compression_headers
    return jsonify(compression_headers(url))


@app.route("/api/tools/indexnow_submit", methods=["POST"])
@login_required
def api_indexnow_submit():
    """Submit one or more URLs to IndexNow (Bing / Yandex).

    Body fields:
      urls   – list of URL strings OR a single URL string  (required)
      key    – IndexNow API key  (falls back to config "indexnow_key")
      host   – hostname that owns the key  (falls back to config "indexnow_host")
    """
    data = request.get_json(force=True) or {}

    # Accept both a list and a newline/comma separated string
    raw_urls = data.get("urls") or data.get("url") or []
    if isinstance(raw_urls, str):
        raw_urls = [u.strip() for u in raw_urls.replace(",", "\n").splitlines() if u.strip()]
    if not raw_urls:
        return jsonify({"ok": False, "error": "urls required"}), 400

    key  = (data.get("key")  or CFG.get("indexnow_key",  "")).strip()
    host = (data.get("host") or CFG.get("indexnow_host", "")).strip()
    if not key:
        return jsonify({"ok": False, "error": "IndexNow API key required (set in Settings → indexnow_key)"}), 400
    if not host:
        return jsonify({"ok": False, "error": "Host required (set in Settings → indexnow_host)"}), 400

    from tools.indexnow import submit_bulk, submit_url
    if len(raw_urls) == 1:
        return jsonify(submit_url(raw_urls[0], key, host))
    return jsonify(submit_bulk(raw_urls, key, host))


@app.route("/api/tools/indexnow_generate_key", methods=["POST"])
@login_required
def api_indexnow_generate_key():
    """Generate a fresh IndexNow API key."""
    from tools.indexnow import generate_key
    return jsonify({"ok": True, "key": generate_key()})


@app.route("/api/tools/sitemap_audit", methods=["POST"])
@login_required
def api_sitemap_audit():
    """Fetch and audit a sitemap — checks structure, duplicates, size, HTTP links."""
    data = request.get_json(force=True) or {}
    url  = _norm_url((data.get("url") or "").strip())
    if not url:
        return jsonify({"ok": False, "error": "url required"}), 400
    if (rej := _reject_unsafe(url)): return rej
    from tools.sitemap_audit import audit_sitemap
    return jsonify(audit_sitemap(url))


@app.route("/api/tools/schema_validate", methods=["POST"])
@login_required
def api_schema_validate():
    """Fetch a URL, extract JSON-LD blocks, validate against Schema.org."""
    data = request.get_json(force=True) or {}
    url  = _norm_url((data.get("url") or "").strip())
    if not url:
        return jsonify({"ok": False, "error": "url required"}), 400
    # schema_validator does its own validate_public_url; we still pre-check so
    # the error shape matches the other tool endpoints.
    if (rej := _reject_unsafe(url)): return rej
    from tools.schema_validator import validate_url
    return jsonify(validate_url(url))


@app.route("/api/tools/keyword_research", methods=["POST"])
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
    limit         = _int(data, "limit", 150, 1, 1000)

    # Credentials come from config (env-overlaid) so callers never need to ship
    # secrets in the request body.
    login    = CFG.get("dataforseo_login", "")
    password = CFG.get("dataforseo_password", "")

    from tools.keyword_research import research_keywords
    return jsonify(research_keywords(
        keywords, login, password,
        location_code=location_code, language_code=language_code,
        limit=limit, mode=mode,
    ))


# ══════════════════════════════════════════════════════════════════════════════
# ROUTES — Stage 3-A: Bing Webmaster
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/api/tools/bing/overview", methods=["POST"])
@login_required
def api_bing_overview():
    """Full Bing Webmaster overview: traffic + crawl stats + sitemap status."""
    data     = request.get_json(force=True) or {}
    site_url = _norm_url((data.get("site_url") or "").strip())
    api_key  = (data.get("api_key")  or CFG.get("bing_api_key", "")).strip()
    period   = _int(data, "period", 2, 1, 3)
    if not site_url:
        return jsonify({"ok": False, "error": "site_url required"}), 400
    if (rej := _require_public_url(site_url, "site_url"))[1]:
        return rej[1]
    if not api_key:
        return jsonify({"ok": False, "error": "Bing API key required (set in Settings → bing_api_key)"}), 400
    from tools.bing_webmaster import site_overview
    return jsonify(site_overview(site_url, api_key, period=period))


@app.route("/api/tools/bing/inspect", methods=["POST"])
@login_required
def api_bing_inspect():
    """Inspect a specific URL via Bing Webmaster API."""
    data     = request.get_json(force=True) or {}
    page_url = _norm_url((data.get("url")      or "").strip())
    site_url = _norm_url((data.get("site_url") or "").strip())
    api_key  = (data.get("api_key")  or CFG.get("bing_api_key", "")).strip()
    if not page_url or not site_url:
        return jsonify({"ok": False, "error": "url and site_url required"}), 400
    if (rej := _reject_unsafe(page_url)):  return rej
    if (rej := _require_public_url(site_url, "site_url"))[1]: return rej[1]
    if not api_key:
        return jsonify({"ok": False, "error": "Bing API key required"}), 400
    from tools.bing_webmaster import inspect_url
    return jsonify(inspect_url(page_url, site_url, api_key))


@app.route("/api/tools/bing/submit", methods=["POST"])
@login_required
def api_bing_submit():
    """Submit a URL to Bing for crawling."""
    data     = request.get_json(force=True) or {}
    page_url = _norm_url((data.get("url")      or "").strip())
    site_url = _norm_url((data.get("site_url") or "").strip())
    api_key  = (data.get("api_key")  or CFG.get("bing_api_key", "")).strip()
    if not page_url or not site_url:
        return jsonify({"ok": False, "error": "url and site_url required"}), 400
    if (rej := _reject_unsafe(page_url)):  return rej
    if (rej := _require_public_url(site_url, "site_url"))[1]: return rej[1]
    if not api_key:
        return jsonify({"ok": False, "error": "Bing API key required"}), 400
    from tools.bing_webmaster import submit_url
    return jsonify(submit_url(page_url, site_url, api_key))


# ══════════════════════════════════════════════════════════════════════════════
# ROUTES — Stage 3-B: GSC Opportunity Layer
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/api/tools/gsc_opportunities", methods=["POST"])
@login_required
def api_gsc_opportunities():
    """Run GSC opportunity analysis: low-CTR pages, position decay, cannibalization."""
    data     = request.get_json(force=True) or {}
    site_url = _norm_url((data.get("site_url") or "").strip())
    if not site_url:
        return jsonify({"ok": False, "error": "site_url required"}), 400
    if (rej := _require_public_url(site_url, "site_url"))[1]: return rej[1]

    gsc_cfg = CFG.get("gsc", {})
    if not gsc_cfg.get("enabled"):
        return jsonify({"ok": False,
                        "error": "Google Search Console not enabled — go to Settings → GSC"}), 400
    try:
        service = build_gsc_service()
    except Exception as exc:
        return jsonify({"ok": False, "error": f"GSC auth error: {exc}"}), 400

    from tools.phase3 import gsc_opportunities
    try:
        return jsonify(gsc_opportunities(service, site_url))
    except Exception as exc:
        logger.error("gsc_opportunities error: %s", exc, exc_info=True)
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.route("/api/tools/gsc_opp_ai_draft", methods=["POST"])
@login_required
def api_gsc_opp_ai_draft():
    """Fetch live metadata, get top GSC queries, and generate 3 CTR-optimized variants using Groq."""
    data     = request.get_json(force=True) or {}
    url      = _norm_url((data.get("url") or "").strip())
    site_url = _norm_url((data.get("site_url") or "").strip())

    if not url or not site_url:
        return jsonify({"ok": False, "error": "url and site_url required"}), 400
    if (rej := _reject_unsafe(url)): return rej
    if (rej := _require_public_url(site_url, "site_url"))[1]: return rej[1]

    # Verify GSC is configured & enabled
    gsc_cfg = CFG.get("gsc", {})
    if not gsc_cfg.get("enabled"):
        return jsonify({"ok": False, "error": "Google Search Console not enabled — go to Settings → GSC"}), 400

    # Verify Groq is configured
    groq_api_key = (CFG.get("groq_api_key", "") or os.getenv("GROQ_API_KEY", "")).strip()
    if not groq_api_key:
        return jsonify({"ok": False, "error": "Groq API key required (Settings → groq_api_key or GROQ_API_KEY env)"}), 400

    # 1. Fetch live page HTML and parse Title and Meta Description
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

    # 2. Get top GSC queries for this URL
    top_queries_list = []
    try:
        service = build_gsc_service()
        from tools.phase3 import top_queries
        queries_res = top_queries(url, service, site_url, top_n=10)
        if queries_res.get("status") == "pass" and isinstance(queries_res.get("value"), list):
            top_queries_list = [q["query"] for q in queries_res["value"] if isinstance(q, dict) and "query" in q]
    except Exception as e:
        logger.warning("Failed to fetch top GSC queries for AI Optimizer: %s", e)

    # 3. Call Groq AI tag drafting helper
    from tools.ai_assist import draft_meta
    try:
        res = draft_meta(url, current_title, current_desc, top_queries_list, groq_api_key)
        if not res.get("ok"):
            return jsonify({"ok": False, "error": res.get("error", "AI draft failed")}), 400

        return jsonify({
            "ok": True,
            "url": url,
            "current_title": current_title,
            "current_description": current_desc,
            "top_queries": top_queries_list,
            "variants": res.get("variants", []),
            "model": res.get("model", "")
        })
    except Exception as exc:
        logger.error("gsc_opp_ai_draft error: %s", exc, exc_info=True)
        return jsonify({"ok": False, "error": str(exc)}), 500



# ══════════════════════════════════════════════════════════════════════════════
# ROUTES — GSC Analytics Tools (position tracker, CTR analyzer, coverage, sitemaps)
# ══════════════════════════════════════════════════════════════════════════════

def _gsc_service_or_error():
    """Return (service, None) or (None, error_response)."""
    gsc_cfg = CFG.get("gsc", {})
    if not gsc_cfg.get("enabled"):
        return None, (jsonify({"ok": False,
                               "error": "Google Search Console not enabled — go to Settings → GSC"}), 400)
    try:
        return build_gsc_service(), None
    except Exception as exc:
        return None, (jsonify({"ok": False, "error": f"GSC auth error: {exc}"}), 400)


@app.route("/api/tools/gsc_position_tracker", methods=["POST"])
@login_required
def api_gsc_position_tracker():
    """Average position trend for a URL over the last 90 days."""
    data = request.get_json(force=True) or {}
    url      = _norm_url((data.get("url")      or "").strip())
    site_url = _norm_url((data.get("site_url") or "").strip())
    if not url or not site_url:
        return jsonify({"ok": False, "error": "url and site_url required"}), 400
    if (rej := _require_public_url(url, "url"))[1]:      return rej[1]
    if (rej := _require_public_url(site_url, "site_url"))[1]: return rej[1]
    svc, err = _gsc_service_or_error()
    if err: return err
    from tools.phase3 import position_tracker
    try:
        return jsonify(position_tracker(url, svc, site_url))
    except Exception as exc:
        logger.error("gsc_position_tracker error: %s", exc, exc_info=True)
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.route("/api/tools/gsc_ctr_analyzer", methods=["POST"])
@login_required
def api_gsc_ctr_analyzer():
    """Find pages with high impressions but low CTR across the whole site."""
    data = request.get_json(force=True) or {}
    site_url        = _norm_url((data.get("site_url") or "").strip())
    min_impressions = _int(data, "min_impressions", 100, 0, 1_000_000)
    if not site_url:
        return jsonify({"ok": False, "error": "site_url required"}), 400
    if (rej := _require_public_url(site_url, "site_url"))[1]: return rej[1]
    svc, err = _gsc_service_or_error()
    if err: return err
    from tools.phase3 import ctr_analyzer
    try:
        return jsonify(ctr_analyzer(svc, site_url, min_impressions=min_impressions))
    except Exception as exc:
        logger.error("gsc_ctr_analyzer error: %s", exc, exc_info=True)
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.route("/api/tools/gsc_coverage_errors", methods=["POST"])
@login_required
def api_gsc_coverage_errors():
    """Fetch coverage errors and indexing gaps from GSC sitemaps."""
    data = request.get_json(force=True) or {}
    site_url = _norm_url((data.get("site_url") or "").strip())
    if not site_url:
        return jsonify({"ok": False, "error": "site_url required"}), 400
    if (rej := _require_public_url(site_url, "site_url"))[1]: return rej[1]
    svc, err = _gsc_service_or_error()
    if err: return err
    from tools.phase3 import coverage_errors
    try:
        return jsonify(coverage_errors(svc, site_url))
    except Exception as exc:
        logger.error("gsc_coverage_errors error: %s", exc, exc_info=True)
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.route("/api/tools/gsc_sitemaps_status", methods=["POST"])
@login_required
def api_gsc_sitemaps_status():
    """List all sitemaps submitted to GSC with submission and indexing stats."""
    data = request.get_json(force=True) or {}
    site_url = _norm_url((data.get("site_url") or "").strip())
    if not site_url:
        return jsonify({"ok": False, "error": "site_url required"}), 400
    if (rej := _require_public_url(site_url, "site_url"))[1]: return rej[1]
    svc, err = _gsc_service_or_error()
    if err: return err
    from tools.phase3 import sitemaps_status
    try:
        return jsonify(sitemaps_status(svc, site_url))
    except Exception as exc:
        logger.error("gsc_sitemaps_status error: %s", exc, exc_info=True)
        return jsonify({"ok": False, "error": str(exc)}), 500


# ══════════════════════════════════════════════════════════════════════════════
# ROUTES — Notification test endpoints
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/api/tools/notify_test", methods=["POST"])
@login_required
def api_notify_test():
    """Send a test notification via email, slack, or teams."""
    data    = request.get_json(force=True) or {}
    channel = (data.get("channel") or "").strip().lower()
    if channel not in ("email", "slack", "teams"):
        return jsonify({"ok": False, "error": "channel must be email, slack, or teams"}), 400
    from core.notifier import NotificationService
    svc = NotificationService(CFG)
    try:
        if channel == "email":
            svc.send_email("SEO Suite — test notification",
                           "<h2>Test OK</h2><p>Your email notification is configured correctly.</p>")
        elif channel == "slack":
            svc.send_slack("SEO Suite test notification: Slack is configured correctly.")
        else:
            svc.send_teams("SEO Suite test notification: Teams is configured correctly.")
        return jsonify({"ok": True, "message": f"Test {channel} sent successfully"})
    except Exception as exc:
        logger.error("notify_test error: %s", exc, exc_info=True)
        return jsonify({"ok": False, "error": str(exc)}), 500


# ══════════════════════════════════════════════════════════════════════════════
# ROUTES — Individual phase execution
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/api/audit/phase/<int:phase_num>", methods=["POST"])
@login_required
def api_audit_single_phase(phase_num: int):
    """Run a single audit phase (1–4) against a URL and return results immediately."""
    if phase_num not in (1, 2, 3, 4):
        return jsonify({"ok": False, "error": "phase must be 1, 2, 3, or 4"}), 400
    data = request.get_json(force=True) or {}
    url  = _norm_url((data.get("url") or "").strip())
    if not url:
        return jsonify({"ok": False, "error": "url required"}), 400
    if (rej := _reject_unsafe(url)): return rej

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
            fns = [robots_check, http_status_check, redirect_check, canonical_check,
                   title_check, meta_description_check, heading_check, image_alt_check,
                   word_count_check, broken_link_check, internal_links_check,
                   sitemap_validate, schema_check]
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=6) as ex:
                futs = [ex.submit(fn, url) for fn in fns]
                results = [f.result() for f in futs]

        elif phase_num == 2:
            api_key = CFG.get("pagespeed_api_key", "")
            if not api_key:
                return jsonify({"ok": False,
                                "error": "PageSpeed API key not set — go to Settings → Performance"}), 400
            from tools.phase2 import audit_url as p2_audit
            results = p2_audit(url, api_key=api_key)

        elif phase_num == 3:
            gsc_cfg = CFG.get("gsc", {})
            if not gsc_cfg.get("enabled"):
                return jsonify({"ok": False,
                                "error": "GSC not enabled — go to Settings → Indexing & Crawling"}), 400
            svc = build_gsc_service()
            from urllib.parse import urlparse
            parsed   = urlparse(url)
            site_url = f"{parsed.scheme}://{parsed.netloc}/"
            from concurrent.futures import ThreadPoolExecutor

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
            from concurrent.futures import ThreadPoolExecutor

            from tools.phase4 import backlink_check, domain_authority, keyword_rank_tracker
            fns = []
            dfs_login = CFG.get("dataforseo_login", "")
            dfs_pass  = CFG.get("dataforseo_password", "")
            moz_id    = CFG.get("moz_access_id", "")
            moz_sec   = CFG.get("moz_secret_key", "")
            keywords  = data.get("keywords") or CFG.get("track_keywords", [])
            if dfs_login or moz_id:
                fns.append(lambda: backlink_check(url, dataforseo_login=dfs_login, dataforseo_password=dfs_pass))
            if moz_id:
                fns.append(lambda: domain_authority(url, moz_id, moz_sec))
            serpapi_key = CFG.get("serpapi_key", "")
            if keywords and (serpapi_key or dfs_login):
                fns.append(lambda: keyword_rank_tracker(url, keywords,
                                                         serpapi_key=serpapi_key,
                                                         dataforseo_login=dfs_login,
                                                         dataforseo_password=dfs_pass))
            if not fns:
                return jsonify({"ok": False,
                                "error": "Phase 4 requires at least one of: DataForSEO, Moz, or SerpAPI credentials"}), 400
            with ThreadPoolExecutor(max_workers=min(len(fns), 8)) as ex:
                results = [f.result() for f in [ex.submit(fn) for fn in fns]]

        from core.seo_audit import calc_seo_score
        score    = calc_seo_score(results)
        issues   = [r for r in results if r.get("status") in ("fail", "error")]
        warnings = [r for r in results if r.get("status") == "warning"]
        passed   = [r for r in results if r.get("status") == "pass"]
        return jsonify({
            "ok": True, "url": url, "phase": phase_num,
            "score": score, "results": results,
            "counts": {"pass": len(passed), "warning": len(warnings), "fail": len(issues)},
        })

    except Exception as exc:
        logger.error("audit_phase_%d error: %s", phase_num, exc, exc_info=True)
        return jsonify({"ok": False, "error": str(exc)}), 500


# ══════════════════════════════════════════════════════════════════════════════
# ROUTES — Stage 3-C: Performance Opportunity Layer
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/api/tools/perf_opportunities", methods=["POST"])
@login_required
def api_perf_opportunities():
    """Run PageSpeed analysis and return prioritised Core Web Vitals fix plan."""
    data    = request.get_json(force=True) or {}
    url     = _norm_url((data.get("url")     or "").strip())
    api_key = (data.get("api_key") or CFG.get("pagespeed_api_key", "")).strip()
    if not url:
        return jsonify({"ok": False, "error": "url required"}), 400
    if (rej := _reject_unsafe(url)): return rej
    if not api_key:
        return jsonify({"ok": False,
                        "error": "PageSpeed API key required (set in Settings → PageSpeed API Key)"}), 400
    from tools.phase2 import performance_opportunities
    try:
        return jsonify(performance_opportunities(url, api_key))
    except Exception as exc:
        logger.error("perf_opportunities error: %s", exc, exc_info=True)
        return jsonify({"ok": False, "error": str(exc)}), 500


# ══════════════════════════════════════════════════════════════════════════════
# ROUTES — Stage 3-D: Groq AI Assistance
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/api/tools/ai_explain", methods=["POST"])
@login_required
def api_ai_explain():
    """Explain audit results in plain English using Groq LLM."""
    data    = request.get_json(force=True) or {}
    results = data.get("results") or data.get("audit_results") or []
    url     = _norm_url((data.get("url") or "").strip())
    api_key = (data.get("api_key") or CFG.get("groq_api_key", "")
               or os.getenv("GROQ_API_KEY", "")).strip()
    if not results:
        return jsonify({"ok": False, "error": "results required"}), 400
    if not api_key:
        return jsonify({"ok": False,
                        "error": "Groq API key required (Settings → groq_api_key or GROQ_API_KEY env)"}), 400
    from tools.ai_assist import explain_audit
    try:
        return jsonify(explain_audit(results, api_key, url=url))
    except Exception as exc:
        logger.error("ai_explain error: %s", exc, exc_info=True)
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.route("/api/tools/ai_draft_meta", methods=["POST"])
@login_required
def api_ai_draft_meta():
    """Draft improved title + meta description variants using Groq LLM."""
    data         = request.get_json(force=True) or {}
    url          = _norm_url((data.get("url")          or "").strip())
    current_title = (data.get("title")       or "").strip()
    current_desc  = (data.get("description") or "").strip()
    top_queries   = data.get("top_queries")  or []
    api_key       = (data.get("api_key") or CFG.get("groq_api_key", "")
                     or os.getenv("GROQ_API_KEY", "")).strip()
    if not url:
        return jsonify({"ok": False, "error": "url required"}), 400
    if (rej := _reject_unsafe(url)): return rej
    if not api_key:
        return jsonify({"ok": False,
                        "error": "Groq API key required (Settings → groq_api_key)"}), 400
    from tools.ai_assist import draft_meta
    try:
        return jsonify(draft_meta(url, current_title, current_desc, top_queries, api_key))
    except Exception as exc:
        logger.error("ai_draft_meta error: %s", exc, exc_info=True)
        return jsonify({"ok": False, "error": str(exc)}), 500


# ══════════════════════════════════════════════════════════════════════════════
# ROUTES — Generators (Phase B)
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/api/tools/schema_fields/<schema_type>")
@login_required
def api_schema_fields(schema_type):
    from tools.generators import get_schema_fields
    return jsonify(get_schema_fields(schema_type))

@app.route("/api/tools/schema_generate", methods=["POST"])
@login_required
def api_schema_generate():
    data = request.get_json(force=True) or {}
    schema_type = (data.get("schema_type") or "").strip()
    form_data   = data.get("data", {})
    if not schema_type:
        return jsonify({"ok": False, "error": "schema_type required"}), 400
    from tools.generators import generate_schema
    return jsonify(generate_schema(schema_type, form_data))

@app.route("/api/tools/robots_txt", methods=["POST"])
@login_required
def api_robots_txt():
    data = request.get_json(force=True) or {}
    from tools.generators import generate_robots_txt
    return jsonify(generate_robots_txt(data))

@app.route("/api/tools/sitemap_generate", methods=["POST"])
@login_required
def api_sitemap_generate():
    data = request.get_json(force=True) or {}
    from tools.generators import generate_sitemap
    return jsonify(generate_sitemap(data))

@app.route("/api/tools/hreflang_generate", methods=["POST"])
@login_required
def api_hreflang_generate():
    data = request.get_json(force=True) or {}
    from tools.generators import generate_hreflang
    return jsonify(generate_hreflang(data))

@app.route("/api/tools/meta_tags_generate", methods=["POST"])
@login_required
def api_meta_tags_generate():
    data = request.get_json(force=True) or {}
    from tools.generators import generate_meta_tags
    return jsonify(generate_meta_tags(data))


@app.route("/api/tools/robots_tester", methods=["POST"])
@login_required
def api_robots_tester():
    """Fetch and analyse a live robots.txt — parse directives, detect issues, validate rules."""
    data = request.get_json(force=True) or {}
    url  = _norm_url((data.get("url") or "").strip())
    if not url:
        return jsonify({"ok": False, "error": "url required"}), 400
    if (rej := _reject_unsafe(url)): return rej
    from tools.quick_tools import robots_tester
    return jsonify(robots_tester(url))


@app.route("/api/tools/hreflang_validate", methods=["POST"])
@login_required
def api_hreflang_validate():
    """Fetch a page, extract hreflang tags, validate them, and check alternate URL reachability."""
    data = request.get_json(force=True) or {}
    url  = _norm_url((data.get("url") or "").strip())
    if not url:
        return jsonify({"ok": False, "error": "url required"}), 400
    if (rej := _reject_unsafe(url)): return rej
    from tools.quick_tools import hreflang_validator
    return jsonify(hreflang_validator(url))


@app.route("/api/tools/link_health", methods=["POST"])
@login_required
def api_link_health():
    """Fetch a page and probe every outbound link for broken (4xx/5xx) or redirect status."""
    data = request.get_json(force=True) or {}
    url  = _norm_url((data.get("url") or "").strip())
    if not url:
        return jsonify({"ok": False, "error": "url required"}), 400
    if (rej := _reject_unsafe(url)): return rej
    from tools.quick_tools import broken_link_checker
    return jsonify(broken_link_checker(url))


# ══════════════════════════════════════════════════════════════════════════════

def _save_partial_index_report() -> tuple[str, str]:
    """Save a partial indexing CSV+HTML from whatever has been collected so far.
    Returns (html_filename, csv_filename) — empty strings on failure."""
    from core.report_generator import ReportGenerator
    snapshot = _snapshot_last_index_run()
    if not snapshot:
        return "", ""
    try:
        ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
        stem = f"indexing_report_{ts}_partial"
        csv_path  = REPORTS_DIR / f"{stem}.csv"
        html_path = REPORTS_DIR / f"{stem}.html"
        counts    = {}
        rows      = []
        from core.checker import get_crawl_depth, get_priority_score, get_url_type
        ts_now = datetime.now().isoformat()
        for i, (url, status) in enumerate(snapshot.items(), 1):
            rows.append({"num": i, "url": url, "status": status,
                         "priority": get_priority_score(url),
                         "depth": get_crawl_depth(url),
                         "url_type": get_url_type(url),
                         "checked_at": ts_now})
            counts[status] = counts.get(status, 0) + 1
        import csv as _csv
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            w = _csv.writer(f)
            w.writerow(["#", "URL", "Google Indexed", "Priority", "Depth", "URL Type", "Checked At"])
            for r in rows:
                w.writerow([r["num"], r["url"], r["status"], r["priority"],
                             r["depth"], r["url_type"], r["checked_at"]])
        ReportGenerator().html(rows, html_path, counts, {}, None, [])
        return html_path.name, csv_path.name
    except Exception as exc:
        logger.warning("Partial index report save failed: %s", exc)
        return "", ""

@app.route("/api/index/cancel", methods=["POST"])
@login_required
def api_index_cancel():
    # Signal cancellation only — let the worker's finally clear `running`.
    # If we flipped `running` here while the worker thread was still alive, a
    # second /api/index/run posted immediately after this would be accepted
    # and race against the still-draining prior thread on _last_index_run.
    _index_cancel.set()
    _index_paused.set()   # unblock thread so it can exit
    html_name, csv_name = _save_partial_index_report()
    with _lock:
        done = _index_status.get("done", 0)
    _broadcast_index({
        "type":    "cancelled",
        "report":  html_name,
        "csv":     csv_name,
        "done":    done,
    })
    return jsonify({"cancelled": True})

@app.route("/api/index/pause", methods=["POST"])
@login_required
def api_index_pause():
    if not _index_status["running"]:
        return jsonify({"error": "Not running"}), 400
    _index_paused.clear()   # block the worker thread
    _index_queue.put({"type": "paused"})
    return jsonify({"paused": True})

@app.route("/api/index/resume", methods=["POST"])
@login_required
def api_index_resume():
    _index_paused.set()     # unblock the worker thread
    _index_queue.put({"type": "resumed"})
    return jsonify({"resumed": True})

@app.route("/api/index/errors")
@login_required
def api_index_errors():
    data = _snapshot_last_index_run()
    error_urls = [url for url, status in data.items() if _is_error_status(status)]
    return jsonify({"error_urls": error_urls, "count": len(error_urls)})

@app.route("/api/index/retry", methods=["POST"])
@login_required
def api_index_retry():
    if _index_status["running"]:
        return jsonify({"error": "Already running"}), 400

    error_urls = [
        url for url, status in _snapshot_last_index_run().items()
        if _is_error_status(status)
    ]

    if not error_urls:
        return jsonify({"error": "No failed URLs to retry"}), 400

    data     = request.get_json() or {}
    headless = data.get("headless", False)
    quiet    = data.get("quiet", False)

    with _lock:
        if _index_status["running"]:
            return jsonify({"error": "Already running"}), 400
        _index_status.update({"running": True, "total": len(error_urls), "done": 0})

    def run():
        try:
            _run_results: dict[str, str] = {}

            def cb(num, total, url, status):
                _run_results[url] = status
                _update_last_index_run(url, status)
                _index_queue.put({"type": "progress", "num": num, "total": total, "url": url, "status": status})
                with _lock:
                    _index_status["done"] = num

            html = execute_and_save(error_urls, headless=headless, quiet=quiet,
                                    do_compare=False, prev_report=None, progress_cb=cb)
            with _lock:
                _last_index_run.update(_run_results)
            error_count = sum(1 for s in _run_results.values() if _is_error_status(s))
            _index_queue.put({"type": "done", "report": str(html), "error_count": error_count})
        except Exception as e:
            logger.error("Retry thread error: %s", e, exc_info=True)
            _index_queue.put({"type": "error", "message": str(e)})
        finally:
            with _lock:
                _index_status["running"] = False

    threading.Thread(target=run, daemon=True).start()
    return jsonify({"total": len(error_urls), "started": True})

def _save_partial_audit_report() -> tuple[str, str]:
    """Save a partial audit HTML+Excel from full results collected so far.
    Returns (html_filename, xlsx_filename) — empty strings on failure/no data."""
    with _lock:
        snapshot = list(_audit_full_results)
    if not snapshot:
        return "", ""
    try:
        ts         = datetime.now().strftime("%Y%m%d_%H%M%S")
        stem       = f"seo_audit_{ts}_partial"
        html_path  = REPORTS_DIR / f"{stem}.html"
        excel_path = REPORTS_DIR / f"{stem}.xlsx"
        json_path  = REPORTS_DIR / f"{stem}.json"
        html_path.write_text(generate_html_report(snapshot, [], ts), encoding="utf-8")
        xlsx_ok = False
        try:
            generate_excel_report(snapshot, excel_path)
            xlsx_ok = True
        except Exception as _xe:
            logger.warning("Partial Excel report failed (non-fatal): %s", _xe)
        try:
            sidecar = {
                "avg_score":      round(sum(a["score"] for a in snapshot) / len(snapshot)),
                "total_issues":   sum(len(a.get("issues", [])) for a in snapshot),
                "total_warnings": sum(len(a.get("warnings", [])) for a in snapshot),
                "urls":           len(snapshot),
            }
            json_path.write_text(json.dumps(sidecar), encoding="utf-8")
        except Exception:
            pass
        return html_path.name, (excel_path.name if xlsx_ok else "")
    except Exception as exc:
        logger.warning("Partial audit report save failed: %s", exc)
        return "", ""

@app.route("/api/audit/cancel", methods=["POST"])
@login_required
def api_audit_cancel():
    # Signal cancellation only — let the worker's finally clear `running`.
    _audit_cancel.set()
    _audit_paused.set()   # unblock thread so it can see the cancel flag
    html_name, xlsx_name = _save_partial_audit_report()
    with _lock:
        done = _audit_status.get("done", 0)
    _broadcast_audit({
        "type":   "cancelled",
        "report": html_name,
        "xlsx":   xlsx_name,
        "done":   done,
    })
    return jsonify({"cancelled": True})

@app.route("/api/audit/pause", methods=["POST"])
@login_required
def api_audit_pause():
    if not _audit_status["running"]:
        return jsonify({"error": "Not running"}), 400
    _audit_paused.clear()
    _audit_queue.put({"type": "paused"})
    return jsonify({"paused": True})

@app.route("/api/audit/resume", methods=["POST"])
@login_required
def api_audit_resume():
    _audit_paused.set()
    _audit_queue.put({"type": "resumed"})
    return jsonify({"resumed": True})

@app.route("/api/audit/partial")
@login_required
def api_audit_partial():
    """Return completed-so-far audit results as CSV for mid-run export."""
    import csv as _csv
    import io as _io
    with _lock:
        rows = list(_audit_partial)
    if not rows:
        return jsonify({"error": "No results yet"}), 404
    buf = _io.StringIO()
    w = _csv.writer(buf)
    w.writerow(["URL", "Score", "Issues", "Warnings"])
    for r in rows:
        w.writerow([r["url"], r["score"], r["issues"], r["warnings"]])
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return buf.getvalue(), 200, {
        "Content-Type": "text/csv",
        "Content-Disposition": f"attachment; filename=audit_partial_{ts}.csv",
    }

@app.route("/api/index/partial")
@login_required
def api_index_partial():
    """Return completed-so-far indexing results as CSV for mid-run export."""
    import csv as _csv
    import io as _io
    data = _snapshot_last_index_run()
    if not data:
        return jsonify({"error": "No results yet"}), 404
    buf = _io.StringIO()
    w = _csv.writer(buf)
    w.writerow(["URL", "Status"])
    for url, status in data.items():
        w.writerow([url, status])
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return buf.getvalue(), 200, {
        "Content-Type": "text/csv",
        "Content-Disposition": f"attachment; filename=indexing_partial_{ts}.csv",
    }


# NOTE: the canonical entry point is main.py at the project root. This module
# is intentionally NOT runnable directly — drift between two __main__ blocks
# (different ports, different env defaults) is too easy a footgun.
