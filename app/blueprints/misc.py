"""Miscellaneous routes that don't fit any larger group.

Includes:

* ``GET /app`` — the dashboard SPA shell (HTML render)
* ``GET /health`` — public liveness probe (intentionally minimal)
* ``GET /health/ready`` — deeper readiness probe (data dir writable, etc.)
* ``GET /api/use_cases`` — registered audit use cases
* ``GET /api/tasks`` — registered audit tasks
* ``GET /openapi.yaml`` — OpenAPI 3.1 spec (raw YAML)
* ``GET /docs`` — Swagger UI viewer for the spec
"""

from __future__ import annotations

from pathlib import Path

from flask import Blueprint, jsonify

from app.state import DATA_DIR, PROJECT_ROOT, REPORTS_DIR, TEMPLATE_DIR, UPLOAD_DIR
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


# ── OpenAPI spec + Swagger UI ─────────────────────────────────────────────────

_OPENAPI_SPEC_PATH = PROJECT_ROOT / "docs" / "openapi.yaml"

_SWAGGER_UI_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>SEO Suite API · Docs</title>
  <link rel="stylesheet" href="https://unpkg.com/swagger-ui-dist@5/swagger-ui.css">
  <style>
    body { margin: 0; }
    .topbar { display: none; }
  </style>
</head>
<body>
  <div id="swagger-ui"></div>
  <script src="https://unpkg.com/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
  <script>
    window.onload = () => {
      SwaggerUIBundle({
        url: '/openapi.yaml',
        dom_id: '#swagger-ui',
        deepLinking: true,
        docExpansion: 'list',
        defaultModelsExpandDepth: -1,
      });
    };
  </script>
</body>
</html>"""


@bp.route("/openapi.yaml")
def openapi_spec():
    """Serve the OpenAPI 3.1 spec as YAML. Unauthenticated — public API docs."""
    if not _OPENAPI_SPEC_PATH.is_file():
        return "OpenAPI spec not found", 404
    return (
        _OPENAPI_SPEC_PATH.read_text(encoding="utf-8"),
        200,
        {"Content-Type": "application/yaml; charset=utf-8"},
    )


@bp.route("/docs")
def api_docs():
    """Swagger UI viewer for the OpenAPI spec at /openapi.yaml.

    Unauthenticated so integrators can discover the API without an account.
    The UI itself just renders the spec — no auth is granted.

    Returns a relaxed CSP allowing the unpkg.com CDN for the Swagger UI
    bundle. This only affects this route; every other response keeps the
    default CSP from app/middleware.py.
    """
    import secrets
    nonce = secrets.token_hex(16)
    html = _SWAGGER_UI_HTML.replace("<script>", f'<script nonce="{nonce}">')
    return (
        html,
        200,
        {
            "Content-Type": "text/html",
            "Content-Security-Policy": (
                "default-src 'self'; "
                f"script-src 'self' 'nonce-{nonce}' https://unpkg.com; "
                "style-src 'self' 'unsafe-inline' https://unpkg.com; "
                "img-src 'self' data: https://unpkg.com; "
                "connect-src 'self'"
            ),
        },
    )


def register(app) -> None:
    app.register_blueprint(bp)
