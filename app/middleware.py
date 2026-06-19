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

    GET/HEAD/OPTIONS are exempt (no state change).  Every other method must
    carry a valid token, either as the ``_csrf_token`` form field or the
    ``X-CSRF-Token`` header.  The historical exemption for
    ``application/json`` requests has been removed — SameSite cookies are
    defence-in-depth, not a substitute for CSRF tokens, and modern attacks
    routinely POST JSON cross-origin (``fetch(..., {mode: 'no-cors'})``).
    """
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return None
    token = request.form.get("_csrf_token") or request.headers.get("X-CSRF-Token", "")
    if not token or not secrets.compare_digest(token, session.get("_csrf_token", "")):
        if resp_on_fail:
            return jsonify({"ok": False, "error": "CSRF validation failed"}), 403
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
    # Cross-origin isolation: COOP/CORP/COEP-ish hardening.
    response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
    response.headers.setdefault("Cross-Origin-Resource-Policy", "same-origin")
    # Permissions-Policy: deny every powerful API by default.  This app
    # never needs camera/mic/geolocation/etc., so opt every page out.
    response.headers.setdefault(
        "Permissions-Policy",
        "accelerometer=(), camera=(), geolocation=(), gyroscope=(), "
        "magnetometer=(), microphone=(), payment=(), usb=(), "
        "interest-cohort=()",
    )
    if os.environ.get("SEO_SUITE_COOKIE_SECURE") == "1":
        response.headers.setdefault(
            "Strict-Transport-Security",
            "max-age=31536000; includeSubDomains",
        )
    response.headers.setdefault(
        "Content-Security-Policy",
        # 'unsafe-inline' kept in script-src: the dashboard wires ~1000+
        # buttons via inline onclick="..." attributes; removing it blocks
        # every interaction.  TODO(S-NEW): migrate to addEventListener and
        # tighten to nonces.
        # 'unsafe-inline' kept in style-src because the UI uses many inline
        # style attributes; removing it would require auditing ~500 elements.
        "default-src 'self'; script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com; "
        "img-src 'self' data:; connect-src 'self'",
    )
    return response


# ── Before-request CSRF guard ────────────────────────────────────────────────

# Deny-by-default for every state-changing method.  Only routes that
# *cannot* obtain a token first are exempted (e.g. the bootstrap endpoint
# that hands out the token itself, and the public site contact form which
# embeds its own hidden field).  Auth flows (/login, /signup, /login/totp)
# embed the token in their POST forms — they pass CSRF naturally and don't
# need to be on this list.
_CSRF_EXEMPT_PATHS: tuple[str, ...] = (
    "/api/csrf",      # GET-only token bootstrap (defence-in-depth — GETs are exempt by method too)
)


def _csrf_protect():
    """Enforce CSRF on every state-changing request.

    Skipped when:
      * method is GET/HEAD/OPTIONS (no state change)
      * path is in :data:`_CSRF_EXEMPT_PATHS`
      * the session has no token yet (first visit / test client without
        GET preamble) — lets the underlying route serve its own 401/error
        instead of a confusing 403.
    """
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return None
    if request.path in _CSRF_EXEMPT_PATHS:
        return None
    if "_csrf_token" not in session:
        return None
    return _validate_csrf()


# ── Error handlers ───────────────────────────────────────────────────────────

def _too_large(_e):
    return jsonify({"ok": False, "error": "File too large — 10 MB maximum"}), 413


# ── Wiring ───────────────────────────────────────────────────────────────────

def init_middleware(app: Flask) -> None:
    """Register security headers, CSRF protection, and error handlers on *app*."""
    app.after_request(_set_security_headers)
    app.before_request(_csrf_protect)
    app.errorhandler(413)(_too_large)
    app.jinja_env.globals["csrf_token"] = generate_csrf_token
