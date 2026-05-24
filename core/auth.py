"""
Session-based authentication.

Activates only when SEO_SUITE_PASSWORD_HASH is set in the environment, so dev /
tests run without auth. In production:

  1. Generate a hash:
       python -c "from werkzeug.security import generate_password_hash; \
                  print(generate_password_hash('your-password'))"
  2. Export:
       SEO_SUITE_USERNAME=admin
       SEO_SUITE_PASSWORD_HASH=<paste hash here>
       SEO_SUITE_SECRET=<random 32+ char string>
"""
from __future__ import annotations

import json
import logging
import os
import re
import secrets
import threading
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path

_log = logging.getLogger(__name__)

from flask import Flask, jsonify, redirect, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

# ── Multi-user store ───────────────────────────────────────────────────────────
# Accounts live in data/users.json: {username: {password_hash, is_admin, created_at}}.
# The env admin (SEO_SUITE_USERNAME, active only when SEO_SUITE_PASSWORD_HASH is
# set) is a bootstrap superadmin that lives outside this file and can't be locked
# out or deleted.
_USERS_PATH  = Path(__file__).parent.parent / "data" / "users.json"
_CONFIG_PATH = Path(__file__).parent.parent / "config.json"
_users_lock  = threading.Lock()
_USERNAME_RE = re.compile(r"^[A-Za-z0-9_.@-]{3,64}$")
_MIN_PASSWORD_LEN = 12


def _load_users() -> dict:
    try:
        data = json.loads(_USERS_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (FileNotFoundError, ValueError, OSError):
        return {}


def _save_users(users: dict) -> None:
    _USERS_PATH.parent.mkdir(parents=True, exist_ok=True)
    _USERS_PATH.write_text(json.dumps(users, indent=2), encoding="utf-8")


def _env_admin() -> str | None:
    """Bootstrap superadmin username, or None when env auth isn't configured."""
    if os.environ.get("SEO_SUITE_PASSWORD_HASH"):
        return os.environ.get("SEO_SUITE_USERNAME", "admin")
    return None


def _safe_check(pw_hash: str, password: str) -> bool:
    if not pw_hash:
        return False
    try:
        return check_password_hash(pw_hash, password)
    except Exception:
        return False


def signup_allowed() -> bool:
    """Public self-registration toggle (config.json 'allow_signup', default True)."""
    try:
        return bool(json.loads(_CONFIG_PATH.read_text(encoding="utf-8")).get("allow_signup", True))
    except (FileNotFoundError, ValueError, OSError):
        return True


def init_auth(app: Flask) -> None:
    """Wire session secret into the Flask app."""
    from datetime import timedelta
    _secret = os.environ.get("SEO_SUITE_SECRET")
    if not _secret:
        # No secret configured — generate an ephemeral key and warn loudly.
        # Every server restart (including Render cold-starts and re-deploys) will
        # produce a new key, invalidating all existing session cookies and forcing
        # every user to sign in again.
        #
        # FIX: copy the key printed below and set SEO_SUITE_SECRET to that value
        # in your hosting dashboard (Render → Environment) so it stays stable.
        _secret = secrets.token_hex(32)
        _log.warning(
            "SEO_SUITE_SECRET is not set — sessions will be lost on every restart.\n"
            "  To fix: add the following to your environment variables:\n"
            "    SEO_SUITE_SECRET=%s\n"
            "  On Render: Dashboard → your service → Environment → Add Variable.",
            _secret,
        )
    app.secret_key = _secret
    # Harden the session cookie. HTTPS is opt-in via env so local dev still works.
    app.config.update(
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("SEO_SUITE_COOKIE_SECURE", "") == "1",
        # permanent sessions last 30 days; login sets session.permanent=True
        PERMANENT_SESSION_LIFETIME=timedelta(days=30),
    )


def auth_enabled() -> bool:
    """Auth is on if an env admin is configured OR any file-based user exists
    OR if explicitly forced via env var (e.g. on public hosting).
    By default, we also enable it if running on Render or in a production-like env.
    """
    if os.environ.get("SEO_SUITE_NO_AUTH") == "1":
        return False
    if os.environ.get("RENDER") == "true" or os.environ.get("SEO_SUITE_FORCE_AUTH") == "1":
        return True
    return bool(os.environ.get("SEO_SUITE_PASSWORD_HASH")) or bool(_load_users())


def authenticate(username: str, password: str) -> dict | None:
    """Return {username, is_admin} on success, else None.

    Checks the env superadmin first, then the file-based user store.
    """
    username = (username or "").strip()
    if not username:
        return None
    env_user = _env_admin()
    if env_user and username == env_user:
        if _safe_check(os.environ.get("SEO_SUITE_PASSWORD_HASH", ""), password):
            return {"username": username, "is_admin": True}
        _log.warning("Failed login attempt for username: %s", username)
        return None
    user = _load_users().get(username)
    if user and _safe_check(user.get("password_hash", ""), password):
        return {"username": username, "is_admin": bool(user.get("is_admin"))}
    _log.warning("Failed login attempt for username: %s", username)
    return None


def verify_credentials(username: str, password: str) -> bool:
    """Backwards-compatible boolean form of authenticate()."""
    return authenticate(username, password) is not None


def create_user(username: str, password: str, is_admin: bool = False) -> tuple[bool, str | None]:
    """Create a file-based user. Returns (ok, error_message)."""
    username = (username or "").strip()
    if not _USERNAME_RE.match(username):
        return False, "Username must be 3–64 chars: letters, numbers, and . _ - @"
    if len(password or "") < _MIN_PASSWORD_LEN:
        return False, f"Password must be at least {_MIN_PASSWORD_LEN} characters"
    if username == _env_admin():
        return False, "That username is reserved by the environment admin"
    with _users_lock:
        users = _load_users()
        if username in users:
            return False, "That username already exists"
        # Bootstrap: the first account becomes admin when there's no env admin.
        if not users and _env_admin() is None:
            is_admin = True
        users[username] = {
            "password_hash": generate_password_hash(password),
            "is_admin": bool(is_admin),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        _save_users(users)
    _log.info("User created: %s (admin=%s)", username, bool(is_admin))
    return True, None


def delete_user(username: str) -> tuple[bool, str | None]:
    """Delete a file-based user. Refuses to delete the env admin or the last admin."""
    username = (username or "").strip()
    if username == _env_admin():
        return False, "Cannot delete the environment admin"
    with _users_lock:
        users = _load_users()
        if username not in users:
            return False, "No such user"
        if users[username].get("is_admin") and _env_admin() is None:
            others = [u for u, v in users.items() if u != username and v.get("is_admin")]
            if not others:
                return False, "Cannot delete the last admin — promote another user first"
        del users[username]
        _save_users(users)
    _log.info("User deleted: %s", username)
    return True, None


def list_users() -> list[dict]:
    """List accounts (no password hashes). Includes the env admin if configured."""
    out: list[dict] = []
    env = _env_admin()
    if env:
        out.append({"username": env, "is_admin": True, "source": "env", "created_at": None})
    for u, v in _load_users().items():
        out.append({
            "username": u, "is_admin": bool(v.get("is_admin")),
            "source": "file", "created_at": v.get("created_at"),
        })
    return out


def is_authed() -> bool:
    return not auth_enabled() or session.get("authed") is True


def is_admin() -> bool:
    """True for the current session's admin, or always when auth is disabled (local dev)."""
    return not auth_enabled() or session.get("is_admin") is True


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not auth_enabled() or session.get("authed") is True:
            return fn(*args, **kwargs)
        # API callers get 401 JSON; browsers get redirected to /login?next=<path>
        if request.path.startswith("/api/") or request.accept_mimetypes.best == "application/json":
            return jsonify({"error": "Authentication required"}), 401
        # Preserve the requested path so the user lands back here after login.
        return redirect(url_for("login", next=request.path))
    return wrapper


def admin_required(fn):
    """Like login_required, but also requires the session to be an admin."""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not auth_enabled():
            return fn(*args, **kwargs)  # local dev — full access
        if session.get("authed") is True and session.get("is_admin") is True:
            return fn(*args, **kwargs)
        if session.get("authed") is True:
            return jsonify({"error": "Admin privileges required"}), 403
        if request.path.startswith("/api/") or request.accept_mimetypes.best == "application/json":
            return jsonify({"error": "Authentication required"}), 401
        return redirect(url_for("login"))
    return wrapper


LOGIN_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>SEO Suite — Sign in</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
@keyframes fadeUp{from{opacity:0;transform:translateY(18px)}to{opacity:1;transform:translateY(0)}}
@keyframes shimmer{0%,100%{opacity:.3}50%{opacity:.7}}
body{
  font-family:'Inter',-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
  background:#080812;color:#e2e8f0;
  display:grid;place-items:center;min-height:100vh;padding:20px;
}
/* Animated gradient orbs */
body::before,body::after{
  content:'';position:fixed;border-radius:50%;pointer-events:none;
  filter:blur(80px);opacity:.25;animation:shimmer 6s ease-in-out infinite;
}
body::before{
  width:600px;height:600px;
  background:radial-gradient(circle,#6366F1,transparent 70%);
  top:-200px;left:-200px;animation-delay:0s;
}
body::after{
  width:500px;height:500px;
  background:radial-gradient(circle,#8B5CF6,transparent 70%);
  bottom:-150px;right:-150px;animation-delay:3s;
}
/* Grid overlay */
body > .grid{
  position:fixed;inset:0;pointer-events:none;
  background-image:linear-gradient(rgba(99,102,241,.035) 1px,transparent 1px),
                   linear-gradient(90deg,rgba(99,102,241,.035) 1px,transparent 1px);
  background-size:48px 48px;
}
.wrap{
  width:100%;max-width:420px;position:relative;z-index:1;
  animation:fadeUp .45s cubic-bezier(.22,.68,0,1.2) both;
}
/* Logo */
.logo{display:flex;align-items:center;gap:11px;justify-content:center;margin-bottom:32px}
.logo-mark{
  width:40px;height:40px;border-radius:12px;flex-shrink:0;
  background:linear-gradient(135deg,#6366F1 0%,#8B5CF6 100%);
  display:flex;align-items:center;justify-content:center;
  box-shadow:0 0 0 1px rgba(99,102,241,.4),0 8px 24px rgba(99,102,241,.35);
}
.logo-mark svg{width:20px;height:20px;fill:none;stroke:#fff;stroke-width:2;stroke-linecap:round;stroke-linejoin:round}
.logo-right{display:flex;flex-direction:column;gap:2px}
.logo-text{font-size:19px;font-weight:800;color:#fff;letter-spacing:-.6px;line-height:1}
.logo-sub{font-size:11px;color:#6366F1;font-weight:500;letter-spacing:.3px}
/* Card */
.card{
  background:rgba(22,22,42,.85);border-radius:20px;
  border:1px solid rgba(255,255,255,.07);
  box-shadow:0 0 0 1px rgba(99,102,241,.08),0 24px 64px rgba(0,0,0,.6),inset 0 1px 0 rgba(255,255,255,.05);
  padding:36px;backdrop-filter:blur(16px);-webkit-backdrop-filter:blur(16px);
}
.card-title{font-size:20px;font-weight:700;color:#f1f5f9;margin-bottom:4px;letter-spacing:-.3px}
.card-sub{font-size:13px;color:#64748b;margin-bottom:28px;line-height:1.5}
/* Fields */
.field{margin-bottom:18px}
label{
  display:block;font-size:11px;font-weight:600;
  color:#7C8599;margin-bottom:7px;
  text-transform:uppercase;letter-spacing:.7px;
}
.input-wrap{position:relative;display:flex;align-items:center}
.input-icon{
  position:absolute;left:13px;top:50%;transform:translateY(-50%);
  width:16px;height:16px;color:#4A5268;pointer-events:none;flex-shrink:0;
}
.input-icon svg{width:16px;height:16px;fill:none;stroke:currentColor;stroke-width:1.8;stroke-linecap:round;stroke-linejoin:round}
input[type=text],input[type=email],input[type=password]{
  width:100%;padding:11px 42px;font-size:14px;
  border:1.5px solid rgba(255,255,255,.08);border-radius:11px;
  background:rgba(8,8,20,.6);color:#e2e8f0;outline:none;
  transition:border-color .15s,box-shadow .15s,background .15s;
  font-family:inherit;caret-color:#6366f1;
}
input::placeholder{color:#3D4560}
input:focus{
  border-color:rgba(99,102,241,.6);
  box-shadow:0 0 0 3px rgba(99,102,241,.15);
  background:rgba(8,8,20,.8);
}
input:focus::placeholder{color:#5C6480}
/* Password toggle */
.pw-toggle{
  position:absolute;right:12px;top:50%;transform:translateY(-50%);
  background:none;border:none;cursor:pointer;padding:4px;
  color:#4A5268;transition:color .15s;line-height:1;
}
.pw-toggle:hover{color:#94a3b8}
.pw-toggle svg{width:16px;height:16px;fill:none;stroke:currentColor;stroke-width:1.8;stroke-linecap:round;stroke-linejoin:round;display:block}
/* Submit button */
.btn{
  margin-top:4px;width:100%;padding:12px;font-size:14px;font-weight:700;
  background:linear-gradient(135deg,#6366F1 0%,#8B5CF6 100%);
  color:#fff;border:none;border-radius:11px;cursor:pointer;
  font-family:inherit;letter-spacing:-.1px;
  box-shadow:0 1px 0 rgba(255,255,255,.1) inset,0 4px 20px rgba(99,102,241,.4);
  transition:all .15s cubic-bezier(.4,0,.2,1);
  display:flex;align-items:center;justify-content:center;gap:8px;
}
.btn:hover{transform:translateY(-1px);box-shadow:0 1px 0 rgba(255,255,255,.15) inset,0 8px 28px rgba(99,102,241,.55)}
.btn:active{transform:translateY(0);box-shadow:0 4px 12px rgba(99,102,241,.3)}
.btn.loading{opacity:.75;pointer-events:none}
.btn svg{width:16px;height:16px;fill:none;stroke:currentColor;stroke-width:2.5;stroke-linecap:round;stroke-linejoin:round;flex-shrink:0}
/* Error */
.err{
  margin-top:16px;padding:11px 14px;
  background:rgba(239,68,68,.08);border:1px solid rgba(239,68,68,.2);
  border-radius:10px;font-size:13px;color:#fca5a5;
  display:flex;align-items:center;gap:9px;
}
.err-icon{width:15px;height:15px;flex-shrink:0;fill:none;stroke:#fca5a5;stroke-width:2;stroke-linecap:round;stroke-linejoin:round}
/* Divider */
.divider{margin:24px 0 0;border:none;border-top:1px solid rgba(255,255,255,.05)}
/* Hint */
.hint{margin-top:16px;font-size:11.5px;color:#3D4560;line-height:1.7;text-align:center}
.hint code{background:rgba(255,255,255,.05);padding:1px 6px;border-radius:5px;color:#6B7499;font-size:10.5px;border:1px solid rgba(255,255,255,.07)}
/* Footer */
.footer{margin-top:24px;text-align:center;font-size:11px;color:#2D3248;display:flex;align-items:center;justify-content:center;gap:5px}
.footer-dot{width:4px;height:4px;border-radius:50%;background:#2D3248}
</style>
</head>
<body>
<div class="grid"></div>
<div class="wrap">
  <div class="logo">
    <div class="logo-mark">
      <svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
    </div>
    <div class="logo-right">
      <span class="logo-text">SEO Suite</span>
      <span class="logo-sub">Professional SEO Platform</span>
    </div>
  </div>

  <div class="card">
    <div class="card-title">Welcome back</div>
    <div class="card-sub">Sign in to access your SEO dashboard</div>

    <form method="post" action="/login" id="lf" onsubmit="onSub(this)">
      <div class="field">
        <label for="un">Username</label>
        <div class="input-wrap">
          <span class="input-icon">
            <svg viewBox="0 0 24 24"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
          </span>
          <input id="un" name="username" type="text" autocomplete="username"
                 placeholder="admin" required autofocus>
        </div>
      </div>
      <div class="field">
        <label for="pw">Password</label>
        <div class="input-wrap">
          <span class="input-icon">
            <svg viewBox="0 0 24 24"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>
          </span>
          <input id="pw" name="password" type="password" autocomplete="current-password"
                 placeholder="••••••••" required>
          <button type="button" class="pw-toggle" onclick="togglePw()" title="Show / hide password" id="pw-eye">
            <svg id="pw-eye-open" viewBox="0 0 24 24"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
          </button>
        </div>
      </div>

      __NEXT__
      <button class="btn" type="submit" id="sub-btn">
        <svg viewBox="0 0 24 24"><path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4"/><polyline points="10 17 15 12 10 7"/><line x1="15" y1="12" x2="3" y2="12"/></svg>
        Sign in
      </button>
      __ERROR__
    </form>

    <hr class="divider">
    <div class="hint">
      Don't have an account? <a href="/signup" style="color:#8B5CF6;font-weight:600">Create one</a>
    </div>
  </div>

  <div class="footer">
    <span>SEO Suite</span>
    <span class="footer-dot"></span>
    <span>v2.0</span>
    <span class="footer-dot"></span>
    <span>localhost</span>
  </div>
</div>

<script>
function togglePw(){
  var i=document.getElementById('pw');
  var open=i.type==='password';
  i.type=open?'text':'password';
  document.getElementById('pw-eye').style.color=open?'#6366f1':'';
}
function onSub(f){
  var b=document.getElementById('sub-btn');
  b.classList.add('loading');
  b.innerHTML='<svg viewBox="0 0 24 24" style="animation:spin .7s linear infinite"><line x1="12" y1="2" x2="12" y2="6"/><line x1="12" y1="18" x2="12" y2="22"/><line x1="4.93" y1="4.93" x2="7.76" y2="7.76"/><line x1="16.24" y1="16.24" x2="19.07" y2="19.07"/><line x1="2" y1="12" x2="6" y2="12"/><line x1="18" y1="12" x2="22" y2="12"/><line x1="4.93" y1="19.07" x2="7.76" y2="16.24"/><line x1="16.24" y1="7.76" x2="19.07" y2="4.93"/></svg> Signing in…';
}
</script>
<style>@keyframes spin{to{transform:rotate(360deg)}}</style>
</body>
</html>"""


# Signup page reuses the login page's <head> (all shared CSS) so the two stay
# visually consistent without duplicating the stylesheet.
SIGNUP_PAGE = LOGIN_PAGE.split("</head>")[0] + """</head>
<body>
<div class="grid"></div>
<div class="wrap">
  <div class="logo">
    <div class="logo-mark">
      <svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
    </div>
    <div class="logo-right">
      <span class="logo-text">SEO Suite</span>
      <span class="logo-sub">Professional SEO Platform</span>
    </div>
  </div>

  <div class="card">
    <div class="card-title">Create your account</div>
    <div class="card-sub">Sign up to access your SEO dashboard</div>

    <form method="post" action="/signup" id="sf" onsubmit="onSub(this)">
      <div class="field">
        <label for="un">Username</label>
        <div class="input-wrap">
          <span class="input-icon">
            <svg viewBox="0 0 24 24"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
          </span>
          <input id="un" name="username" type="text" autocomplete="username"
                 placeholder="your-username" required autofocus>
        </div>
      </div>
      <div class="field">
        <label for="pw">Password</label>
        <div class="input-wrap">
          <span class="input-icon">
            <svg viewBox="0 0 24 24"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>
          </span>
          <input id="pw" name="password" type="password" autocomplete="new-password"
                 placeholder="min 12 characters" required minlength="12">
          <button type="button" class="pw-toggle" onclick="togglePw('pw')" title="Show / hide password">
            <svg viewBox="0 0 24 24"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
          </button>
        </div>
      </div>
      <div class="field">
        <label for="pw2">Confirm Password</label>
        <div class="input-wrap">
          <span class="input-icon">
            <svg viewBox="0 0 24 24"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>
          </span>
          <input id="pw2" name="confirm" type="password" autocomplete="new-password"
                 placeholder="repeat password" required minlength="12">
        </div>
      </div>

      <button class="btn" type="submit" id="sub-btn">
        <svg viewBox="0 0 24 24"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><line x1="19" y1="8" x2="19" y2="14"/><line x1="22" y1="11" x2="16" y2="11"/></svg>
        Create account
      </button>
      __ERROR__
    </form>

    <hr class="divider">
    <div class="hint">
      Already have an account? <a href="/login" style="color:#8B5CF6;font-weight:600">Sign in</a>
    </div>
  </div>

  <div class="footer">
    <span>SEO Suite</span>
    <span class="footer-dot"></span>
    <span>v2.0</span>
  </div>
</div>

<script>
function togglePw(id){
  var i=document.getElementById(id);
  i.type = i.type==='password' ? 'text' : 'password';
}
function onSub(f){
  var b=document.getElementById('sub-btn');
  b.classList.add('loading');
  b.innerHTML='<svg viewBox="0 0 24 24" style="animation:spin .7s linear infinite"><line x1="12" y1="2" x2="12" y2="6"/><line x1="12" y1="18" x2="12" y2="22"/><line x1="4.93" y1="4.93" x2="7.76" y2="7.76"/><line x1="16.24" y1="16.24" x2="19.07" y2="19.07"/><line x1="2" y1="12" x2="6" y2="12"/><line x1="18" y1="12" x2="22" y2="12"/><line x1="4.93" y1="19.07" x2="7.76" y2="16.24"/><line x1="16.24" y1="7.76" x2="19.07" y2="4.93"/></svg> Creating…';
}
</script>
<style>@keyframes spin{to{transform:rotate(360deg)}}</style>
</body>
</html>"""
