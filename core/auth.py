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

import logging
import os
import secrets
from functools import wraps

_log = logging.getLogger(__name__)

from flask import Flask, jsonify, redirect, request, session, url_for
from werkzeug.security import check_password_hash


def init_auth(app: Flask) -> None:
    """Wire session secret into the Flask app."""
    from datetime import timedelta
    _secret = os.environ.get("SEO_SUITE_SECRET")
    if not _secret:
        # No secret configured — generate ephemeral key and warn. Sessions will be
        # invalidated on every restart, forcing re-login. Set SEO_SUITE_SECRET in
        # .env to get persistent sessions across restarts.
        _log.warning(
            "SEO_SUITE_SECRET not set — using ephemeral session key. "
            "Sessions will be lost on server restart. "
            "Set SEO_SUITE_SECRET=<random-32-char-string> in your .env to persist logins."
        )
        _secret = secrets.token_hex(32)
    app.secret_key = _secret
    # Harden the session cookie. HTTPS is opt-in via env so local dev still works.
    app.config.update(
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("SEO_SUITE_COOKIE_SECURE", "") == "1",
        # permanent sessions last 30 days; login_required sets session.permanent=True
        PERMANENT_SESSION_LIFETIME=timedelta(days=30),
    )


def auth_enabled() -> bool:
    return bool(os.environ.get("SEO_SUITE_PASSWORD_HASH"))


def verify_credentials(username: str, password: str) -> bool:
    expected_user = os.environ.get("SEO_SUITE_USERNAME", "admin")
    pw_hash = os.environ.get("SEO_SUITE_PASSWORD_HASH", "")
    if not pw_hash:
        return False
    if username != expected_user:
        _log.warning("Failed login attempt for username: %s", username)
        return False
    try:
        result = check_password_hash(pw_hash, password)
    except Exception:
        result = False
    if not result:
        _log.warning("Failed login attempt for username: %s", username)
    return result


def is_authed() -> bool:
    return not auth_enabled() or session.get("authed") is True


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not auth_enabled() or session.get("authed") is True:
            return fn(*args, **kwargs)
        # API callers get 401 JSON; browsers get redirected to /login
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

      <button class="btn" type="submit" id="sub-btn">
        <svg viewBox="0 0 24 24"><path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4"/><polyline points="10 17 15 12 10 7"/><line x1="15" y1="12" x2="3" y2="12"/></svg>
        Sign in
      </button>
      __ERROR__
    </form>

    <hr class="divider">
    <div class="hint">
      Set <code>SEO_SUITE_USERNAME</code> &amp; <code>SEO_SUITE_PASSWORD_HASH</code> in your <code>.env</code> file to enable auth
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
