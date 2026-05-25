"""Miscellaneous routes that don't fit any larger group.

Includes:

* ``GET /app`` — the dashboard SPA shell (HTML render)
* ``GET /health`` — public liveness probe (intentionally minimal)
* ``GET /api/use_cases`` — registered audit use cases
* ``GET /api/tasks`` — registered audit tasks
"""

from __future__ import annotations

from flask import Blueprint, jsonify

from app.state import TEMPLATE_DIR
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

    Use authed endpoints (e.g. ``/api/history``) for in-depth status. Probes
    only need a 200 to consider the instance healthy.
    """
    return jsonify({"status": "ok"})


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
