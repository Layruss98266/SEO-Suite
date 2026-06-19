"""Flask blueprints for the SEO Suite app.

Route groups live here as separate blueprints so each module owns a coherent
slice of the URL space. Each blueprint module exposes a single ``bp`` symbol
(or a ``register(app, limiter)`` factory for blueprints that need limiter
access) which ``app/server.py`` imports and registers on the Flask app.
"""

from __future__ import annotations

from typing import Tuple

from flask import Response, jsonify


def api_error(msg: str, status: int = 400) -> Tuple[Response, int]:
    """Return the canonical JSON error response ``{"ok": False, "error": msg}``.

    Audit item C25: all API endpoints should use this single shape so SPA
    fetch wrappers and integrators only have to handle one error format.
    """
    return jsonify({"ok": False, "error": msg}), status


__all__ = ["api_error"]
