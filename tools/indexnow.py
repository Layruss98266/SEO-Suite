"""
IndexNow submission tool.

IndexNow is a simple ping protocol supported by Bing, Yandex, and other
search engines.  When you publish or update a URL you send a single POST
request and the engine queues it for crawling — no GSC verification needed.

Spec: https://www.indexnow.org/documentation
"""

from __future__ import annotations

import secrets
from typing import Any

from core.security import safe_requests_post, validate_public_url

# Official IndexNow endpoint (Bing accepts submissions for Bing + Yandex).
# Microsoft routes submissions to all IndexNow-supporting search engines.
INDEXNOW_ENDPOINT = "https://api.indexnow.org/indexnow"

HEADERS = {
    "Content-Type": "application/json; charset=utf-8",
    "User-Agent": "SEO-Suite/2.0 IndexNow-Client",
}


def generate_key() -> str:
    """Return a fresh 32-hex-char IndexNow API key.

    The key must be placed at ``https://{host}/{key}.txt`` containing only
    the key string so IndexNow can verify ownership.
    """
    return secrets.token_hex(16)


def submit_url(url: str, key: str, host: str, timeout: int = 10) -> dict[str, Any]:
    """Submit a single URL to IndexNow.

    Parameters
    ----------
    url:     Full URL of the page that was added/updated.
    key:     Your IndexNow API key.
    host:    The hostname that owns the key (e.g. "example.com").
    timeout: Request timeout in seconds.

    Returns a dict with ``ok`` bool and ``status`` / ``error`` detail.
    """
    try:
        url = validate_public_url(url)
    except ValueError as e:
        return {"ok": False, "error": str(e)}

    params = {
        "url": url,
        "key": key,
        "keyLocation": f"https://{host}/{key}.txt",
    }
    try:
        resp = safe_requests_post(
            INDEXNOW_ENDPOINT,
            params=params,
            headers=HEADERS,
            timeout=timeout,
        )
        if resp.status_code in (200, 202):
            return {"ok": True, "status": resp.status_code, "url": url}
        return {
            "ok": False,
            "status": resp.status_code,
            "error": f"IndexNow returned HTTP {resp.status_code}",
        }
    except Exception as e:
        return {"ok": False, "error": f"Request failed: {e}"}


def submit_bulk(
    urls: list[str],
    key: str,
    host: str,
    timeout: int = 15,
) -> dict[str, Any]:
    """Submit up to 10 000 URLs in a single IndexNow batch POST.

    URLs that fail the SSRF check are skipped and reported separately.

    Returns a summary dict with ``ok``, ``submitted``, ``skipped``, and
    per-URL ``results`` list.
    """
    safe_urls: list[str] = []
    skipped: list[dict[str, str]] = []

    for raw in urls:
        try:
            safe_urls.append(validate_public_url(raw.strip()))
        except ValueError as e:
            skipped.append({"url": raw, "reason": str(e)})

    if not safe_urls:
        return {
            "ok": False,
            "error": "No valid public URLs to submit",
            "skipped": skipped,
        }

    payload = {
        "host": host,
        "key": key,
        "keyLocation": f"https://{host}/{key}.txt",
        "urlList": safe_urls,
    }
    try:
        resp = safe_requests_post(
            INDEXNOW_ENDPOINT,
            json=payload,
            headers=HEADERS,
            timeout=timeout,
        )
        ok = resp.status_code in (200, 202)
        return {
            "ok": ok,
            "status": resp.status_code,
            "submitted": len(safe_urls),
            "skipped": skipped,
            "error": None if ok else f"IndexNow returned HTTP {resp.status_code}",
        }
    except Exception as e:
        return {
            "ok": False,
            "submitted": 0,
            "skipped": skipped,
            "error": f"Request failed: {e}",
        }
