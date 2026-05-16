"""
Shared mutable state for the SEO Suite Flask application.

All background threads, route handlers, and blueprints import from here so
there is a single source of truth for run status, SSE queues, and config.
"""

import queue
import threading
from pathlib import Path

from core.checker import load_config

# ── Filesystem anchors ────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent.parent.resolve()
CONFIG_PATH  = PROJECT_ROOT / "config.json"
DATA_DIR     = PROJECT_ROOT / "data"
REPORTS_DIR  = DATA_DIR / "reports"

DATA_DIR.mkdir(exist_ok=True)
REPORTS_DIR.mkdir(exist_ok=True)

# ── Live config ───────────────────────────────────────────────────────────────
CFG: dict = load_config()

# ── Error status tokens ───────────────────────────────────────────────────────
ERROR_STATUSES = {"Error", "Timeout", "Other"}
ERROR_PREFIXES = ("GSC Error", "Error:", "Error ", "Browser Error", "Playwright Error")

# ── SSE subscriber pools ──────────────────────────────────────────────────────
_sub_lock: threading.Lock = threading.Lock()
index_subscribers: list[queue.Queue] = []
audit_subscribers:  list[queue.Queue] = []


class _BroadcastQueue:
    """Fan-out adapter: `.put(msg)` delivers to all live subscriber queues."""

    def __init__(self, subs: list[queue.Queue]) -> None:
        self._subs = subs

    def put(self, msg: object) -> None:
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


index_queue = _BroadcastQueue(index_subscribers)
audit_queue  = _BroadcastQueue(audit_subscribers)


def subscribe(subs: list[queue.Queue]) -> queue.Queue:
    q: queue.Queue = queue.Queue(maxsize=1000)
    with _sub_lock:
        subs.append(q)
    return q


def unsubscribe(subs: list[queue.Queue], q: queue.Queue) -> None:
    with _sub_lock:
        try:
            subs.remove(q)
        except ValueError:
            pass


def _cleanup_subscribers() -> None:
    """Daemon thread: drop stale (full) SSE queues every 5 minutes."""
    import time
    while True:
        time.sleep(300)
        with _sub_lock:
            for subs in (index_subscribers, audit_subscribers):
                subs[:] = [q for q in subs if not q.full()]


threading.Thread(
    target=_cleanup_subscribers, daemon=True, name="sse-cleanup"
).start()

# ── Run status ────────────────────────────────────────────────────────────────
index_status: dict = {"running": False, "total": 0, "done": 0}
audit_status:  dict = {"running": False, "total": 0, "done": 0}

audit_cancel  = threading.Event()
index_cancel  = threading.Event()
state_lock    = threading.Lock()

last_index_run: dict[str, str] = {}  # {url: status} — updated live

index_paused = threading.Event()
index_paused.set()   # set = running (not paused)

audit_paused = threading.Event()
audit_paused.set()

audit_partial:       list[dict] = []
audit_full_results:  list[dict] = []


# ── Helpers ───────────────────────────────────────────────────────────────────

def snapshot_last_index_run() -> dict[str, str]:
    with state_lock:
        return dict(last_index_run)


def reset_last_index_run() -> None:
    with state_lock:
        last_index_run.clear()


def update_last_index_run(url: str, status: str) -> None:
    with state_lock:
        last_index_run[url] = status


def replace_last_index_run(results: dict[str, str]) -> None:
    with state_lock:
        last_index_run.clear()
        last_index_run.update(results)


def reload_cfg() -> None:
    """Reload config.json into the global CFG dict in-place (preserves references)."""
    global CFG
    CFG = load_config()
