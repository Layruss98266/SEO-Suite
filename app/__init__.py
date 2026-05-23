"""
SEO Suite app package.

The Flask application is defined and fully configured (auth, CORS, rate
limiting, Sentry, routes) at import time in ``app.server``. That module is the
single source of truth — ``main.py`` runs it directly via ``from app.server
import app``.

``create_app`` is a thin WSGI-friendly factory that returns that same
configured app, so deployment targets expecting an ``app:create_app`` entry
point work without duplicating configuration.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from flask import Flask


def create_app(config: dict | None = None) -> Flask:
    """Return the configured Flask app from app.server.

    Parameters
    ----------
    config:
        Optional dict of Flask config overrides (useful for testing).
    """
    # Importing app.server runs its module-level setup (Flask instance, auth,
    # CORS, limiter, Sentry, and all @app.route registrations).
    from app.server import app

    if config:
        app.config.update(config)
    return app
