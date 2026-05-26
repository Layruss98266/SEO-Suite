"""
Live "test connection" checks for the Settings tab.

Each check makes a minimal real API call and returns {"ok": bool, "message": str}
so the user can confirm a key actually works — not just that a field is filled.
Credentials come from the request (when the user just typed one) or fall back to
the stored config (so a masked/saved key can be tested without re-entering it).
"""

from __future__ import annotations

import logging
from typing import Any

from tools._common import safe_error

logger = logging.getLogger(__name__)

# Mirror of the secret sentinel the settings route returns for masked keys.
_SENTINEL = "••••••••"


def _val(data: dict, key: str, cfg: dict, cfg_key: str | None = None) -> str:
    """Resolve a credential: prefer a real (non-sentinel) request value, else cfg."""
    v = (data.get(key) or "").strip()
    if v and v != _SENTINEL:
        return v
    return str(cfg.get(cfg_key or key, "") or "").strip()


def _test_pagespeed(data: dict, cfg: dict) -> dict:
    key = _val(data, "pagespeed_api_key", cfg)
    if not key:
        return {"ok": False, "message": "No PageSpeed API key set."}
    try:
        from tools._common import fetch_html
        resp = fetch_html(
            "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"
            f"?url=https://example.com&key={key}",
            timeout=25,
        )
        if resp.status_code == 200:
            return {"ok": True, "message": "PageSpeed API key works."}
        if resp.status_code in (400, 403):
            return {"ok": False, "message": "PageSpeed rejected the key (invalid or API not enabled)."}
        return {"ok": False, "message": f"PageSpeed returned HTTP {resp.status_code}."}
    except (OSError, ValueError) as exc:
        logger.warning("_test_pagespeed failed: %s", exc)
        return {"ok": False, "message": safe_error(exc)}


def _test_groq(data: dict, cfg: dict) -> dict:
    key = _val(data, "groq_api_key", cfg)
    if not key:
        return {"ok": False, "message": "No Groq API key set."}
    try:
        from tools.ai_assist import _chat
        _chat([{"role": "user", "content": "ping"}], key, max_tokens=1)
        return {"ok": True, "message": "Groq API key works."}
    except Exception as exc:
        logger.warning("_test_groq failed: %s", exc)
        return {"ok": False, "message": safe_error(exc)}


def _test_bing(data: dict, cfg: dict) -> dict:
    key = _val(data, "bing_api_key", cfg)
    if not key:
        return {"ok": False, "message": "No Bing API key set."}
    try:
        from tools.bing_webmaster import _get
        res = _get("GetUserSites", key)
        if isinstance(res, dict) and res.get("ErrorCode"):
            return {"ok": False, "message": f"Bing rejected the key: {res.get('Message', 'invalid key')}."}
        return {"ok": True, "message": "Bing Webmaster API key works."}
    except (OSError, ValueError) as exc:
        logger.warning("_test_bing failed: %s", exc)
        return {"ok": False, "message": safe_error(exc)}


def _test_moz(data: dict, cfg: dict) -> dict:
    access_id = _val(data, "moz_access_id", cfg)
    secret    = _val(data, "moz_secret_key", cfg)
    if not access_id or not secret:
        return {"ok": False, "message": "Both Moz Access ID and Secret Key are required."}
    try:
        from tools.phase4 import domain_authority
        res = domain_authority("https://example.com", access_id, secret)
        if res.get("status") == "error":
            return {"ok": False, "message": "Moz rejected the credentials."}
        return {"ok": True, "message": "Moz API credentials work."}
    except (OSError, ValueError) as exc:
        logger.warning("_test_moz failed: %s", exc)
        return {"ok": False, "message": safe_error(exc)}


def _test_serpapi(data: dict, cfg: dict) -> dict:
    key = _val(data, "serpapi_key", cfg)
    if not key:
        return {"ok": False, "message": "No SerpAPI key set."}
    try:
        from core.security import safe_requests_get
        resp = safe_requests_get(
            "https://serpapi.com/search",
            params={"api_key": key, "q": "test", "num": 1, "engine": "google"},
            timeout=15,
        )
        body = resp.json() if resp.status_code == 200 else {}
        if resp.status_code == 200 and "error" not in body:
            return {"ok": True, "message": "SerpAPI key works."}
        msg = body.get("error", f"HTTP {resp.status_code}")
        return {"ok": False, "message": f"SerpAPI rejected the key: {msg}."}
    except (OSError, ValueError) as exc:
        logger.warning("_test_serpapi failed: %s", exc)
        return {"ok": False, "message": safe_error(exc)}


def _test_dataforseo(data: dict, cfg: dict) -> dict:
    login = _val(data, "dataforseo_login", cfg)
    pw    = _val(data, "dataforseo_password", cfg)
    if not login or not pw:
        return {"ok": False, "message": "Both DataForSEO login and password are required."}
    try:
        from core.security import safe_requests_get
        resp = safe_requests_get(
            "https://api.dataforseo.com/v3/appendix/user_data",
            auth=(login, pw), timeout=15,
        )
        if resp.status_code == 200 and resp.json().get("status_code") == 20000:
            return {"ok": True, "message": "DataForSEO credentials work."}
        return {"ok": False, "message": "DataForSEO rejected the credentials."}
    except (OSError, ValueError) as exc:
        logger.warning("_test_dataforseo failed: %s", exc)
        return {"ok": False, "message": safe_error(exc)}


def _test_gsc(data: dict, cfg: dict) -> dict:
    try:
        from core.checker import build_gsc_service
        svc = build_gsc_service()
        if svc is None:
            return {"ok": False, "message": "Could not build GSC client — check the credentials file path."}
        svc.sites().list().execute()
        return {"ok": True, "message": "Google Search Console credentials work."}
    except Exception as exc:
        logger.warning("_test_gsc failed: %s", exc)
        return {"ok": False, "message": safe_error(exc)}


_TESTS = {
    "pagespeed":  _test_pagespeed,
    "groq":       _test_groq,
    "bing":       _test_bing,
    "moz":        _test_moz,
    "serpapi":    _test_serpapi,
    "dataforseo": _test_dataforseo,
    "gsc":        _test_gsc,
}


def run_test(provider: str, data: dict, cfg: dict) -> dict[str, Any]:
    """Dispatch a connection test for *provider*. Returns {ok, message}."""
    fn = _TESTS.get(provider)
    if not fn:
        return {"ok": False, "message": f"Unknown provider: {provider}"}
    return fn(data or {}, cfg or {})
