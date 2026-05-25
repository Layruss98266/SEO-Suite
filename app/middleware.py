"""
Flask middleware for the SEO Suite app: security headers, CSRF token plumbing,
and shared error handlers.

Everything in this module is wired in via :func:`init_middleware`, called from
the app factory after the Flask instance exists. Keeping these handlers out of
``app/server.py`` lets the main module focus on app construction and route
registration.
"""

from __future__ import annotations

import os
import secrets

from flask import Flask, jsonify, request, session


# ── CSRF token plumbing ──────────────────────────────────────────────────────

def generate_csrf_token() -> str:
    """Return the session's CSRF token, lazily creating it on first access.

    Exposed to Jinja as ``csrf_token`` so templates can render hidden inputs:
    ``<input type="hidden" name="_csrf_token" value="{{ csrf_token() }}">``.
    """
    if "_csrf_token" not in session:
        session["_csrf_token"] = secrets.token_hex(32)
    return session["_csrf_token"]


def _validate_csrf(resp_on_fail: bool = True):
    """Return an error response if the current request fails CSRF check.

    GET/HEAD/OPTIONS are exempt (no state change). JSON API requests are also
    exempt because they're protected by SameSite cookies and the JSON content
    type forbids cross-origin form submission.
    """
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return None
    if request.path.startswith("/api/") and request.is_json:
        return None
    token = request.form.get("_csrf_token") or request.headers.get("X-CSRF-Token", "")
    if not token or not secrets.compare_digest(token, session.get("_csrf_token", "")):
        if resp_on_fail:
            return jsonify({"error": "CSRF validation failed"}), 403
    return None


# ── Security headers ─────────────────────────────────────────────────────────

def _set_security_headers(response):
    """Apply defensive HTTP headers to every response.

    ``setdefault`` so a route can opt out (e.g. for specific HTML responses
    needing a relaxed CSP). HSTS is only sent under HTTPS to avoid breaking
    local dev which serves over plain HTTP.
    """
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("X-XSS-Protection", "1; mode=block")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    if os.environ.get("SEO_SUITE_COOKIE_SECURE") == "1":
        response.headers.setdefault(
            "Strict-Transport-Security",
            "max-age=31536000; includeSubDomains",
        )
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com; "
        "img-src 'self' data:; connect-src 'self'",
    )
    return response


# ── Before-request CSRF guard ────────────────────────────────────────────────

_CSRF_PROTECTED_PATHS = ("/login", "/signup", "/contact")


def _csrf_protect():
    """Enforce CSRF on POST submissions to form endpoints.

    Skipped when the session has no token yet (first visit / test client
    without GET preamble) so the route can still serve its own 401/error
    response instead of being short-circuited with a 403.
    """
    if request.method == "POST" and request.path in _CSRF_PROTECTED_PATHS:
        if "_csrf_token" in session:
            result = _validate_csrf()
            if result:
                return result
    return None


# ── Error handlers ───────────────────────────────────────────────────────────

def _too_large(_e):
    return jsonify({"error": "File too large — 10 MB maximum"}), 413


# ── Wiring ───────────────────────────────────────────────────────────────────

def init_middleware(app: Flask) -> None:
    """Register security headers, CSRF protection, and error handlers on *app*."""
    app.after_request(_set_security_headers)
    app.before_request(_csrf_protect)
    app.errorhandler(413)(_too_large)
    app.jinja_env.globals["csrf_token"] = generate_csrf_token
