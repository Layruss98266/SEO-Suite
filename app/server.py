"""
SEO Suite — Flask app factory.

This module constructs the Flask ``app`` instance, wires CORS / Sentry / rate
limiting / middleware, and registers all route blueprints. Every route now
lives in :mod:`app.blueprints.*`; shared in-process state and helpers live in
:mod:`app.state`; cross-cutting middleware lives in :mod:`app.middleware`.

``main.py`` imports ``app`` from here directly; ``app/__init__.create_app`` is
a thin factory that returns this same configured app for WSGI deployment.
"""

from __future__ import annotations

import logging
import os
import threading

from flask import Flask
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from app import state
from app.metrics import init_metrics
from app.middleware import init_middleware
from app.state import (
    CFG,
    CONFIG_PATH,
    DATA_DIR,
    REPORTS_DIR,
    STATIC_DIR,
    TEMPLATE_DIR,
    _audit_cancel,
    _audit_paused,
    _audit_status,
    _cleanup_subscribers,
    _index_cancel,
    _index_paused,
    _index_status,
    _lock,
    _pdf_semaphore,
)
from core.auth import init_auth

# ── Logging ───────────────────────────────────────────────────────────────────
# File logging is best-effort: on a read-only filesystem (e.g. a serverless
# host) the FileHandler is skipped so import never crashes. Stream logging
# always works and is what container/PaaS log collectors read anyway.
#
# Set SEO_SUITE_LOG_JSON=1 to emit structured JSON logs (drop-in for ELK /
# Datadog / Loki pipelines that prefer JSON over text). Falls back to plain
# text format when python-json-logger isn't installed or the env var is off.
_log_handlers: list[logging.Handler] = [logging.StreamHandler()]
try:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    _log_handlers.insert(0, logging.FileHandler(DATA_DIR / "app.log", encoding="utf-8"))
except OSError:
    pass  # read-only FS — stream logging only

if os.getenv("SEO_SUITE_LOG_JSON") == "1":
    try:
        from pythonjsonlogger import jsonlogger

        _json_fmt = jsonlogger.JsonFormatter(
            "%(asctime)s %(levelname)s %(name)s %(message)s",
            rename_fields={"asctime": "timestamp", "levelname": "level"},
        )
        for _h in _log_handlers:
            _h.setFormatter(_json_fmt)
        logging.basicConfig(level=logging.INFO, handlers=_log_handlers)
    except ImportError:
        # python-json-logger not installed — fall through to text format.
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] %(message)s",
            handlers=_log_handlers,
        )
else:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=_log_handlers,
    )
logger = logging.getLogger(__name__)

# ── App construction ──────────────────────────────────────────────────────────
app = Flask(__name__, template_folder=str(TEMPLATE_DIR), static_folder=str(STATIC_DIR))
init_auth(app)

# CORS origins are env-configurable so production deployments don't need a code
# change. Default is 8080 (the canonical port) — set CORS_ALLOWED_ORIGINS if
# you front the app on a different port.
_cors_origins = [
    o.strip()
    for o in os.getenv(
        "CORS_ALLOWED_ORIGINS",
        "http://localhost:8080,http://127.0.0.1:8080",
    ).split(",")
    if o.strip()
]
CORS(app, origins=_cors_origins, supports_credentials=True)
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024  # 10 MB upload cap

# Security headers, CSRF, error handlers, Jinja csrf_token global.
init_middleware(app)

# Prometheus /metrics endpoint + per-request HTTP counters and histograms.
# Returns 503 if prometheus-client isn't installed; restrict the route at the
# network layer in production.
init_metrics(app)

# ── Sentry error tracking (Stage 1-D) ─────────────────────────────────────────
# Opt-in: set SENTRY_DSN env var to activate. No-ops silently when absent so
# local / air-gapped installs are unaffected.
_sentry_dsn = os.getenv("SENTRY_DSN", "")
if _sentry_dsn:
    import sentry_sdk
    from sentry_sdk.integrations.flask import FlaskIntegration

    sentry_sdk.init(
        dsn=_sentry_dsn,
        integrations=[FlaskIntegration()],
        traces_sample_rate=0.05,  # capture 5% of requests for perf
        environment=os.getenv("SEO_SUITE_ENV", "development"),
    )
    logger.info(
        "Sentry error tracking enabled (env=%s)", os.getenv("SEO_SUITE_ENV", "development")
    )

# ── Rate limiting (Stage 1-B) ────────────────────────────────────────────────
# In-memory store — no Redis dependency needed for single-server deployments.
# Limits apply per remote IP address. Per-route limits are applied inside each
# blueprint's ``register()`` factory so they target the bound view function.
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["240 per minute"],
    storage_uri="memory://",
)

# Start the SSE subscriber-cleanup thread now that state is initialised.
threading.Thread(target=_cleanup_subscribers, daemon=True, name="sse-cleanup").start()


# ══════════════════════════════════════════════════════════════════════════════
# BLUEPRINTS
# ══════════════════════════════════════════════════════════════════════════════
from app.blueprints import audit as _audit_bp
from app.blueprints import auth_views as _auth_bp
from app.blueprints import indexing as _indexing_bp
from app.blueprints import misc as _misc_bp
from app.blueprints import reports as _reports_bp
from app.blueprints import runners as _runners_bp
from app.blueprints import settings as _settings_bp
from app.blueprints import site as _site_bp
from app.blueprints import tools as _tools_bp

_site_bp.register(app, limiter)
_misc_bp.register(app)
_auth_bp.register(app, limiter)
_reports_bp.register(app)
_settings_bp.register(app, limiter)
_tools_bp.register(app)
_indexing_bp.register(app, limiter)
_audit_bp.register(app, limiter)
_runners_bp.register(app)


# ══════════════════════════════════════════════════════════════════════════════
# API VERSIONING
# ══════════════════════════════════════════════════════════════════════════════
# Mirror every existing /api/<path> rule under /api/v1/<path> so future
# breaking API changes can ship as /api/v2 without forcing existing clients
# (or the bundled dashboard.js) to switch. This is purely additive — the
# unversioned /api routes stay as the default for now.
#
# We do this *after* all blueprints register so we capture their rules. Skip
# the SSE stream endpoints (they share view functions across long-lived
# connections; double-registration causes endpoint name collisions in Flask).
_API_VERSION_PREFIX = "/api/v1"
_versioned: list[tuple[str, str]] = []
for _rule in list(app.url_map.iter_rules()):
    _path = str(_rule.rule)
    if not _path.startswith("/api/") or _path.startswith("/api/v"):
        continue
    _view = app.view_functions.get(_rule.endpoint)
    if _view is None:
        continue
    _versioned_path = _API_VERSION_PREFIX + _path[len("/api"):]
    # Add the alias under a distinct endpoint name so Flask routing stays
    # unambiguous. We don't reuse the view function name to avoid
    # collisions across blueprints.
    _alias_endpoint = f"v1.{_rule.endpoint}"
    app.add_url_rule(
        _versioned_path,
        endpoint=_alias_endpoint,
        view_func=_view,
        methods=list(_rule.methods - {"HEAD", "OPTIONS"}) if _rule.methods else None,
    )
    _versioned.append((_path, _versioned_path))
logger.info("Registered %d /api/v1 aliases", len(_versioned))


# ── Backward-compatibility re-exports ─────────────────────────────────────────
# Tests and external callers reference these names directly on the server
# module. The state dicts (``_audit_status``, ``_index_status``, ``CFG``) are
# mutated in place — never reassigned — so importers all see the same object.
# ``_is_error_status`` lives in the indexing blueprint; re-export it here so
# existing tests can ``from app.server import _is_error_status``.
from app.blueprints.indexing import _is_error_status

__all__ = [
    "app",
    "CFG",
    "CONFIG_PATH",
    "REPORTS_DIR",
    "_audit_cancel",
    "_audit_paused",
    "_audit_status",
    "_index_cancel",
    "_index_paused",
    "_index_status",
    "_is_error_status",
    "_lock",
    "_pdf_semaphore",
]
