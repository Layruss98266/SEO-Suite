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

import os
from pathlib import Path

from flask import Blueprint, jsonify, session

from app.state import DATA_DIR, PROJECT_ROOT, REPORTS_DIR, TEMPLATE_DIR, UPLOAD_DIR
from core.auth import login_required

bp = Blueprint("misc", __name__)


@bp.route("/app")
@login_required
def app_dashboard():
    from core.version import VERSION
    html = (TEMPLATE_DIR / "dashboard.html").read_text(encoding="utf-8")
    # Cache-bust static assets on every release so browsers don't serve
    # stale JS/CSS after an upgrade.
    html = (
        html
        .replace("/static/js/dashboard.js", f"/static/js/dashboard.js?v={VERSION}")
        .replace("/static/css/dashboard.css", f"/static/css/dashboard.css?v={VERSION}")
    )
    return (html, 200, {"Content-Type": "text/html"})


@bp.route("/health")
def health():
    """Public liveness probe.

    Returns ``{"status": "ok", "version": <VERSION>}``.  The ``version``
    field powers the dashboard cache-bust (``/app`` rewrites static asset
    URLs to ``?v=<VERSION>``) and lets the SPA show the running build in
    the nav logo. Use ``/health/ready`` for deeper readiness checks.
    """
    from core.version import VERSION
    return jsonify({"status": "ok", "version": VERSION})


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


@bp.route("/api/csrf")
def api_csrf():
    """Hand out the session's CSRF token for SPA fetch() calls.

    The dashboard's fetch wrapper calls this once on load and stores the
    token, then injects it as the ``X-CSRF-Token`` header on every
    POST/PUT/PATCH/DELETE.  Unauthenticated because the login form needs
    a token before login completes.
    """
    from app.middleware import generate_csrf_token
    return jsonify({"token": generate_csrf_token()})


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


def _public_docs_enabled() -> bool:
    """Whether unauthenticated visitors may view ``/openapi.yaml`` and ``/docs``.

    Default OFF: the API spec leaks attack surface (every endpoint, every
    parameter shape) to anyone who can reach the host. Operators can flip
    ``SEO_SUITE_PUBLIC_DOCS=1`` when they intentionally want to expose the
    spec to third-party integrators.
    """
    return os.environ.get("SEO_SUITE_PUBLIC_DOCS") == "1"


@bp.route("/openapi.yaml")
def openapi_spec():
    """Serve the OpenAPI 3.1 spec as YAML.

    Authed-only by default — see :func:`_public_docs_enabled`.
    """
    if not _public_docs_enabled() and not session.get("authed"):
        return jsonify({"error": "Not authorized"}), 401
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

    Authed-only by default. Set ``SEO_SUITE_PUBLIC_DOCS=1`` to expose the
    docs publicly when running a developer portal.

    Returns a relaxed CSP allowing the unpkg.com CDN for the Swagger UI
    bundle. This only affects this route; every other response keeps the
    default CSP from app/middleware.py.
    """
    if not _public_docs_enabled() and not session.get("authed"):
        return ("Login required to view API docs.", 401, {"Content-Type": "text/plain"})
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
