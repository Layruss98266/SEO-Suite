"""HTTP routes for authentication and user management.

Covers:

* ``GET/POST /login`` — login form + credential check (rate-limited via :func:`register`)
* ``GET/POST /signup`` — self-registration form (rate-limited via :func:`register`)
* ``GET/POST /logout`` — clears the session
* ``GET/POST /api/users``, ``DELETE /api/users/<u>`` — admin user management
* ``GET /api/auth_status`` — auth configuration snapshot for the Settings UI
* ``POST /api/auth/change_credentials`` — generate an env-admin hash for the
  user to paste into their ``.env`` file

The login form embeds a CSRF token; signup likewise. The :func:`register`
factory wires rate limits to ``login`` and ``signup`` after the blueprint is
attached so the limiter sees the bound view functions.
"""

from __future__ import annotations

import logging
import os

from flask import Blueprint, jsonify, request, session

from app.middleware import generate_csrf_token
from core.auth import (
    LOGIN_PAGE,
    SIGNUP_PAGE,
    _is_locked_out,
    admin_required,
    auth_enabled,
    authenticate,
    create_user,
    delete_user,
    list_users,
    login_required,
    signup_allowed,
)
from core.security import esc

logger = logging.getLogger(__name__)

bp = Blueprint("auth_views", __name__)


# ── Login ─────────────────────────────────────────────────────────────────────
@bp.route("/login", methods=["GET", "POST"])
def login():
    if not auth_enabled():
        # Auth disabled (no SEO_SUITE_PASSWORD_HASH env). Send users straight in.
        return ("", 302, {"Location": "/app"})
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        if _is_locked_out(username):
            page = LOGIN_PAGE.replace(
                "__ERROR__",
                "<div class='err'>Account temporarily locked — try again in 15 minutes</div>",
            )
            return page, 429, {"Content-Type": "text/html"}
        identity = authenticate(username, password)
        if identity:
            session.clear()
            session["authed"] = True
            session["username"] = identity["username"]
            session["is_admin"] = identity["is_admin"]
            session.permanent = True
            # Honour ?next= so login_required can bounce users back to their
            # original destination (e.g. /app). Validate strictly: must be a
            # relative path starting with / and must not start with // (which
            # browsers treat as a protocol-relative URL, enabling open-redirect).
            _next = request.form.get("next") or request.args.get("next") or ""
            _next = _next.strip()
            if _next and _next.startswith("/") and not _next.startswith("//"):
                dest = _next
            else:
                dest = "/app"
            return ("", 302, {"Location": dest})
        page = LOGIN_PAGE.replace("__ERROR__", "<div class='err'>Invalid credentials</div>")
        return page, 401, {"Content-Type": "text/html"}
    # GET — embed ?next= and CSRF token into the form as hidden fields.
    _next = request.args.get("next", "")
    _next = _next.strip() if (_next.startswith("/") and not _next.startswith("//")) else ""
    hidden = f'<input type="hidden" name="_csrf_token" value="{generate_csrf_token()}">'
    if _next:
        hidden += f'\n      <input type="hidden" name="next" value="{esc(_next)}">'
    page = LOGIN_PAGE.replace("__NEXT__", hidden).replace("__ERROR__", "")
    return page, 200, {"Content-Type": "text/html"}


# ── Signup ────────────────────────────────────────────────────────────────────
@bp.route("/signup", methods=["GET", "POST"])
def signup():
    if not signup_allowed():
        return ("Signups are disabled.", 403, {"Content-Type": "text/plain"})
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        confirm = request.form.get("confirm") or ""
        if password != confirm:
            page = SIGNUP_PAGE.replace(
                "__ERROR__", "<div class='err'>Passwords do not match</div>"
            )
            return page, 400, {"Content-Type": "text/html"}
        ok, err = create_user(username, password)
        if not ok:
            page = SIGNUP_PAGE.replace("__ERROR__", f"<div class='err'>{esc(err)}</div>")
            return page, 400, {"Content-Type": "text/html"}
        # Auto-login the new account so the first signup isn't locked out.
        identity = authenticate(username, password)
        session.clear()
        session["authed"] = True
        session["username"] = identity["username"]
        session["is_admin"] = identity["is_admin"]
        session.permanent = True
        return ("", 302, {"Location": "/app"})
    csrf_field = f'<input type="hidden" name="_csrf_token" value="{generate_csrf_token()}">'
    page = SIGNUP_PAGE.replace("__ERROR__", csrf_field)
    return page, 200, {"Content-Type": "text/html"}


# ── Logout ────────────────────────────────────────────────────────────────────
@bp.route("/logout", methods=["POST", "GET"])
def logout():
    session.clear()
    return ("", 302, {"Location": "/login"})


# ── User management (admin only) ──────────────────────────────────────────────
@bp.route("/api/users", methods=["GET"])
@admin_required
def api_users_list():
    return jsonify(
        {
            "ok": True,
            "users": list_users(),
            "me": session.get("username"),
            "signup_allowed": signup_allowed(),
        }
    )


@bp.route("/api/users", methods=["POST"])
@admin_required
def api_users_create():
    data = request.get_json(force=True) or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    is_admin = bool(data.get("is_admin"))
    ok, err = create_user(username, password, is_admin=is_admin)
    if not ok:
        return jsonify({"ok": False, "error": err}), 400
    return jsonify({"ok": True, "users": list_users()})


@bp.route("/api/users/<username>", methods=["DELETE"])
@admin_required
def api_users_delete(username):
    if username == session.get("username"):
        return jsonify({"ok": False, "error": "You cannot delete your own account"}), 400
    ok, err = delete_user(username)
    if not ok:
        return jsonify({"ok": False, "error": err}), 400
    return jsonify({"ok": True, "users": list_users()})


# ── Auth status / credential helper ───────────────────────────────────────────
@bp.route("/api/auth_status")
@login_required
def api_auth_status():
    """Return current auth configuration state (for Settings → Security card)."""
    return jsonify(
        {
            "auth_enabled": auth_enabled(),
            "username": os.getenv("SEO_SUITE_USERNAME", "admin"),
            "secret_set": bool(os.getenv("SEO_SUITE_SECRET")),
        }
    )


@bp.route("/api/auth/change_credentials", methods=["POST"])
@login_required
def api_auth_change_credentials():
    """Generate a new password hash and return it for the user to paste into .env.

    We intentionally do NOT write to ``.env`` automatically — env changes must
    be explicit and deliberate. The hash is returned in the response so the
    user can update ``SEO_SUITE_USERNAME`` / ``SEO_SUITE_PASSWORD_HASH``
    themselves and restart the server.
    """
    from werkzeug.security import generate_password_hash

    data = request.get_json(force=True) or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    if not username:
        return jsonify({"ok": False, "error": "username required"}), 400
    if len(password) < 12:
        return (
            jsonify({"ok": False, "error": "password must be at least 12 characters"}),
            400,
        )
    pw_hash = generate_password_hash(password)
    logger.info("Credential change requested for username: %s", username)
    return jsonify(
        {
            "ok": True,
            "message": "Hash generated — update your .env file with these values and restart the server",
            "env_snippet": (
                f"SEO_SUITE_USERNAME={username}\n"
                f"SEO_SUITE_PASSWORD_HASH={pw_hash}"
            ),
        }
    )


def register(app, limiter) -> None:
    """Register the blueprint and wire login/signup rate limits.

    Rate limits target the bound view functions, which only exist after
    blueprint registration — hence the factory-style wiring.
    """
    app.register_blueprint(bp)
    limiter.limit("5 per minute")(app.view_functions["auth_views.login"])
    limiter.limit("10 per minute")(app.view_functions["auth_views.signup"])
