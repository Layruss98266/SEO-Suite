"""
Shared in-process state and helper utilities for the SEO Suite Flask app.

This module is the single source of truth for:

* **Paths & directories** — project root, data dir, reports dir, upload dir
* **Constants** — limits, error tokens, format prefixes
* **Shared mutable state** — SSE subscriber queues, run status dicts, locks,
  cancel events, paused events, partial result buffers
* **Helper functions** — URL validation, SSRF guards, integer parsing,
  CSV sanitization, path traversal guards, broadcast queue plumbing

Routes (whether in ``app/server.py`` or ``app/blueprints/*``) import what they
need from here. Keeping state out of ``server.py`` means each blueprint can be
written without depending on the big monolith, and ``server.py`` can shrink to
a slim factory.

**Reassignment vs. mutation:** Some state values (``_audit_status`` /
``_index_status`` / ``CFG``) are reassigned during runtime. Callers reassigning
these must reference them through the module to avoid rebinding a local name —
e.g. ``from app import state; state._audit_status = {...}``. Values that are
*mutated in place* (dicts cleared+updated, lists appended, events set/cleared)
can be imported directly: ``from app.state import _lock, _audit_subscribers``.
"""

from __future__ import annotations

import logging
import os
import queue
import re
import threading
import time
from pathlib import Path

from flask import jsonify

from core.checker import load_config
from core.security import is_safe_url, validate_public_url

logger = logging.getLogger(__name__)

# ── Paths ─────────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent.parent.resolve()
_DATA_BASE   = Path(os.environ.get("SEO_SUITE_DATA_DIR", PROJECT_ROOT / "data"))

TEMPLATE_DIR = Path(__file__).parent / "templates"
STATIC_DIR   = Path(__file__).parent / "static"

CONFIG_PATH  = PROJECT_ROOT / "config.json"
DATA_DIR     = _DATA_BASE
REPORTS_DIR  = DATA_DIR / "reports"
UPLOAD_DIR   = DATA_DIR / "uploads"
PROFILES_PATH = DATA_DIR / "profiles.json"

# Best-effort dir creation — never crash import on a read-only filesystem.
for _d in (DATA_DIR, REPORTS_DIR, UPLOAD_DIR):
    try:
        _d.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass

# Loaded once at import; refreshed in /api/settings POST.
CFG = load_config()

# ── Constants ─────────────────────────────────────────────────────────────────
# Cap on per-run audit result lists so a huge sitemap can't blow up memory.
# Past this point new results are dropped from the live progress feed; the
# completed report still gets every URL written to disk.
MAX_AUDIT_RESULTS = 5000

ERROR_STATUSES = {"Error", "Timeout", "Other"}
ERROR_PREFIXES = ("GSC Error", "Error:", "Error ", "Browser Error", "Playwright Error")

# PDF generation spawns Playwright per request — cap concurrency so a burst of
# /api/reports/pdf calls can't OOM the host with parallel chromium processes.
_PDF_CONCURRENCY = max(1, int(os.environ.get("SEO_SUITE_PDF_WORKERS", "2")))
_pdf_semaphore = threading.Semaphore(_PDF_CONCURRENCY)

# CSV formula injection prefixes (Excel auto-executes these on cell click).
_CSV_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")

# Stem regex for delete operations — defensive even though _safe_report_path
# already filters extensions.
_REPORT_STEM_RE = re.compile(r"^(indexing_report|seo_audit)_[\w\-]+$")


# ── Shared run state ──────────────────────────────────────────────────────────
# SSE subscribers — each connected client gets its own bounded queue so multiple
# browser tabs (or a tab that reloads mid-run) all see every progress event.
# The previous single-Queue design let the first subscriber drain the queue,
# leaving later/reconnected clients stuck on the last seen state.
_index_subscribers: list[queue.Queue] = []
_audit_subscribers: list[queue.Queue] = []
_sub_lock = threading.Lock()


class _BroadcastQueue:
    """Thin adapter that broadcasts ``put`` calls to every subscriber queue.

    The internal cancel/error paths still call ``_index_queue.put(...)`` style;
    this lets that code remain unchanged while every subscriber sees the event.
    """

    def __init__(self, subs: list[queue.Queue]) -> None:
        self._subs = subs

    def put(self, msg) -> None:
        with _sub_lock:
            dead = []
            for q in self._subs:
                try:
                    q.put_nowait(msg)
                except queue.Full:
                    dead.append(q)
            for q in dead:
                try:
                    self._subs.remove(q)
                except ValueError:
                    pass


_index_queue = _BroadcastQueue(_index_subscribers)
_audit_queue = _BroadcastQueue(_audit_subscribers)


def _broadcast_index(msg) -> None:
    _index_queue.put(msg)


def _broadcast_audit(msg) -> None:
    _audit_queue.put(msg)


def _subscribe(subs: list[queue.Queue]) -> queue.Queue:
    q = queue.Queue(maxsize=1000)
    with _sub_lock:
        subs.append(q)
    return q


def _unsubscribe(subs: list[queue.Queue], q: queue.Queue) -> None:
    with _sub_lock:
        try:
            subs.remove(q)
        except ValueError:
            pass


def _cleanup_subscribers() -> None:
    """Background thread: periodically drop fully-queued (stale) SSE queues.

    A subscriber that has disconnected without calling /api/index/stream
    cleanup leaves a full queue behind. Without this sweep those queues
    accumulate indefinitely, slowly leaking memory. We remove any queue
    whose buffer is already at capacity — a live consumer would have drained
    it. Runs every 5 minutes; daemon so it doesn't block process exit.
    """
    while True:
        time.sleep(300)
        with _sub_lock:
            for subs in (_index_subscribers, _audit_subscribers):
                subs[:] = [q for q in subs if not q.full()]


# Mutable status dicts — REASSIGNED in routes via `state._index_status = {...}`.
_index_status = {"running": False, "total": 0, "done": 0}
_audit_status = {"running": False, "total": 0, "done": 0}

# Cancel events — set() to request cancellation, clear() at run start.
_index_cancel = threading.Event()
_audit_cancel = threading.Event()

# Pause events — start in "set" (running) state. clear() to pause, set() to resume.
_index_paused = threading.Event()
_index_paused.set()
_audit_paused = threading.Event()
_audit_paused.set()

# Generic write lock for status dicts and the live-results map below.
_lock = threading.Lock()

# Live per-URL status map for the active indexing run.
_last_index_run: dict[str, str] = {}

# Partial result buffers — drained mid-run to produce CSV/HTML exports if the
# user cancels. Bounded by MAX_AUDIT_RESULTS to keep memory flat on huge runs.
_audit_partial: list = []
_audit_full_results: list = []


def _snapshot_last_index_run() -> dict[str, str]:
    with _lock:
        return dict(_last_index_run)


def _reset_last_index_run() -> None:
    with _lock:
        _last_index_run.clear()


def _update_last_index_run(url: str, status: str) -> None:
    with _lock:
        _last_index_run[url] = status


def _replace_last_index_run(results: dict[str, str]) -> None:
    with _lock:
        _last_index_run.clear()
        _last_index_run.update(results)


# ── URL validation helpers ────────────────────────────────────────────────────

def _require_public_url(value: str, field_name: str = "url"):
    """Validate `value` as a public URL. Returns (url, None) on success or
    (None, (response, status)) on failure — ready to be `return`ed from a route.
    """
    try:
        return validate_public_url(value), None
    except ValueError as exc:
        return None, (jsonify({"error": f"Invalid {field_name}: {exc}"}), 400)


def _safe_public_url_list(raw: str) -> list[str]:
    """Split a comma-separated URL list and drop any URL that fails SSRF check."""
    urls = []
    for part in raw.split(","):
        candidate = part.strip()
        if not candidate:
            continue
        try:
            urls.append(validate_public_url(candidate))
        except ValueError as exc:
            logger.warning("Blocked URL in list %s: %s", candidate, exc)
    return urls


def _norm_url(url: str) -> str:
    """Prepend https:// if the user omitted a scheme (e.g. 'example.com')."""
    if url and not url.startswith(("http://", "https://")):
        return f"https://{url}"
    return url


def _reject_unsafe(url: str):
    """Return a 400 JSON response if *url* fails the SSRF safety check, else None.

    The tool endpoints all accept a URL from the request body and fetch it
    server-side. Without this guard, anyone reaching the server can pivot
    requests to internal services (cloud metadata, the dashboard's own
    delete_all endpoint, etc.). See core.security.is_safe_url for the policy.
    """
    ok, reason = is_safe_url(url)
    if ok:
        return None
    return jsonify({"ok": False, "error": f"URL refused: {reason}"}), 400


def _int(data: dict, key: str, default: int, lo: int, hi: int) -> int:
    """Safely parse an integer from a request-data dict, clamped to [lo, hi].

    Returns *default* (clamped) when the key is absent, None, or not
    convertible to int — preventing bare ``int()`` calls from raising
    ValueError / TypeError and producing HTTP 500 responses.
    """
    try:
        return max(lo, min(hi, int(data.get(key, default))))
    except (TypeError, ValueError):
        return max(lo, min(hi, default))


# ── CSV sanitization ──────────────────────────────────────────────────────────

def _sanitize_csv(content: str) -> str:
    """Strip leading formula characters from CSV cell values to prevent injection."""
    lines = []
    for line in content.splitlines(keepends=True):
        cells = []
        for cell in line.rstrip("\n\r").split(","):
            stripped = cell.lstrip()
            if stripped and stripped[0] in _CSV_FORMULA_PREFIXES:
                cell = "'" + cell
            cells.append(cell)
        lines.append(",".join(cells) + ("\n" if line.endswith("\n") else ""))
    return "".join(lines)


# ── Path traversal guards ─────────────────────────────────────────────────────

def _safe_report_path(filename: str, allowed_exts: tuple[str, ...]) -> Path | None:
    """Validate that *filename* resolves inside REPORTS_DIR and has an allowed extension.
    Returns the resolved Path or None. Used to block path traversal in /api/open,
    /api/download, /api/reports/pdf."""
    if not isinstance(filename, str) or not filename:
        return None
    # Reject anything that looks like a separator or traversal segment up front.
    if "/" in filename or "\\" in filename or ".." in filename or filename.startswith("."):
        return None
    if not re.match(r"^[\w\-]+(?:\.[\w\-]+)*$", filename):
        return None
    if allowed_exts and not filename.lower().endswith(allowed_exts):
        return None
    try:
        candidate = (REPORTS_DIR / filename).resolve()
        candidate.relative_to(REPORTS_DIR.resolve())
    except (ValueError, OSError):
        return None
    return candidate


def _safe_upload_path(raw: str) -> Path | None:
    """Validate that *raw* points to a file inside data/uploads/.
    Returns the resolved Path if safe, else None. Used to prevent a client from
    making the audit/index handlers read arbitrary filesystem paths via the
    csv/xlsx input mode."""
    try:
        uploads = UPLOAD_DIR.resolve()
        target = Path(raw).resolve()
        target.relative_to(uploads)
        return target if target.is_file() else None
    except (ValueError, OSError):
        return None
