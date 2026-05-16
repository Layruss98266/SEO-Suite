"""
SEO Suite Flask application factory.

Usage:
    from app import create_app
    app = create_app()

Architecture notes:
    Routes currently live in app/server.py (monolith, ~2 200 lines).
    app/routes/ holds blueprint stubs ready for incremental migration —
    move a route section from server.py into its blueprint file, uncomment
    the matching line in app/routes/__init__.py, and delete the old block.

    Shared mutable state (queues, run status, config) lives in app/state.py
    so both the current server.py and future blueprints import from one place.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path


def create_app(config: dict | None = None) -> "Flask":  # type: ignore[name-defined]
    """Create and configure the Flask application.

    Parameters
    ----------
    config:
        Optional dict of Flask config overrides (useful for testing).
    """
    import os
    import logging
    from flask import Flask
    from flask_cors import CORS
    from flask_limiter import Limiter
    from flask_limiter.util import get_remote_address

    from core.version import VERSION
    from core.auth import init_auth
    from core.checker import load_config

    # ── Paths ─────────────────────────────────────────────────────────────────
    _here = Path(__file__).parent
    template_dir = _here / "templates"
    static_dir   = _here / "static"

    # ── Logging ───────────────────────────────────────────────────────────────
    data_dir = _here.parent / "data"
    data_dir.mkdir(exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(data_dir / "app.log", encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )

    # ── App ───────────────────────────────────────────────────────────────────
    app = Flask(
        __name__,
        template_folder=str(template_dir),
        static_folder=str(static_dir),
    )
    app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024  # 10 MB upload cap

    if config:
        app.config.update(config)

    # ── Auth ──────────────────────────────────────────────────────────────────
    init_auth(app)

    # ── CORS ──────────────────────────────────────────────────────────────────
    _cors_origins = [
        o.strip()
        for o in os.getenv(
            "CORS_ALLOWED_ORIGINS",
            "http://localhost:8080,http://127.0.0.1:8080",
        ).split(",")
        if o.strip()
    ]
    CORS(app, origins=_cors_origins, supports_credentials=True)

    # ── Rate limiting ─────────────────────────────────────────────────────────
    Limiter(
        app=app,
        key_func=get_remote_address,
        default_limits=[],
        storage_uri="memory://",
    )

    # ── Sentry (opt-in) ───────────────────────────────────────────────────────
    _sentry_dsn = os.getenv("SENTRY_DSN", "")
    if _sentry_dsn:
        import sentry_sdk
        from sentry_sdk.integrations.flask import FlaskIntegration
        sentry_sdk.init(
            dsn=_sentry_dsn,
            integrations=[FlaskIntegration()],
            traces_sample_rate=0.05,
            environment=os.getenv("SEO_SUITE_ENV", "development"),
        )

    # ── Blueprints (uncomment as routes are migrated from server.py) ──────────
    from app.routes import register_blueprints
    register_blueprints(app)

    # ── Temporary: mount monolith server routes ───────────────────────────────
    # Once all route sections are migrated to blueprints, this import can be
    # removed and server.py reduced to the shared-state and helper layer only.
    with app.app_context():
        import app.server  # noqa: F401  — registers @app.route decorators

    return app
