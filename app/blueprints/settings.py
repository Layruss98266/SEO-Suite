"""Settings, profiles, file upload, and audit comparison routes.

Owns:
* ``GET/POST /api/settings`` — read/write ``config.json`` with secret masking
* ``POST /api/settings/test/<provider>`` — live "test connection" for an API key
* ``GET/POST/DELETE /api/profiles`` — saved audit configurations
* ``POST /api/upload`` — CSV/XLSX URL list upload (formula-injection sanitised)
* ``GET /api/compare`` — diff two audit XLSX reports

The settings allow-list strictly bounds what keys ``POST /api/settings`` will
write to ``config.json`` — anything else is dropped and reported back in
``rejected_keys``. Secrets are masked on read and preserved (not overwritten
by the sentinel) on write.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime

from flask import Blueprint, jsonify, request
from werkzeug.utils import secure_filename

from app import state
from app.state import (
    CFG,
    CONFIG_PATH,
    PROFILES_PATH,
    REPORTS_DIR,
    UPLOAD_DIR,
    _safe_report_path,
    _sanitize_csv,
)
from core.auth import login_required
from core.checker import load_config, load_from_csv_excel

logger = logging.getLogger(__name__)

bp = Blueprint("settings", __name__)


# ── Settings allowlist + masking ──────────────────────────────────────────────
# Keys allowed in POST /api/settings — anything not in this set is dropped
# silently so a malicious client can't inject arbitrary keys into config.json.
_SETTINGS_ALLOWED_KEYS = {
    "parallel_tabs", "gsc", "email", "slack", "teams", "schedule",
    "priority", "track_keywords", "timings", "thresholds", "proxies",
    # API keys — kept in config so they persist across restarts without re-entry
    "pagespeed_api_key",              # PageSpeed Insights
    "serpapi_key",                    # SerpAPI rank tracking
    "dataforseo_login",               # DataForSEO login email
    "dataforseo_password",            # DataForSEO API password
    "moz_access_id",                  # Moz domain authority
    "moz_secret_key",                 # Moz secret
    "indexnow_key", "indexnow_host",  # IndexNow
    "bing_api_key",                   # Bing Webmaster
    "groq_api_key",                   # Groq AI
    "allow_signup",                   # Public self-registration toggle
}

# Sentinel returned by GET in place of a set secret, and recognised by POST as
# "unchanged — keep the stored value". Never the literal value of a real key.
_SECRET_SENTINEL = "••••••••"

# Top-level secret keys masked on GET and preserved-if-unchanged on POST.
_SECRET_TOP_KEYS = {
    "pagespeed_api_key", "serpapi_key", "dataforseo_password", "moz_secret_key",
    "indexnow_key", "bing_api_key", "groq_api_key",
}
# Secret fields inside nested config objects.
_SECRET_NESTED = {
    "email": {"smtp_pass"},
    "slack": {"webhook_url"},
    "teams": {"webhook_url"},
}


def _mask_settings(cfg: dict) -> dict:
    """Return a copy of *cfg* with secret values replaced by the sentinel.

    Credentials are never shipped to the browser in plaintext on GET.
    """
    masked = dict(cfg)
    for k in _SECRET_TOP_KEYS:
        if masked.get(k):
            masked[k] = _SECRET_SENTINEL
    for parent, fields in _SECRET_NESTED.items():
        if isinstance(masked.get(parent), dict):
            sub = dict(masked[parent])
            for f in fields:
                if sub.get(f):
                    sub[f] = _SECRET_SENTINEL
            masked[parent] = sub
    return masked


def _merge_settings(incoming: dict, existing: dict) -> dict:
    """Merge *incoming* (allow-listed) into *existing*.

    The secret sentinel means "leave the stored value untouched". Nested
    objects are merged field-by-field so a sentinel in one field doesn't wipe
    its siblings.
    """
    merged = dict(existing)
    for k, v in incoming.items():
        if k in _SECRET_NESTED and isinstance(v, dict):
            base = dict(existing.get(k) or {})
            for fk, fv in v.items():
                if fk in _SECRET_NESTED[k] and fv == _SECRET_SENTINEL:
                    continue  # unchanged secret — keep stored value
                base[fk] = fv
            merged[k] = base
        elif k in _SECRET_TOP_KEYS and v == _SECRET_SENTINEL:
            continue  # unchanged secret — keep stored value
        else:
            merged[k] = v
    return merged


def _validate_settings(cfg: dict) -> str | None:
    """Return an error message if any value is malformed, else None."""
    email = cfg.get("email")
    if isinstance(email, dict) and email.get("smtp_port") not in (None, ""):
        try:
            port = int(email["smtp_port"])
            if not (1 <= port <= 65535):
                return "SMTP port must be between 1 and 65535"
        except (TypeError, ValueError):
            return "SMTP port must be a number"
    host = cfg.get("indexnow_host")
    if host and not re.match(r"^[A-Za-z0-9.-]+$", str(host)):
        return "IndexNow host must be a bare hostname (no scheme or path), e.g. example.com"
    for parent in ("slack", "teams"):
        block = cfg.get(parent)
        if isinstance(block, dict):
            wh = block.get("webhook_url")
            if wh and wh != _SECRET_SENTINEL and not str(wh).startswith("https://"):
                return f"{parent.title()} webhook URL must start with https://"
    creds = cfg.get("gsc", {})
    if isinstance(creds, dict):
        cf = creds.get("credentials_file", "")
        if cf and (".." in cf or cf.startswith(("/", "\\"))):
            return "GSC credentials file must be a relative filename, not an absolute or traversal path"
    return None


# ── Settings ──────────────────────────────────────────────────────────────────
@bp.route("/api/settings", methods=["GET", "POST"])
@login_required
def api_settings():
    import core.checker as _checker_mod
    import core.seo_audit as _audit_mod

    if request.method == "POST":
        new_cfg = request.get_json() or {}
        if not isinstance(new_cfg, dict):
            return jsonify({"error": "JSON object required"}), 400
        filtered = {k: v for k, v in new_cfg.items() if k in _SETTINGS_ALLOWED_KEYS}
        rejected = sorted(set(new_cfg) - _SETTINGS_ALLOWED_KEYS)
        err = _validate_settings(filtered)
        if err:
            return jsonify({"error": err}), 400
        existing = json.loads(state.CONFIG_PATH.read_text()) if state.CONFIG_PATH.exists() else {}
        merged = _merge_settings(filtered, existing)
        state.CONFIG_PATH.write_text(json.dumps(merged, indent=2))
        # Refresh in-process globals so the next run uses the saved values.
        # Mutate in place (clear+update) so existing imports keep their reference.
        refreshed = load_config()
        state.CFG.clear()
        state.CFG.update(refreshed)
        _checker_mod.CFG = state.CFG
        _audit_mod.CFG = state.CFG
        resp = {"message": "Settings saved ✓"}
        if rejected:
            resp["rejected_keys"] = rejected
        return jsonify(resp)

    raw = json.loads(state.CONFIG_PATH.read_text()) if state.CONFIG_PATH.exists() else {}
    return jsonify(_mask_settings(raw))


@bp.route("/api/settings/test/<provider>", methods=["POST"])
@login_required
def api_settings_test(provider):
    """Live 'test connection' for an API credential.

    Credentials come from the request body (just-typed) or fall back to stored
    config (masked/saved key).
    """
    data = request.get_json(silent=True) or {}
    from tools.connection_tests import run_test

    return jsonify(run_test(provider, data, CFG))


# ── Profiles ──────────────────────────────────────────────────────────────────
def _load_profiles() -> dict:
    if PROFILES_PATH.exists():
        try:
            return json.loads(PROFILES_PATH.read_text())
        except Exception:
            pass
    return {}


def _save_profiles(p: dict) -> None:
    PROFILES_PATH.write_text(json.dumps(p, indent=2))


@bp.route("/api/profiles", methods=["GET", "POST", "DELETE"])
@login_required
def api_profiles():
    profiles = _load_profiles()
    if request.method == "GET":
        return jsonify(profiles)
    if request.method == "DELETE":
        name = request.args.get("name", "").strip()
        if name in profiles:
            del profiles[name]
            _save_profiles(profiles)
        return jsonify({"ok": True, "profiles": profiles})
    # POST: save
    data = request.get_json(force=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "name required"}), 400
    profiles[name] = {
        "use_cases": data.get("use_cases", []),
        "tasks": data.get("tasks", []),
        "keywords": data.get("keywords", ""),
        "limit": data.get("limit", 10),
        "saved_at": datetime.now().isoformat(),
    }
    _save_profiles(profiles)
    return jsonify({"ok": True, "profiles": profiles})


# ── Upload ────────────────────────────────────────────────────────────────────
@bp.route("/api/upload", methods=["POST"])
@login_required
def api_upload():
    """Upload a CSV/Excel file. Returns server path for use as 'input' with input_type='csv'."""
    if "file" not in request.files:
        return jsonify({"error": "No file in request"}), 400
    f = request.files["file"]
    if not f.filename:
        return jsonify({"error": "No file selected"}), 400
    name = f.filename
    if not name.lower().endswith((".csv", ".xlsx", ".xls", ".tsv", ".txt")):
        return jsonify({"error": "Only .csv .xlsx .xls .tsv .txt allowed"}), 400
    # werkzeug's hardened sanitizer handles unicode + reserved Windows names.
    safe = secure_filename(name) or "upload"
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = UPLOAD_DIR / f"{ts}_{safe}"
    try:
        f.save(str(dest))
    except Exception as e:
        return jsonify({"error": f"Save failed: {e}"}), 500

    # Sanitize CSV content: strip formula prefixes that could execute in Excel.
    if safe.lower().endswith((".csv", ".tsv", ".txt")):
        try:
            raw = dest.read_text(encoding="utf-8", errors="replace")
            sanitized = _sanitize_csv(raw)
            dest.write_text(sanitized, encoding="utf-8")
        except Exception:
            pass  # best-effort — file is still usable even if sanitization fails

    warning = ""
    try:
        urls = load_from_csv_excel(str(dest))
        count = len(urls)
    except Exception as exc:
        count = 0
        warning = str(exc)
    body = {"path": str(dest), "filename": safe, "url_count": count}
    if warning:
        body["warning"] = warning
    return jsonify(body)


# ── Compare ───────────────────────────────────────────────────────────────────
@bp.route("/api/compare")
@login_required
def api_compare():
    """Compare two audit XLSX reports — returns score diffs per URL."""
    a_name = request.args.get("a", "")
    b_name = request.args.get("b", "")
    pa = _safe_report_path(a_name, (".xlsx",))
    pb = _safe_report_path(b_name, (".xlsx",))
    if pa is None or pb is None:
        return jsonify({"error": "invalid filenames"}), 400
    if not (pa.exists() and pb.exists()):
        return jsonify({"error": "report(s) not found"}), 404
    try:
        import openpyxl as _ox

        def _scores(p):
            wb = _ox.load_workbook(p, read_only=True, data_only=True)
            ws = wb["Summary"]
            out = {}
            for row in ws.iter_rows(min_row=2, values_only=True):
                if not row or row[1] is None:
                    continue
                out[str(row[1])] = {
                    "score": row[2] or 0,
                    "pass": row[3] or 0,
                    "warn": row[4] or 0,
                    "fail": row[5] or 0,
                    "top_issue": row[6] or "",
                }
            return out

        a = _scores(pa)
        b = _scores(pb)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    all_urls = sorted(set(a) | set(b))
    rows = []
    for u in all_urls:
        sa = a.get(u, {}).get("score")
        sb = b.get(u, {}).get("score")
        rows.append(
            {
                "url": u,
                "a_score": sa,
                "b_score": sb,
                "delta": (sb - sa) if sa is not None and sb is not None else None,
                "added": sa is None,
                "removed": sb is None,
            }
        )
    improved = sum(1 for r in rows if r["delta"] is not None and r["delta"] > 0)
    declined = sum(1 for r in rows if r["delta"] is not None and r["delta"] < 0)
    return jsonify(
        {
            "a": a_name,
            "b": b_name,
            "rows": rows,
            "improved": improved,
            "declined": declined,
            "added": sum(1 for r in rows if r["added"]),
            "removed": sum(1 for r in rows if r["removed"]),
        }
    )


def register(app, limiter) -> None:
    """Register the blueprint and apply the rate limit on /api/settings/test."""
    app.register_blueprint(bp)
    limiter.limit("20 per minute")(app.view_functions["settings.api_settings_test"])
