"""Indexing routes — ``/api/index/*``.

Owns the indexing workflow: run/cancel/pause/resume/retry, the long-lived SSE
progress stream, the live "what's been done so far" partial CSV export, and
the saved partial report when a run is cancelled.

Concurrency:
* At most one indexing run at a time, enforced by ``_lock`` +
  ``_index_status["running"]``.
* The worker thread is a daemon — process exit drops it cleanly.
* SSE stream subscribers each get their own bounded queue so multiple
  browser tabs see every event.
"""

from __future__ import annotations

import csv as _csv
import io as _io
import json
import logging
import queue
import threading
from datetime import datetime

from flask import Blueprint, Response, jsonify, request

from app.blueprints import api_error
from app.metrics import record_indexing_event
from app.state import (
    ERROR_PREFIXES,
    ERROR_STATUSES,
    REPORTS_DIR,
    _broadcast_index,
    _index_cancel,
    _index_paused,
    _index_queue,
    _index_status,
    _index_subscribers,
    _int,
    _last_index_run,
    _lock,
    _norm_url,
    _replace_last_index_run,
    _reset_last_index_run,
    _safe_public_url_list,
    _safe_upload_path,
    _snapshot_last_index_run,
    _subscribe,
    _unsubscribe,
    _update_last_index_run,
)
from core.auth import login_required
from core.checker import (
    execute_and_save,
    fetch_from_domain,
    fetch_sitemap_urls,
    filter_urls,
    find_latest_report,
    load_from_csv_excel,
)
from core.security import is_safe_url

logger = logging.getLogger(__name__)

bp = Blueprint("indexing", __name__)


# ── Helpers ───────────────────────────────────────────────────────────────────

# Canonical 7-column header for indexing CSV exports. Shared between the
# end-of-run report, the cancelled-run partial report, and the live mid-run
# `/api/index/partial` download so downstream tools (Excel, pandas, Screaming
# Frog) see a stable column shape regardless of when the export is triggered.
INDEX_CSV_HEADER = [
    "#",
    "URL",
    "Google Indexed",
    "Priority",
    "Depth",
    "URL Type",
    "Checked At",
]


def _pad_row(row: list, width: int = len(INDEX_CSV_HEADER)) -> list:
    """Right-pad ``row`` with empty strings so it matches ``width`` columns.

    Truncates over-long rows to ``width`` to guarantee column alignment even
    when a partial/cancelled export hands us a short tuple.
    """
    row = list(row)
    if len(row) < width:
        row = row + [""] * (width - len(row))
    elif len(row) > width:
        row = row[:width]
    return row


def _is_error_status(status: str) -> bool:
    """True if a per-URL status string indicates a failure to verify indexing.

    Covers the exact tokens ``Error``, ``Timeout``, ``Other`` and the various
    ``"GSC Error: …"`` / ``"Error: …"`` prefixes returned by the checker on
    exceptions.
    """
    if not isinstance(status, str):
        return False
    if status in ERROR_STATUSES:
        return True
    return any(status.startswith(prefix) for prefix in ERROR_PREFIXES)


def _save_partial_index_report() -> tuple[str, str]:
    """Save a partial indexing CSV+HTML from whatever has been collected so far.

    Returns ``(html_filename, csv_filename)`` — empty strings on failure.
    """
    from core.report_generator import ReportGenerator

    snapshot = _snapshot_last_index_run()
    if not snapshot:
        return "", ""
    try:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        stem = f"indexing_report_{ts}_partial"
        csv_path = REPORTS_DIR / f"{stem}.csv"
        html_path = REPORTS_DIR / f"{stem}.html"
        counts: dict = {}
        rows = []
        from core.checker import get_crawl_depth, get_priority_score, get_url_type

        ts_now = datetime.now().isoformat()
        for i, (url, status) in enumerate(snapshot.items(), 1):
            rows.append(
                {
                    "num": i,
                    "url": url,
                    "status": status,
                    "priority": get_priority_score(url),
                    "depth": get_crawl_depth(url),
                    "url_type": get_url_type(url),
                    "checked_at": ts_now,
                }
            )
            counts[status] = counts.get(status, 0) + 1
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            w = _csv.writer(f)
            w.writerow(INDEX_CSV_HEADER)
            for r in rows:
                w.writerow(
                    _pad_row(
                        [
                            r["num"],
                            r["url"],
                            r["status"],
                            r["priority"],
                            r["depth"],
                            r["url_type"],
                            r["checked_at"],
                        ]
                    )
                )
        ReportGenerator().html(rows, html_path, counts, {}, None, [])
        return html_path.name, csv_path.name
    except Exception as exc:
        logger.warning("Partial index report save failed: %s", exc)
        return "", ""


# ── Run ───────────────────────────────────────────────────────────────────────
@bp.route("/api/index/run", methods=["POST"])
@login_required
def api_index_run():
    # Quick reject — snapshot under lock so we don't read shared dict bare.
    with _lock:
        running = _index_status.get("running", False)
    if running:
        return api_error("Already running", 400)

    try:
        data = request.get_json(force=True) or {}
    except Exception:
        return api_error("Invalid JSON in request body", 400)

    input_type = data.get("input_type", "sitemap")
    raw = data.get("input", "").strip()
    if not raw:
        return api_error("No URL or sitemap provided", 400)
    # SSRF guard for URL-bearing input modes. CSV/list inputs are filesystem or
    # multi-URL — those URLs are checked individually downstream by Playwright,
    # which targets google.com (not the user-supplied host).
    if input_type in ("sitemap", "domain"):
        raw = _norm_url(raw)
        ok, reason = is_safe_url(raw)
        if not ok:
            return api_error(f"URL refused: {reason}", 400)
    pattern = data.get("pattern", "")
    # Clamp limit so a client can't request a 999999-URL run that ties up
    # Playwright workers and disk.
    limit = _int(data, "limit", 20, 1, 500)
    quiet = data.get("quiet", False)
    headless = data.get("headless", False)
    do_compare = data.get("compare", False)

    estimated_total = limit
    # Atomic check+set so a concurrent POST that snuck past the early check
    # can't also flip running=True and spawn a second worker thread.
    with _lock:
        if _index_status["running"]:
            return api_error("Already running", 400)
        _index_status.update({"running": True, "total": estimated_total, "done": 0})

    def run():
        try:
            # Fetch URLs inside the thread — keeps the HTTP response fast.
            if input_type == "sitemap":
                urls = fetch_sitemap_urls(raw)
            elif input_type == "domain":
                urls = fetch_from_domain(raw)
            elif input_type == "csv":
                safe = _safe_upload_path(raw)
                if safe is None:
                    _index_queue.put(
                        {
                            "type": "error",
                            "message": "CSV path must point to an uploaded file in data/uploads/",
                        }
                    )
                    return
                urls = load_from_csv_excel(str(safe))
            elif input_type in ("paste", "list"):
                # Comma-separated list of URLs pasted by the user. The helper
                # drops anything that fails the SSRF check.
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
                _index_queue.put(
                    {
                        "type": "error",
                        "message": "No URLs found — check your sitemap URL or filter pattern",
                    }
                )
                return

            with _lock:
                _index_status["total"] = len(urls)
            _reset_last_index_run()

            _index_cancel.clear()
            _index_paused.set()  # ensure not paused at start of run
            prev = find_latest_report() if do_compare else None
            _run_results: dict[str, str] = {}

            def cb(num, total, url, status):
                _index_paused.wait()  # block here while paused
                if _index_cancel.is_set():
                    return
                _run_results[url] = status
                _update_last_index_run(url, status)
                from core.checker import get_crawl_depth, get_priority_score, get_url_type

                _index_queue.put(
                    {
                        "type": "progress",
                        "num": num,
                        "total": total,
                        "url": url,
                        "status": status,
                        "priority": get_priority_score(url),
                        "depth": get_crawl_depth(url),
                        "url_type": get_url_type(url),
                    }
                )
                with _lock:
                    _index_status["done"] = num

            html = execute_and_save(
                urls,
                headless=headless,
                quiet=quiet,
                do_compare=do_compare,
                prev_report=prev,
                progress_cb=cb,
            )
            _replace_last_index_run(_run_results)
            error_count = sum(1 for s in _run_results.values() if _is_error_status(s))
            _index_queue.put(
                {"type": "done", "report": str(html), "error_count": error_count}
            )
            record_indexing_event("completed")
        except Exception as e:
            logger.error("Indexing thread error: %s", e, exc_info=True)
            _index_queue.put({"type": "error", "message": str(e)})
            record_indexing_event("error")
        finally:
            with _lock:
                _index_status["running"] = False

    record_indexing_event("started")
    threading.Thread(target=run, daemon=True).start()
    return jsonify({"total": estimated_total, "started": True})


# ── SSE stream ────────────────────────────────────────────────────────────────
@bp.route("/api/index/stream")
@login_required
def api_index_stream():
    """Long-lived SSE stream of indexing progress.

    The :func:`register` factory marks this endpoint as ``limiter.exempt`` so
    the connection isn't counted against the per-IP rate cap.
    """
    sub = _subscribe(_index_subscribers)
    if sub is None:
        return api_error("Too many concurrent SSE connections", 503)

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
            _unsubscribe(_index_subscribers, sub)

    return Response(
        gen(),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── Cancel / pause / resume / errors ──────────────────────────────────────────
@bp.route("/api/index/cancel", methods=["POST"])
@login_required
def api_index_cancel():
    # Signal cancellation only — let the worker's finally clear `running`.
    # If we flipped `running` here while the worker thread was still alive, a
    # second /api/index/run posted immediately after this would be accepted
    # and race against the still-draining prior thread on _last_index_run.
    _index_cancel.set()
    _index_paused.set()  # unblock thread so it can exit
    html_name, csv_name = _save_partial_index_report()
    with _lock:
        done = _index_status.get("done", 0)
    _broadcast_index(
        {
            "type": "cancelled",
            "report": html_name,
            "csv": csv_name,
            "done": done,
        }
    )
    record_indexing_event("cancelled")
    return jsonify({"cancelled": True})


@bp.route("/api/index/pause", methods=["POST"])
@login_required
def api_index_pause():
    with _lock:
        running = _index_status.get("running", False)
    if not running:
        return api_error("Not running", 400)
    _index_paused.clear()  # block the worker thread
    _index_queue.put({"type": "paused"})
    return jsonify({"paused": True})


@bp.route("/api/index/resume", methods=["POST"])
@login_required
def api_index_resume():
    _index_paused.set()  # unblock the worker thread
    _index_queue.put({"type": "resumed"})
    return jsonify({"resumed": True})


@bp.route("/api/index/errors")
@login_required
def api_index_errors():
    data = _snapshot_last_index_run()
    error_urls = [url for url, status in data.items() if _is_error_status(status)]
    return jsonify({"error_urls": error_urls, "count": len(error_urls)})


# ── Retry only error URLs ─────────────────────────────────────────────────────
@bp.route("/api/index/retry", methods=["POST"])
@login_required
def api_index_retry():
    with _lock:
        running = _index_status.get("running", False)
    if running:
        return api_error("Already running", 400)

    error_urls = [
        url
        for url, status in _snapshot_last_index_run().items()
        if _is_error_status(status)
    ]

    if not error_urls:
        return api_error("No failed URLs to retry", 400)

    data = request.get_json() or {}
    headless = data.get("headless", False)
    quiet = data.get("quiet", False)

    with _lock:
        if _index_status["running"]:
            return api_error("Already running", 400)
        _index_status.update({"running": True, "total": len(error_urls), "done": 0})

    def run():
        try:
            _run_results: dict[str, str] = {}

            def cb(num, total, url, status):
                _run_results[url] = status
                _update_last_index_run(url, status)
                _index_queue.put(
                    {
                        "type": "progress",
                        "num": num,
                        "total": total,
                        "url": url,
                        "status": status,
                    }
                )
                with _lock:
                    _index_status["done"] = num

            html = execute_and_save(
                error_urls,
                headless=headless,
                quiet=quiet,
                do_compare=False,
                prev_report=None,
                progress_cb=cb,
            )
            with _lock:
                # Remove stale entries for retried URLs before writing fresh
                # results so a URL that was skipped/errored during this run
                # does not silently keep its previous status (H-4).
                for url in error_urls:
                    _last_index_run.pop(url, None)
                _last_index_run.update(_run_results)
            error_count = sum(1 for s in _run_results.values() if _is_error_status(s))
            _index_queue.put(
                {"type": "done", "report": str(html), "error_count": error_count}
            )
        except Exception as e:
            logger.error("Retry thread error: %s", e, exc_info=True)
            _index_queue.put({"type": "error", "message": str(e)})
        finally:
            with _lock:
                _index_status["running"] = False

    threading.Thread(target=run, daemon=True).start()
    return jsonify({"total": len(error_urls), "started": True})


# ── Partial CSV export ────────────────────────────────────────────────────────
@bp.route("/api/index/partial")
@login_required
def api_index_partial():
    """Return completed-so-far indexing results as CSV for mid-run export.

    Emits the same 7-column shape as the end-of-run report and the cancelled-run
    partial report (see ``INDEX_CSV_HEADER``). Earlier this endpoint emitted a
    bespoke 2-column format which broke downstream tools that expected the
    canonical schema (AUDIT_LOG C9).
    """
    data = _snapshot_last_index_run()
    if not data:
        return api_error("No results yet", 404)
    # Lazy import — avoids pulling Playwright/etc at module import time and
    # mirrors the import pattern used in `_save_partial_index_report`.
    from core.checker import get_crawl_depth, get_priority_score, get_url_type

    buf = _io.StringIO()
    w = _csv.writer(buf)
    w.writerow(INDEX_CSV_HEADER)
    ts_now = datetime.now().isoformat()
    for i, (url, status) in enumerate(data.items(), 1):
        w.writerow(
            _pad_row(
                [
                    i,
                    url,
                    status,
                    get_priority_score(url),
                    get_crawl_depth(url),
                    get_url_type(url),
                    ts_now,
                ]
            )
        )
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return buf.getvalue(), 200, {
        "Content-Type": "text/csv",
        "Content-Disposition": f"attachment; filename=indexing_partial_{ts}.csv",
    }


# ── Public re-exports for use by other blueprints ─────────────────────────────
__all__ = ["bp", "register", "_is_error_status", "_save_partial_index_report"]


def register(app, limiter) -> None:
    """Register the blueprint and rate-limit / exempt routes appropriately."""
    app.register_blueprint(bp)
    limiter.limit("10 per hour")(app.view_functions["indexing.api_index_run"])
    limiter.exempt(app.view_functions["indexing.api_index_stream"])
