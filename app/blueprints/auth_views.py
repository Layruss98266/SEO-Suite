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
    change_password,
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
        # Pass IP + UA so authenticate() can record them in login_attempts.
        identity = authenticate(
            username,
            password,
            ip=request.remote_addr,
            user_agent=(request.user_agent.string if request.user_agent else None),
        )
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


# ── Password reset (forgot password flow) ────────────────────────────────────
@bp.route("/api/auth/request_password_reset", methods=["POST"])
def api_request_password_reset():
    """Email a single-use reset link to the user.

    Anti-enumeration: ALWAYS returns 200 + the same message regardless of
    whether the username exists. A user-existence oracle is too useful to
    an attacker. We log internally and only actually send mail when the
    account is real.
    """
    data = request.get_json(force=True) or {}
    username = (data.get("username") or "").strip()
    generic_response = jsonify(
        {
            "ok": True,
            "message": (
                "If that account exists, a password reset link has been sent. "
                "Check your inbox (and spam folder)."
            ),
        }
    )
    if not username:
        return generic_response

    from app import state
    from core import db as _db
    from core.auth import _USERS_DB
    from core.notifier import NotificationService

    if not _use_sqlite_login_history():
        # Tokens are stored in SQLite — reset isn't supported on the JSON backend.
        logger.warning("Password reset attempted with JSON backend — no-op")
        return generic_response

    users = _db.load_users(_USERS_DB)
    if username not in users:
        # Burn time so timing doesn't leak existence (auth.py uses dummy
        # hashing for the same reason).
        import time as _time

        _time.sleep(0.05)
        return generic_response

    # Username doubles as email when it contains "@". This is the common SaaS
    # pattern. If your usernames aren't email addresses you'd need a separate
    # email column on users — out of scope here.
    if "@" not in username:
        logger.warning("Password reset for %s skipped: username is not an email", username)
        return generic_response

    try:
        raw_token = _db.issue_auth_token(_USERS_DB, username, "password_reset", ttl_seconds=3600)
    except Exception as exc:
        logger.error("Failed to issue password reset token for %s: %s", username, exc)
        return generic_response

    reset_path = f"/reset_password?token={raw_token}"
    body = f"""
    <h2>Password reset for SEO Suite</h2>
    <p>We received a request to reset your password. Click the link below to set a new one.
    This link expires in 1 hour and can only be used once.</p>
    <p><a href="{reset_path}">{reset_path}</a></p>
    <p>If you didn't request this, ignore the email — your password hasn't changed.</p>
    """
    svc = NotificationService(state.CFG)
    svc.send_email_to(username, "Reset your SEO Suite password", body)
    return generic_response


@bp.route("/api/auth/reset_password", methods=["POST"])
def api_reset_password():
    """Consume a reset token and set a new password.

    Token is single-use: a successful reset OR an attempted reset with a
    consumed/expired token both make the token invalid afterward.
    """
    data = request.get_json(force=True) or {}
    token = (data.get("token") or "").strip()
    new_password = data.get("new_password") or ""

    if not token or not new_password:
        return jsonify({"ok": False, "error": "token and new_password required"}), 400

    from core import db as _db
    from core.auth import _MIN_PASSWORD_LEN, _USERS_DB, _hash_password
    from core.password_policy import validate_new_password

    if len(new_password) < _MIN_PASSWORD_LEN:
        return jsonify(
            {"ok": False, "error": f"Password must be at least {_MIN_PASSWORD_LEN} characters"}
        ), 400

    username = _db.consume_auth_token(_USERS_DB, token, "password_reset")
    if not username:
        return jsonify({"ok": False, "error": "Invalid or expired reset token"}), 400

    pol_ok, pol_err = validate_new_password(new_password, username=username)
    if not pol_ok:
        # Token was already consumed by this point. That's fine — user just
        # has to request a fresh one. Prevents bypassing the policy by
        # rapid-fire submissions until a weak one slips through.
        return jsonify({"ok": False, "error": pol_err}), 400

    if not _db.reset_password_hash(_USERS_DB, username, _hash_password(new_password)):
        return jsonify({"ok": False, "error": "Password reset failed"}), 500

    logger.info("Password reset successful for %s", username)
    return jsonify({"ok": True, "message": "Password updated — you can now log in."})


# ── Email verification ────────────────────────────────────────────────────────
@bp.route("/api/auth/send_verification", methods=["POST"])
@login_required
def api_send_verification():
    """Email a fresh verification link to the current user. Always returns 200."""
    me = session.get("username") or ""
    if not me or "@" not in me:
        return jsonify({"ok": False, "error": "Your account isn't an email address"}), 400

    from app import state
    from core import db as _db
    from core.auth import _USERS_DB
    from core.notifier import NotificationService

    if _db.get_email_verified(_USERS_DB, me):
        return jsonify({"ok": True, "message": "Email is already verified"})

    try:
        raw_token = _db.issue_auth_token(_USERS_DB, me, "email_verify", ttl_seconds=86400)
    except Exception as exc:
        logger.error("Failed to issue verification token for %s: %s", me, exc)
        return jsonify({"ok": False, "error": "Could not issue verification token"}), 500

    verify_path = f"/verify_email?token={raw_token}"
    body = f"""
    <h2>Verify your SEO Suite email</h2>
    <p>Click the link below to confirm your email address. The link expires in 24 hours.</p>
    <p><a href="{verify_path}">{verify_path}</a></p>
    <p>If you didn't sign up for SEO Suite, ignore this email.</p>
    """
    svc = NotificationService(state.CFG)
    sent = svc.send_email_to(me, "Verify your SEO Suite email", body)
    return jsonify({"ok": True, "sent": sent, "message": "Verification email sent (if SMTP is configured)"})


@bp.route("/api/auth/verify_email", methods=["POST"])
def api_verify_email():
    """Consume an email-verify token and mark the account as verified."""
    data = request.get_json(force=True) or {}
    token = (data.get("token") or "").strip()
    if not token:
        return jsonify({"ok": False, "error": "token required"}), 400

    from core import db as _db
    from core.auth import _USERS_DB

    username = _db.consume_auth_token(_USERS_DB, token, "email_verify")
    if not username:
        return jsonify({"ok": False, "error": "Invalid or expired verification token"}), 400

    _db.set_email_verified(_USERS_DB, username, True)
    return jsonify({"ok": True, "message": "Email verified", "username": username})


# ── Password change ───────────────────────────────────────────────────────────
@bp.route("/api/auth/change_password", methods=["POST"])
@login_required
def api_change_password():
    """Change the current user's own password.

    Requires the current password (so a stolen session cookie alone can't
    permanently take over an account). The env admin is rejected — their
    hash lives in ``SEO_SUITE_PASSWORD_HASH`` and must be rotated out-of-band.
    """
    data = request.get_json(force=True) or {}
    current = data.get("current_password") or ""
    new = data.get("new_password") or ""
    me = session.get("username") or ""

    if not me:
        return jsonify({"ok": False, "error": "Not logged in"}), 401
    if not current or not new:
        return jsonify({"ok": False, "error": "current_password and new_password required"}), 400

    ok, err = change_password(me, current, new)
    if not ok:
        # Don't leak whether the failure was a bad current pw vs a policy
        # violation — but we do echo the policy errors (length, "same as old")
        # because those are clearly NOT a credential-validation result.
        status = 400 if err and "password" not in err.lower() or "differ" in (err or "").lower() else 401
        return jsonify({"ok": False, "error": err}), status
    return jsonify({"ok": True, "message": "Password updated"})


# ── Login history (audit trail) ───────────────────────────────────────────────
@bp.route("/api/auth/login_history")
@admin_required
def api_login_history():
    """Admin-only: list recent login attempts across all users.

    Query params:
      * ``username`` — filter to one account
      * ``failures_only=1`` — return only failed attempts (brute-force scan)
      * ``limit`` — cap rows (default 100, max 500)
    """
    if not _use_sqlite_login_history():
        return jsonify({"ok": False, "error": "Login history requires the SQLite backend"}), 503

    from core import db as _db
    from core.auth import _USERS_DB

    username = (request.args.get("username") or "").strip() or None
    failures_only = request.args.get("failures_only") in ("1", "true", "yes")
    try:
        limit = max(1, min(int(request.args.get("limit", "100")), 500))
    except (TypeError, ValueError):
        limit = 100

    rows = _db.get_login_history(
        _USERS_DB,
        username=username,
        success=(False if failures_only else None),
        limit=limit,
    )
    return jsonify({"ok": True, "rows": rows, "count": len(rows)})


@bp.route("/api/auth/my_logins")
@login_required
def api_my_logins():
    """Return the current user's own login history (last 50 attempts).

    No admin requirement — every user can see when their own account was
    accessed. Useful for spotting unauthorized access.
    """
    if not _use_sqlite_login_history():
        return jsonify({"ok": False, "error": "Login history requires the SQLite backend"}), 503

    from core import db as _db
    from core.auth import _USERS_DB

    me = session.get("username")
    if not me:
        return jsonify({"ok": False, "error": "Not logged in"}), 401

    rows = _db.get_login_history(_USERS_DB, username=me, limit=50)
    return jsonify({"ok": True, "rows": rows, "count": len(rows)})


def _use_sqlite_login_history() -> bool:
    """Login history only works when the SQLite backend is active."""
    import os as _os

    return _os.environ.get("SEO_SUITE_USERS_BACKEND", "sqlite").lower() != "json"


# ── Auth status / credential helper ───────────────────────────────────────────
@bp.route("/api/auth_status")
@login_required
def api_auth_status():
    """Return current auth configuration state (for Settings → Security card).

    Also surfaces the ``must_rotate_password`` flag so the dashboard can
    pop a banner asking the env admin to set a per-user password and move
    off the env-based credential.
    """
    me = session.get("username") or ""
    from core.auth import _should_force_env_admin_rotation

    return jsonify(
        {
            "auth_enabled": auth_enabled(),
            "username": os.getenv("SEO_SUITE_USERNAME", "admin"),
            "secret_set": bool(os.getenv("SEO_SUITE_SECRET")),
            "must_rotate_password": _should_force_env_admin_rotation(me),
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
