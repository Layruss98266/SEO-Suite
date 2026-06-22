"""HTTP routes for authentication and user management.

Covers:

* ``GET/POST /login`` — login form + credential check (rate-limited via :func:`register`)
* ``GET/POST /signup`` — self-registration form (rate-limited via :func:`register`)
* ``GET/POST /logout`` — clears the session
* ``GET/POST /api/users``, ``DELETE /api/users/<u>`` — admin user management
* ``GET /api/me`` — current user identity + admin flag
* ``GET /api/auth_status`` — auth configuration snapshot for the Settings UI
* ``POST /api/auth/change_credentials`` — generate an env-admin hash for the
  user to paste into their ``.env`` file

The login form embeds a CSRF token; signup likewise. The :func:`register`
factory wires rate limits to ``login`` and ``signup`` after the blueprint is
attached so the limiter sees the bound view functions.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone

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


def _safe_next(value: str | None) -> str:
    """Validate a ``next`` redirect target against open-redirect vectors.

    Returns the value unchanged when it is a safe same-origin relative path,
    otherwise returns ``"/"``. Blocks:

    * empty / missing values
    * values that don't start with ``/`` (absolute URLs like ``https://evil``)
    * values starting with ``//`` (protocol-relative URLs → browsers resolve
      to ``//evil.com`` as ``https://evil.com``)
    * values containing ``\\`` (Windows-style path separators that some
      browsers normalise into ``/``, enabling ``/\\evil.com``)
    * values containing ``://`` anywhere (defence-in-depth against
      ``/redirect?to=http://evil`` style payloads if the value is later
      concatenated into another URL)
    """
    if not value:
        return "/"
    v = value.strip()
    if (
        not v
        or not v.startswith("/")
        or v.startswith("//")
        or "\\" in v
        or "://" in v
    ):
        return "/"
    return v


@bp.before_app_request
def _enforce_server_side_session():
    """Drop the cookie session if its server-side row no longer exists.

    Triggered on every request (across all blueprints). If the user has an
    ``authed=True`` cookie but the DB row was deleted (logout from another
    device, password change, admin revoke), we clear the cookie so the next
    auth check returns 401.

    No-op when ``sid`` is missing (e.g. user logged in before the
    server-side session feature shipped, or the SQLite backend is disabled).
    """
    sid = session.get("sid")
    if not sid or not session.get("authed"):
        return
    if not _use_sqlite_login_history():
        return
    try:
        from core import db as _db
        from core.auth import _USERS_DB

        if _db.validate_session(_USERS_DB, sid) is None:
            session.clear()
    except Exception as exc:
        logger.debug("session validation failed: %s", exc)


# ── Login ─────────────────────────────────────────────────────────────────────
@bp.route("/login", methods=["GET", "POST"])
def login():
    if not auth_enabled():
        # Auth disabled (no SEO_SUITE_PASSWORD_HASH env). Send users straight in.
        return ("", 302, {"Location": "/app"})
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        # Build the CSRF hidden field now — needed for any error re-render so the
        # next submission passes the CSRF check (the field must be present even on
        # error pages; omitting it causes a 403 on the second attempt).
        _csrf_hidden = f'<input type="hidden" name="_csrf_token" value="{generate_csrf_token()}">'
        _next_val = _safe_next(request.form.get("next"))
        if _next_val != "/":
            _csrf_hidden += f'\n      <input type="hidden" name="next" value="{esc(_next_val)}">'
        if _is_locked_out(username):
            page = (
                LOGIN_PAGE
                .replace("__NEXT__", _csrf_hidden)
                .replace("__ERROR__", "<div class='err'>Account temporarily locked — try again in 15 minutes</div>")
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

            # 2FA gate: if the account has TOTP enabled, don't grant full
            # session yet. Stash the username + intended state in a
            # half-session and redirect to /login/totp for the second step.
            # The half-session has NO `authed=True` so it can't access
            # anything @login_required.
            if identity.get("totp_required"):
                session["pending_username"] = identity["username"]
                session["pending_is_admin"] = identity["is_admin"]
                return ("", 302, {"Location": "/login/totp"})

            session["authed"] = True
            session["username"] = identity["username"]
            session["is_admin"] = identity["is_admin"]
            session.permanent = True
            # Re-seed the CSRF token after session.clear() so the very next
            # POST is protected — without this, there's a window between
            # login and the SPA's /api/csrf bootstrap where the deny-by-
            # default middleware (S2) skips its check (no token in session).
            generate_csrf_token()
            if identity.get("must_rotate_password"):
                session["must_rotate_password"] = True

            # Server-side session row. The cookie is a signed pointer; the
            # row controls revocation. If creation fails (e.g. SQLite
            # backend disabled or unavailable), fall through with cookie-only
            # auth so we don't lock the user out — they just can't use the
            # "sign out everywhere" UI.
            try:
                if _use_sqlite_login_history():
                    from core import db as _db
                    from core.auth import _USERS_DB

                    sid = _db.create_session(
                        _USERS_DB,
                        identity["username"],
                        request.remote_addr,
                        request.user_agent.string if request.user_agent else None,
                    )
                    session["sid"] = sid
            except Exception as exc:
                logger.warning("Could not create server-side session row: %s", exc)
            # Honour ?next= so login_required can bounce users back to their
            # original destination (e.g. /app). Validate strictly: must be a
            # relative path starting with / and must not start with // (which
            # browsers treat as a protocol-relative URL, enabling open-redirect).
            _next = _safe_next(request.form.get("next") or request.args.get("next"))
            dest = _next if _next != "/" else "/app"
            return ("", 302, {"Location": dest})
        page = (
            LOGIN_PAGE
            .replace("__NEXT__", _csrf_hidden)
            .replace("__ERROR__", "<div class='err'>Invalid credentials</div>")
        )
        return page, 401, {"Content-Type": "text/html"}
    # GET — embed ?next= and CSRF token into the form as hidden fields.
    _next = _safe_next(request.args.get("next"))
    hidden = f'<input type="hidden" name="_csrf_token" value="{generate_csrf_token()}">'
    if _next != "/":
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
        # On cloud hosts, never auto-login: account farming becomes profitable
        # if a single POST yields a logged-in session.  Force the new account
        # through a real /login round-trip so the limiter sees both events.
        # Local/single-tenant installs keep the convenience auto-login.
        from core.auth import _on_cloud_host
        if _on_cloud_host():
            return ("", 302, {"Location": "/login?signed_up=1"})
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
@bp.route("/logout", methods=["POST"])
def logout():
    """Clear the Flask session cookie AND delete the server-side session row.

    The row deletion is the key part: even if a stolen cookie is replayed
    after logout, the session lookup will return None and the request fails.
    """
    sid = session.get("sid")
    if sid and _use_sqlite_login_history():
        try:
            from core import db as _db
            from core.auth import _USERS_DB

            _db.delete_session(_USERS_DB, sid)
        except Exception as exc:
            logger.debug("delete_session on logout failed: %s", exc)
    session.clear()
    return ("", 302, {"Location": "/login"})


# ── Server-side session management ───────────────────────────────────────────
@bp.route("/api/auth/sessions", methods=["GET"])
@login_required
def api_list_sessions():
    """List the current user's active sessions across all devices."""
    if not _use_sqlite_login_history():
        return jsonify({"ok": False, "error": "Requires SQLite backend"}), 503

    from core import db as _db
    from core.auth import _USERS_DB

    me = session.get("username") or ""
    if not me:
        return jsonify({"ok": False, "error": "Not logged in"}), 401

    rows = _db.list_sessions(_USERS_DB, me)
    current_sid = session.get("sid")
    # Annotate which row is the requesting session so the UI can mark it.
    for r in rows:
        r["is_current"] = r["sid"] == current_sid
        # Drop the sid from rows that aren't current so it can't be replayed
        # against /api/auth/sessions/<sid>/revoke from a JS leak. Current
        # row keeps its sid because the user needs it for "sign out".
        if not r["is_current"]:
            r.pop("sid", None)
    return jsonify({"ok": True, "rows": rows, "count": len(rows)})


@bp.route("/api/auth/sessions/revoke", methods=["POST"])
@login_required
def api_revoke_session():
    """Revoke a specific session by SID. Body: {sid: "..."}.

    Users can only revoke their own sessions. Admins can revoke anyone's
    session by passing the SID directly (we still verify the target row
    belongs to the requested user-id).
    """
    if not _use_sqlite_login_history():
        return jsonify({"ok": False, "error": "Requires SQLite backend"}), 503

    from core import db as _db
    from core.auth import _USERS_DB

    me = session.get("username") or ""
    am_admin = bool(session.get("is_admin"))
    data = request.get_json(force=True) or {}
    target_sid = (data.get("sid") or "").strip()
    if not target_sid:
        return jsonify({"ok": False, "error": "sid required"}), 400

    # Verify ownership unless caller is admin.
    if not am_admin:
        rows = _db.list_sessions(_USERS_DB, me)
        if not any(r["sid"] == target_sid for r in rows):
            return jsonify({"ok": False, "error": "Session not found"}), 404

    deleted = _db.delete_session(_USERS_DB, target_sid)
    if not deleted:
        return jsonify({"ok": False, "error": "Session not found"}), 404
    return jsonify({"ok": True, "revoked": target_sid})


@bp.route("/api/auth/sessions/revoke_others", methods=["POST"])
@login_required
def api_revoke_other_sessions():
    """Sign out everywhere EXCEPT the current device.

    Useful after a "did someone else log in?" alert — flushes every session
    you can't see in front of you.
    """
    if not _use_sqlite_login_history():
        return jsonify({"ok": False, "error": "Requires SQLite backend"}), 503

    from core import db as _db
    from core.auth import _USERS_DB

    me = session.get("username") or ""
    if not me:
        return jsonify({"ok": False, "error": "Not logged in"}), 401
    current_sid = session.get("sid")
    deleted = _db.delete_sessions_for_user(_USERS_DB, me, except_sid=current_sid)
    return jsonify({"ok": True, "revoked": deleted})


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


# ── TOTP 2FA ──────────────────────────────────────────────────────────────────
@bp.route("/login/totp", methods=["GET", "POST"])
def login_totp():
    """Second-factor challenge after a successful password step.

    Only reachable with a pending half-session (set by /login after the
    password check). Direct visits without the half-session redirect to
    /login.
    """
    pending_username = session.get("pending_username")
    if not pending_username:
        return ("", 302, {"Location": "/login"})

    if request.method == "POST":
        code = (request.form.get("code") or "").strip()
        use_backup = (request.form.get("use_backup") or "").strip()

        from core import totp as _totp
        from core.auth import _USERS_DB

        ok = False
        if use_backup:
            ok = _totp.consume_backup_code(_USERS_DB, pending_username, code)
        else:
            ok = _totp.verify_code(_USERS_DB, pending_username, code)

        if not ok:
            # Record failure in the audit log so brute-force attempts are visible.
            from core.auth import _record_attempt, _record_failed_login
            _record_failed_login(pending_username)
            _record_attempt(
                pending_username, success=False,
                ip=request.remote_addr,
                user_agent=(request.user_agent.string if request.user_agent else None),
                reason="bad_totp",
            )
            return _totp_challenge_html("<div class='err'>Invalid code — try again</div>"), 401, {
                "Content-Type": "text/html"
            }

        # Promote half-session to a full session.
        username = pending_username
        is_admin = bool(session.pop("pending_is_admin", False))
        session.pop("pending_username", None)
        session["authed"] = True
        session["username"] = username
        session["is_admin"] = is_admin
        session.permanent = True

        # Create server-side session row (same flow as /login).
        if _use_sqlite_login_history():
            try:
                from core import db as _db

                sid = _db.create_session(
                    _USERS_DB,
                    username,
                    request.remote_addr,
                    request.user_agent.string if request.user_agent else None,
                )
                session["sid"] = sid
            except Exception as exc:
                logger.debug("create_session after TOTP failed: %s", exc)

        return ("", 302, {"Location": "/app"})

    return _totp_challenge_html(""), 200, {"Content-Type": "text/html"}


def _totp_challenge_html(error_html: str) -> str:
    """Render the TOTP challenge form. Reuses the login page's CSS so the
    UI feels continuous."""
    from core.auth import LOGIN_PAGE
    from app.middleware import generate_csrf_token

    csrf = generate_csrf_token()
    body = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>SEO Suite — Two-factor authentication</title>
<style>
{LOGIN_PAGE.split('<style>')[1].split('</style>')[0]}
</style>
</head>
<body>
<div class="grid"></div>
<div class="wrap">
  <div class="card">
    <div class="card-title">Two-factor authentication</div>
    <div class="card-sub">Enter the 6-digit code from your authenticator app, or use a backup code.</div>
    <form method="post" action="/login/totp">
      <input type="hidden" name="_csrf_token" value="{csrf}">
      <div class="field">
        <label for="code">Code</label>
        <input id="code" name="code" type="text" inputmode="numeric"
               autocomplete="one-time-code" placeholder="123456" required autofocus>
      </div>
      <button class="btn" type="submit">Verify</button>
      {error_html}
    </form>
    <hr class="divider">
    <details style="margin-top:8px">
      <summary class="hint" style="cursor:pointer;color:#8B5CF6">Lost your phone? Use a backup code</summary>
    <form id="bk" method="post" action="/login/totp" style="margin-top:12px">
      <input type="hidden" name="_csrf_token" value="{csrf}">
      <input type="hidden" name="use_backup" value="1">
      <div class="field">
        <label for="bcode">Backup code</label>
        <input id="bcode" name="code" type="text" placeholder="ABC123DEF456" required>
      </div>
      <button class="btn" type="submit">Use backup code</button>
    </form>
    </details>
  </div>
</div>
</body>
</html>"""
    return body


@bp.route("/api/auth/totp/status", methods=["GET"])
@login_required
def api_totp_status():
    """Is 2FA enabled for the current user? Used by Settings UI."""
    if not _use_sqlite_login_history():
        return jsonify({"ok": False, "error": "Requires SQLite backend"}), 503
    from core import totp as _totp
    from core.auth import _USERS_DB

    me = session.get("username") or ""
    return jsonify(
        {
            "ok": True,
            "enabled": _totp.is_enabled(_USERS_DB, me),
            "remaining_backup_codes": _totp.remaining_backup_codes(_USERS_DB, me),
        }
    )


@bp.route("/api/auth/totp/enroll", methods=["POST"])
@login_required
def api_totp_enroll():
    """Mint a fresh TOTP secret. Returns the secret + provisioning URI so the
    frontend can render a QR code."""
    if not _use_sqlite_login_history():
        return jsonify({"ok": False, "error": "Requires SQLite backend"}), 503
    from core import totp as _totp
    from core.auth import _USERS_DB

    me = session.get("username") or ""
    if not me:
        return jsonify({"ok": False, "error": "Not logged in"}), 401

    try:
        secret, uri = _totp.enroll(_USERS_DB, me)
    except Exception as exc:
        logger.error("totp enroll failed: %s", exc, exc_info=True)
        return jsonify({"ok": False, "error": "An internal error occurred"}), 500

    return jsonify(
        {
            "ok": True,
            "secret": secret,
            "provisioning_uri": uri,
            "message": "Scan the QR (render client-side from the URI) and submit a code to activate.",
        }
    )


@bp.route("/api/auth/totp/activate", methods=["POST"])
@login_required
def api_totp_activate():
    """Verify the user's first TOTP code and enable 2FA. Returns the
    one-time-visible plaintext backup codes."""
    if not _use_sqlite_login_history():
        return jsonify({"ok": False, "error": "Requires SQLite backend"}), 503
    from core import totp as _totp
    from core.auth import _USERS_DB

    me = session.get("username") or ""
    code = ((request.get_json(force=True) or {}).get("code") or "").strip()
    if not code:
        return jsonify({"ok": False, "error": "code required"}), 400

    ok, backup_codes = _totp.activate(_USERS_DB, me, code)
    if not ok:
        return jsonify({"ok": False, "error": "Invalid code — try again"}), 400

    return jsonify(
        {
            "ok": True,
            "message": (
                "2FA enabled. Save these backup codes somewhere safe — "
                "each works once, and they won't be shown again."
            ),
            "backup_codes": backup_codes,
        }
    )


@bp.route("/api/auth/totp/disable", methods=["POST"])
@login_required
def api_totp_disable():
    """Disable 2FA after re-verifying the user's password.

    Requiring the password (not just the session) prevents a stolen cookie
    from weakening the account behind the legitimate user's back.
    """
    if not _use_sqlite_login_history():
        return jsonify({"ok": False, "error": "Requires SQLite backend"}), 503
    from core import totp as _totp
    from core.auth import _USERS_DB, _safe_check, _load_users

    me = session.get("username") or ""
    if not me:
        return jsonify({"ok": False, "error": "Not logged in"}), 401

    password = ((request.get_json(force=True) or {}).get("password") or "")
    user = _load_users().get(me)
    if not user or not _safe_check(user.get("password_hash", ""), password):
        return jsonify({"ok": False, "error": "Password incorrect"}), 401

    _totp.disable(_USERS_DB, me)
    return jsonify({"ok": True, "message": "2FA disabled"})


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

    base_url = os.getenv("SEO_SUITE_BASE_URL", request.host_url).rstrip("/")
    reset_url = f"{base_url}/reset_password?token={raw_token}"
    body = f"""
    <h2>Password reset for SEO Suite</h2>
    <p>We received a request to reset your password. Click the link below to set a new one.
    This link expires in 1 hour and can only be used once.</p>
    <p><a href="{reset_url}">{reset_url}</a></p>
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

    # Peek first — validate the token exists without burning it so a failed
    # policy check doesn't invalidate the user's reset link (C-3).
    username = _db.peek_auth_token(_USERS_DB, token, "password_reset")
    if not username:
        return jsonify({"ok": False, "error": "Invalid or expired reset token"}), 400

    pol_ok, pol_err = validate_new_password(new_password, username=username)
    if not pol_ok:
        return jsonify({"ok": False, "error": pol_err}), 400

    # Policy passed — now consume the token (single-use enforcement).
    if not _db.consume_auth_token(_USERS_DB, token, "password_reset"):
        return jsonify({"ok": False, "error": "Invalid or expired reset token"}), 400

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

    base_url = os.getenv("SEO_SUITE_BASE_URL", request.host_url).rstrip("/")
    verify_url = f"{base_url}/verify_email?token={raw_token}"
    body = f"""
    <h2>Verify your SEO Suite email</h2>
    <p>Click the link below to confirm your email address. The link expires in 24 hours.</p>
    <p><a href="{verify_url}">{verify_url}</a></p>
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

    # Security best practice: invalidate every OTHER session on password
    # change. If the password change is happening because the user noticed
    # a suspicious sign-in, the attacker's cookie stops working immediately.
    # The current device keeps its session so the UI doesn't have to log
    # them out.
    if _use_sqlite_login_history():
        try:
            from core import db as _db
            from core.auth import _USERS_DB

            current_sid = session.get("sid")
            revoked = _db.delete_sessions_for_user(_USERS_DB, me, except_sid=current_sid)
            return jsonify(
                {
                    "ok": True,
                    "message": "Password updated",
                    "other_sessions_revoked": revoked,
                }
            )
        except Exception as exc:
            logger.debug("failed to revoke other sessions: %s", exc)

    return jsonify({"ok": True, "message": "Password updated"})


# ── Login history (audit trail) ───────────────────────────────────────────────
@bp.route("/api/auth/login_history")
@admin_required
def api_login_history():
    """Admin-only: list recent login attempts across all users.

    Query params:
      * ``username`` — filter to one account
      * ``failures_only=1`` — return only failed attempts (brute-force scan)
      * ``limit`` — page size (default 50, max 200) — S20: paginated
      * ``offset`` — page offset (default 0, clamped to total)
    """
    if not _use_sqlite_login_history():
        return jsonify({"ok": False, "error": "Login history requires the SQLite backend"}), 503

    from core import db as _db
    from core.auth import _USERS_DB

    username = (request.args.get("username") or "").strip() or None
    failures_only = request.args.get("failures_only") in ("1", "true", "yes")
    success_filter = False if failures_only else None
    try:
        limit = max(1, min(int(request.args.get("limit", "50")), 200))
    except (TypeError, ValueError):
        limit = 50
    try:
        offset = max(0, int(request.args.get("offset", "0")))
    except (TypeError, ValueError):
        offset = 0

    total = _db.count_login_history(
        _USERS_DB, username=username, success=success_filter
    )
    if offset > total:
        offset = total

    rows = _db.get_login_history(
        _USERS_DB,
        username=username,
        success=success_filter,
        limit=limit,
        offset=offset,
    )
    return jsonify({
        "ok": True,
        "rows": rows,
        "total": total,
        "limit": limit,
        "offset": offset,
        "count": len(rows),
    })


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


# ── GDPR / self-service account ops ───────────────────────────────────────────
@bp.route("/api/auth/me/export", methods=["GET"])
@login_required
def api_export_my_data():
    """Return everything we have on the current user as a single JSON dump.

    Helps satisfy GDPR Article 15 (right of access) without admin
    intervention. Includes:
      - account fields (excluding password hash)
      - full login history
      - active sessions (sids redacted except the current one)
      - TOTP status (secret never exported, even to the user themselves)
      - saved profiles (TODO: not yet keyed by user; out of scope)

    Returns a downloadable JSON file so the user can archive it locally.
    """
    if not _use_sqlite_login_history():
        return jsonify({"ok": False, "error": "Requires SQLite backend"}), 503

    from core import db as _db
    from core import totp as _totp
    from core.auth import _USERS_DB

    me = session.get("username") or ""
    if not me:
        return jsonify({"ok": False, "error": "Not logged in"}), 401

    user_row = _db.get_user(_USERS_DB, me)
    if user_row:
        # Strip the hash — it's a credential, not personal data the user
        # would need or want to export.
        user_row.pop("password_hash", None)

    login_history = _db.get_login_history(_USERS_DB, username=me, limit=500)
    sessions_list = _db.list_sessions(_USERS_DB, me)
    current_sid = session.get("sid")
    for s in sessions_list:
        if s["sid"] != current_sid:
            s.pop("sid", None)

    totp_row = _totp.get_row(_USERS_DB, me)
    totp_status = {
        "enabled": bool(totp_row and totp_row["enabled"]),
        "remaining_backup_codes": _totp.remaining_backup_codes(_USERS_DB, me),
        # Deliberately NOT exporting the secret or backup codes.
    }

    body = {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "username": me,
        "account": user_row,
        "login_history": login_history,
        "sessions": sessions_list,
        "totp": totp_status,
        "notice": (
            "Sensitive credentials (password hash, TOTP secret, backup codes) "
            "are deliberately excluded from this export."
        ),
    }
    payload = json.dumps(body, indent=2)
    return payload, 200, {
        "Content-Type": "application/json",
        "Content-Disposition": f'attachment; filename="seosuite_export_{me}.json"',
    }


@bp.route("/api/auth/me/delete", methods=["POST"])
@login_required
def api_delete_my_account():
    """Self-service account deletion.

    Requires the current password (so a stolen session can't nuke the
    account permanently) AND an explicit ``confirm: "DELETE"`` in the body.
    Wipes the user row, every related session row, every login_attempts
    row, every auth_token, and the TOTP secret. Logs the user out
    afterwards.

    Refuses to delete the env admin (their hash lives in env vars; the
    operator must remove SEO_SUITE_PASSWORD_HASH out-of-band) and refuses
    to delete the last admin user (would lock everyone out).
    """
    if not _use_sqlite_login_history():
        return jsonify({"ok": False, "error": "Requires SQLite backend"}), 503

    from core import db as _db
    from core import totp as _totp
    from core.auth import _USERS_DB, _env_admin, _load_users, _safe_check
    from core.db import _connect

    me = session.get("username") or ""
    data = request.get_json(force=True) or {}
    password = data.get("password") or ""
    confirm = (data.get("confirm") or "").strip()

    if not me:
        return jsonify({"ok": False, "error": "Not logged in"}), 401
    if confirm != "DELETE":
        return jsonify(
            {"ok": False, "error": "Set confirm=\"DELETE\" to confirm account deletion"}
        ), 400
    if me == _env_admin():
        return jsonify(
            {
                "ok": False,
                "error": (
                    "The environment admin account can't be self-deleted. "
                    "Remove SEO_SUITE_PASSWORD_HASH from the environment instead."
                ),
            }
        ), 400

    users = _load_users()
    user = users.get(me)
    if not user or not _safe_check(user.get("password_hash", ""), password):
        return jsonify({"ok": False, "error": "Password incorrect"}), 401

    # Last-admin guard.
    if user.get("is_admin") and _env_admin() is None:
        others = [u for u, v in users.items() if u != me and v.get("is_admin")]
        if not others:
            return jsonify(
                {
                    "ok": False,
                    "error": (
                        "Cannot delete the last admin — promote another user first."
                    ),
                }
            ), 400

    # Wipe everything related to this user. Wrapped in a transaction so a
    # partial failure leaves either the whole user intact or nothing.
    try:
        with _connect(_USERS_DB) as conn:
            conn.execute("BEGIN")
            conn.execute("DELETE FROM users WHERE username = ?", (me,))
            conn.execute("DELETE FROM login_attempts WHERE username = ?", (me,))
            conn.execute("DELETE FROM sessions WHERE username = ?", (me,))
            conn.execute("DELETE FROM auth_tokens WHERE username = ?", (me,))
            conn.execute("DELETE FROM totp_secrets WHERE username = ?", (me,))
            conn.execute("COMMIT")
    except Exception as exc:
        logger.error("self-delete failed for %s: %s", me, exc)
        return jsonify({"ok": False, "error": "Deletion failed"}), 500

    # Best-effort TOTP wipe via the dedicated helper (in case schema changes).
    _totp.disable(_USERS_DB, me)

    session.clear()
    logger.info("User self-deleted account: %s", me)
    return jsonify({"ok": True, "message": "Account deleted"})


def _use_sqlite_login_history() -> bool:
    """Login history only works when the SQLite backend is active."""
    import os as _os

    return _os.environ.get("SEO_SUITE_USERS_BACKEND", "sqlite").lower() != "json"


# ── Auth status / credential helper ───────────────────────────────────────────
@bp.route("/api/auth_status")
def api_auth_status():
    """Return current auth configuration state (for Settings → Security card).

    Returns a minimal payload when not authenticated so the endpoint can
    still be called on page load without exposing admin details (M-10).
    Never returns the env admin username — callers get a boolean flag only (C-7).
    """
    if auth_enabled() and not session.get("authed"):
        return jsonify({"auth_enabled": True, "authenticated": False})

    me = session.get("username") or ""
    from core.auth import _should_force_env_admin_rotation

    return jsonify(
        {
            "auth_enabled": auth_enabled(),
            "authenticated": True,
            "is_env_admin": bool(os.getenv("SEO_SUITE_PASSWORD_HASH")),
            "secret_set": bool(os.getenv("SEO_SUITE_SECRET")),
            "must_rotate_password": _should_force_env_admin_rotation(me),
        }
    )


@bp.route("/api/me")
@login_required
def api_me():
    """Return the current user's identity and admin flag.

    Lets the SPA check admin status before making admin-only calls (e.g.
    ``/api/users``) so those 403 responses are eliminated, not just handled.
    """
    return jsonify({
        "ok": True,
        "username": session.get("username"),
        "is_admin": bool(session.get("is_admin")),
    })


@bp.route("/api/auth/change_credentials", methods=["POST"])
@login_required
@admin_required
def api_auth_change_credentials():
    """Generate a new password hash and return it for the user to paste into .env.

    We intentionally do NOT write to ``.env`` automatically — env changes must
    be explicit and deliberate. The hash is returned in the response so the
    user can update ``SEO_SUITE_USERNAME`` / ``SEO_SUITE_PASSWORD_HASH``
    themselves and restart the server.
    """
    from core.auth import _hash_password
    from core.password_policy import validate_new_password

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
    
    pol_ok, pol_err = validate_new_password(password, username=username)
    if not pol_ok:
        return jsonify({"ok": False, "error": pol_err}), 400

    pw_hash = _hash_password(password)
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
    """Register the blueprint and wire login/signup/totp rate limits.

    Rate limits target the bound view functions, which only exist after
    blueprint registration — hence the factory-style wiring.
    """
    app.register_blueprint(bp)
    limiter.limit("5 per minute")(app.view_functions["auth_views.login"])
    limiter.limit("10 per minute")(app.view_functions["auth_views.signup"])
    limiter.limit("5 per minute")(app.view_functions["auth_views.login_totp"])
    limiter.limit("30 per minute")(app.view_functions["auth_views.api_users_create"])
    limiter.limit("30 per minute")(app.view_functions["auth_views.api_users_delete"])
    limiter.limit("5 per 10 minute")(app.view_functions["auth_views.api_request_password_reset"])
    limiter.limit("10 per minute")(app.view_functions["auth_views.api_reset_password"])
    limiter.limit("10 per minute")(app.view_functions["auth_views.api_verify_email"])
