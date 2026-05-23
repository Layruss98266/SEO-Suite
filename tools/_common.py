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
    if isinstance(exc, (ToolFetchError, ValueError)):
        return str(exc)
    if isinstance(exc, requests.Timeout):
        return "The request timed out. Try again."
    if isinstance(exc, requests.ConnectionError):
        return "Could not connect to the server. Check the URL and try again."
    return "Request failed. Please try again."


def xml_text(value: object) -> str:
    """XML-escape a value (& < > \" ') for safe interpolation into generated XML."""
    if value is None:
        return ""
    return _html_escape(str(value), quote=True)
