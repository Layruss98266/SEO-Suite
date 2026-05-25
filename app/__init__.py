"""
SEO Suite app package.

The Flask application is constructed at import time in :mod:`app.server`,
which:

* Creates the Flask instance + wires CORS, rate limiting, Sentry, auth
* Calls :func:`app.middleware.init_middleware` for security headers and CSRF
* Imports shared state from :mod:`app.state` (SSE queues, run status, paths)
* Registers route groups split into Flask blueprints under
  :mod:`app.blueprints` (``site``, ``misc``, ``auth_views``)
* Defines the remaining inline routes (indexing, audit, reports, settings,
  tools — pending further extraction)

``main.py`` runs the app directly via ``from app.server import app``.
:func:`create_app` is a thin WSGI-friendly factory that returns that same
configured app, so deployment targets expecting an ``app:create_app`` entry
point work without duplicating configuration.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from flask import Flask


def create_app(config: dict | None = None) -> Flask:
    """Return the configured Flask app from :mod:`app.server`.

    Parameters
    ----------
    config:
        Optional dict of Flask config overrides (useful for testing).
    """
    # Importing app.server runs its module-level setup: Flask instance, auth,
    # CORS, middleware, limiter, Sentry, blueprint registration, and the
    # inline route definitions.
    from app.server import app

    if config:
        app.config.update(config)
    return app
