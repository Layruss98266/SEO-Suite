"""Miscellaneous routes that don't fit any larger group.

Includes:

* ``GET /app`` — the dashboard SPA shell (HTML render)
* ``GET /health`` — public liveness probe (intentionally minimal)
* ``GET /health/ready`` — deeper readiness probe (data dir writable, etc.)
* ``GET /api/use_cases`` — registered audit use cases
* ``GET /api/tasks`` — registered audit tasks
"""

from __future__ import annotations

from flask import Blueprint, jsonify

from app.state import DATA_DIR, REPORTS_DIR, TEMPLATE_DIR, UPLOAD_DIR
from core.auth import login_required

bp = Blueprint("misc", __name__)


@bp.route("/app")
@login_required
def app_dashboard():
    return (
        (TEMPLATE_DIR / "dashboard.html").read_text(encoding="utf-8"),
        200,
        {"Content-Type": "text/html"},
    )


@bp.route("/health")
def health():
    """Public, intentionally minimal — no version, no run-state.

    Use ``/health/ready`` or authed endpoints (e.g. ``/api/history``) for
    in-depth status. Liveness probes only need a 200 to consider the instance
    healthy.
    """
    return jsonify({"status": "ok"})


@bp.route("/health/ready")
def health_ready():
    """Readiness probe — checks the things a request actually needs to succeed.

    Returns 200 when all checks pass, 503 when any fail. Each check is best-
    effort; a failure surfaces in the JSON body so operators can see which
    dependency is broken without having to read logs.
    """
    checks = {}
    overall_ok = True

    # Data directory writable
    try:
        probe = DATA_DIR / ".healthcheck"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        checks["data_dir_writable"] = True
    except Exception as e:
        checks["data_dir_writable"] = False
        checks["data_dir_error"] = str(e)
        overall_ok = False

    # Reports and upload directories exist
    checks["reports_dir_exists"] = REPORTS_DIR.exists()
    checks["upload_dir_exists"] = UPLOAD_DIR.exists()
    if not (checks["reports_dir_exists"] and checks["upload_dir_exists"]):
        overall_ok = False

    status = 200 if overall_ok else 503
    return jsonify({"status": "ok" if overall_ok else "degraded", "checks": checks}), status


@bp.route("/api/use_cases")
@login_required
def api_use_cases():
    from core.seo_audit import USE_CASES

    return jsonify(USE_CASES)


@bp.route("/api/tasks")
@login_required
def api_tasks():
    from core.seo_audit import TASKS

    return jsonify(TASKS)


def register(app) -> None:
    app.register_blueprint(bp)
