"""
Shared utilities for the tool modules.

Centralizes HTTP fetching (size-capped, retrying, SSRF-safe), error message
sanitisation, and XML escaping so individual tools don't re-implement them.
"""

from __future__ import annotations

import time
from html import escape as _html_escape

import requests

from core.security import safe_requests_get

HEADERS: dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}
DEFAULT_TIMEOUT = 15
MAX_RESPONSE_BYTES = 5_000_000  # 5 MB


class ToolFetchError(Exception):
    """Raised by fetch_html when a fetch fails or the response is too large."""


def safe_error(exc: Exception) -> str:
    """Map an exception to user-safe text. Never leaks tracebacks/paths/internals."""
    if isinstance(exc, ToolFetchError | ValueError):
        return str(exc)
    if isinstance(exc, requests.Timeout):
        return "The request timed out. Try again."
    if isinstance(exc, requests.ConnectionError):
        return "Could not connect to the server. Check the URL and try again."
    return "Request failed. Please try again."


def fetch_html(
    url: str,
    *,
    max_bytes: int = MAX_RESPONSE_BYTES,
    timeout: int = DEFAULT_TIMEOUT,
    retries: int = 2,
    headers: dict[str, str] | None = None,
) -> requests.Response:
    """Fetch a URL via the SSRF-safe wrapper, size-capped and with retry.

    - safe_requests_get applies SSRF validation, per-hop redirect checks, and the
      process-wide DNS-rebinding guard.
    - Aborts (ToolFetchError) if Content-Length or streamed bytes exceed max_bytes.
    - Retries on ConnectionError/Timeout/HTTP-5xx with exponential backoff.
    """
    last_exc: Exception | None = None
    for attempt in range(retries + 1):
        try:
            resp = safe_requests_get(
                url, headers=headers or HEADERS, timeout=timeout, stream=True
            )
            if resp.status_code >= 500:
                last_exc = ToolFetchError(f"Server returned HTTP {resp.status_code}")
                resp.close()
                if attempt < retries:
                    time.sleep(0.5 * (2 ** attempt))
                    continue
                raise last_exc

            declared = resp.headers.get("Content-Length")
            if declared is not None:
                try:
                    if int(declared) > max_bytes:
                        resp.close()
                        raise ToolFetchError(
                            f"Response too large ({int(declared) // 1_000_000} MB, max {max_bytes // 1_000_000} MB)"
                        )
                except ValueError:
                    pass

            total = 0
            body = bytearray()
            for chunk in resp.iter_content(chunk_size=65536):
                if not chunk:
                    continue
                total += len(chunk)
                if total > max_bytes:
                    resp.close()
                    raise ToolFetchError(
                        f"Response too large (>{max_bytes // 1_000_000} MB)"
                    )
                body.extend(chunk)

            resp._content = bytes(body)  # type: ignore[attr-defined]
            return resp
        except (requests.ConnectionError, requests.Timeout) as exc:
            last_exc = exc
            if attempt < retries:
                time.sleep(0.5 * (2 ** attempt))
                continue
            raise ToolFetchError(safe_error(exc)) from exc
    raise ToolFetchError(safe_error(last_exc) if last_exc else "Fetch failed")


def xml_text(value: object) -> str:
    """XML-escape a value (& < > \" ') for safe interpolation into generated XML."""
    if value is None:
        return ""
    return _html_escape(str(value), quote=True)
