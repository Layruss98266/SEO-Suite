"""
Security helpers:

* `esc()`              — HTML-escape user data for safe interpolation in reports.
* `is_safe_url()`      — boolean SSRF check returning (ok, reason).
* `ssrf_guard()`       — same as above but raises.
* `validate_public_url()` — strict validator that returns the normalized URL
                         or raises ValueError. Use this from tool modules.
* `filter_public_urls()` — bulk filter that drops anything failing the check.
* `safe_requests_get/head()` — requests wrappers that re-validate every
                         redirect hop so a public URL cannot bounce the
                         server into localhost/private/metadata addresses.
* `public_hostname()`  — normalize a URL to its public hostname.
"""

from __future__ import annotations

import ipaddress
import socket
from html import escape as _html_escape
from urllib.parse import urljoin, urlparse, urlsplit

import requests
import urllib3.util.connection as _urllib3_conn

# ── HTML escaping ─────────────────────────────────────────────────────────────

def esc(value) -> str:
    """HTML-escape any value for safe interpolation into report templates."""
    if value is None:
        return ""
    return _html_escape(str(value), quote=True)


# ── SSRF protection ──────────────────────────────────────────────────────────

PRIVATE_HOSTNAMES = {"localhost", "localhost.localdomain"}
_METADATA_HOSTS = {"169.254.169.254", "metadata.google.internal", "metadata"}


def is_valid_http_url(url: str) -> bool:
    """Cheap structural check: is *url* a syntactically valid http(s) URL?

    Returns True only when:
      * input is a non-empty string with no whitespace, newlines, or control chars
      * scheme is http or https
      * netloc (host[:port]) is non-empty

    This is a fast, no-DNS, no-SSRF sanity gate. It is the single source of
    truth for "does this look like a URL we'd consider fetching" and is the
    first check inside `validate_public_url` (which then layers on SSRF rules).
    """
    if not url or not isinstance(url, str):
        return False
    # Reject newlines, tabs, spaces, and any ASCII control char (0x00–0x1F, 0x7F).
    # urlsplit happily accepts whitespace, which can smuggle header-injection
    # payloads ("https://example.com/\r\nHost: evil") into downstream requests.
    if any(ch.isspace() or ord(ch) < 0x20 or ord(ch) == 0x7F for ch in url):
        return False
    try:
        parts = urlsplit(url)
    except ValueError:
        return False
    if parts.scheme not in ("http", "https"):
        return False
    if not parts.netloc:
        return False
    return True


def _reject_private_ip(ip) -> None:
    if (ip.is_private or ip.is_loopback or ip.is_link_local
            or ip.is_multicast or ip.is_reserved or ip.is_unspecified):
        raise ValueError("Private, local, reserved, or metadata IP addresses are not allowed")


def public_hostname(url: str, *, strip_www: bool = True) -> str:
    """Return a normalized hostname for public URL-facing checks."""
    host = (urlparse(url).hostname or "").strip().lower().rstrip(".")
    if strip_www and host.startswith("www."):
        host = host[4:]
    return host


def validate_public_url(url: str, *, allow_empty_path: bool = True) -> str:
    """Return the URL or raise ValueError if it targets a private/internal host.

    Blocks SSRF-style requests to localhost, RFC1918/private ranges, link-local,
    loopback, multicast, reserved, unspecified, and cloud metadata addresses.
    Prefer this over `is_safe_url` inside tool modules — it raises with a
    specific message instead of returning a tuple.
    """
    if not isinstance(url, str) or not url.strip():
        raise ValueError("URL is required")
    url = url.strip()
    # Single source of truth for the scheme+netloc+no-control-chars sanity check.
    if not is_valid_http_url(url):
        raise ValueError("URL must start with http:// or https:// and contain no whitespace")
    parsed = urlparse(url)
    if not allow_empty_path and not parsed.path:
        raise ValueError("URL path is required")

    host = (parsed.hostname or "").strip().lower().rstrip(".")
    if not host:
        raise ValueError("URL host is required")
    if host in PRIVATE_HOSTNAMES or host.endswith(".localhost"):
        raise ValueError("Localhost URLs are not allowed")
    if host in _METADATA_HOSTS:
        raise ValueError("Metadata service URLs are not allowed")

    # Try to parse host as an IP literal.
    # IMPORTANT: ipaddress.ip_address() raises a plain ValueError (not the
    # subclass AddressValueError) when the input is not a valid IP address.
    # We must NOT catch ValueError here because _reject_private_ip() also
    # raises ValueError — catching both in one clause would swallow private-IP
    # rejections and allow them through. Use a sentinel variable instead.
    _ip: ipaddress.IPv4Address | ipaddress.IPv6Address | None = None
    try:
        _ip = ipaddress.ip_address(host)
    except ValueError:
        pass  # host is a hostname, not an IP literal — resolve below

    if _ip is not None:
        # Host IS a valid IP literal — reject if private/loopback/etc.
        _reject_private_ip(_ip)
    else:
        # Host is a hostname — resolve and validate every returned address.
        try:
            infos = socket.getaddrinfo(
                host,
                parsed.port or (443 if parsed.scheme == "https" else 80),
                type=socket.SOCK_STREAM,
            )
        except socket.gaierror as dns_exc:
            raise ValueError(f"Could not resolve URL host: {host}") from dns_exc
        for info in infos:
            resolved = info[4][0]
            _reject_private_ip(ipaddress.ip_address(resolved))
    # ValueError from _reject_private_ip propagates as-is
    return url


def filter_public_urls(urls: list[str]) -> list[str]:
    """Return only URLs that pass validate_public_url, order-preserving + de-duped."""
    out: list[str] = []
    seen: set[str] = set()
    for url in urls:
        try:
            safe = validate_public_url(str(url).strip())
        except Exception:
            continue
        if safe not in seen:
            seen.add(safe)
            out.append(safe)
    return out


def is_safe_url(url: str) -> tuple[bool, str]:
    """Boolean form of validate_public_url. Returns (ok, reason)."""
    try:
        validate_public_url(url)
        return True, ""
    except ValueError as e:
        return False, str(e)


def ssrf_guard(url: str) -> None:
    """Raise ValueError if URL is unsafe to fetch server-side."""
    validate_public_url(url)


# ── Safe HTTP wrappers ───────────────────────────────────────────────────────
#
# DNS rebinding caveat: the hostname is resolved here for validation, but the
# socket library does a second DNS lookup at connect time. An attacker with DNS
# control could serve a public IP during validation and switch to 127.0.0.1
# before TCP connect. Run behind a short-TTL resolver or replace with an
# SSRF-safe HTTP library if that matters for your threat model.

# ── DNS rebinding mitigation ─────────────────────────────────────────────────
#
# Process-wide patch on urllib3's connection factory: every TCP connect goes
# through here, and we re-validate the resolved IP at connect time. That closes
# the DNS rebinding window where a hostname resolves to a public IP during
# validation and a private IP at socket connect.
#
# Any private/loopback/metadata IP raises OSError, which requests surfaces as a
# ConnectionError — the same shape as a network failure, which callers already
# handle.

_orig_create_connection = _urllib3_conn.create_connection


def _pinned_create_connection(address, *args, **kwargs):
    host, port = address[0], address[1]
    # Literal IP — validate directly. Hostname — resolve and validate each result.
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        try:
            infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        except socket.gaierror:
            return _orig_create_connection(address, *args, **kwargs)
        for info in infos:
            try:
                _reject_private_ip(ipaddress.ip_address(info[4][0]))
            except ValueError as exc:
                raise OSError(
                    f"DNS rebinding guard: refusing private IP {info[4][0]} for host {host}: {exc}"
                ) from exc
    else:
        try:
            _reject_private_ip(ip)
        except ValueError as exc:
            raise OSError(f"DNS rebinding guard: {exc}") from exc
    return _orig_create_connection(address, *args, **kwargs)


# Install once at import. Idempotent — re-imports won't double-wrap.
if getattr(_urllib3_conn.create_connection, "__wrapped_by_seo_suite__", False) is not True:
    _pinned_create_connection.__wrapped_by_seo_suite__ = True  # type: ignore[attr-defined]
    _urllib3_conn.create_connection = _pinned_create_connection


def safe_requests_get(url: str, *, max_redirects: int = 5, **kwargs) -> requests.Response:
    """requests.get with URL validation before every redirect hop."""
    current = validate_public_url(url)
    kwargs.pop("allow_redirects", None)
    for _ in range(max_redirects + 1):
        resp = requests.get(current, allow_redirects=False, **kwargs)
        if not resp.is_redirect:
            return resp
        location = resp.headers.get("Location")
        if not location:
            return resp
        try:
            current = validate_public_url(urljoin(current, location))
        except ValueError as exc:
            raise ValueError(f"Redirect target blocked: {exc}") from exc
    raise ValueError("Too many redirects")


def safe_requests_head(url: str, *, max_redirects: int = 5, **kwargs) -> requests.Response:
    """requests.head with URL validation before every redirect hop."""
    current = validate_public_url(url)
    kwargs.pop("allow_redirects", None)
    for _ in range(max_redirects + 1):
        resp = requests.head(current, allow_redirects=False, **kwargs)
        if not resp.is_redirect:
            return resp
        location = resp.headers.get("Location")
        if not location:
            return resp
        try:
            current = validate_public_url(urljoin(current, location))
        except ValueError as exc:
            raise ValueError(f"Redirect target blocked: {exc}") from exc
    raise ValueError("Too many redirects")


def safe_requests_post(url: str, *, max_redirects: int = 5, **kwargs) -> requests.Response:
    """requests.post with URL validation before every redirect hop.

    IndexNow and similar outbound POST endpoints may redirect; we validate
    each hop to prevent SSRF via redirect chains.
    """
    current = validate_public_url(url)
    kwargs.pop("allow_redirects", None)
    for _ in range(max_redirects + 1):
        resp = requests.post(current, allow_redirects=False, **kwargs)
        if not resp.is_redirect:
            return resp
        location = resp.headers.get("Location")
        if not location:
            return resp
        # Redirected POSTs become GETs (HTTP 303 / real-world behaviour)
        try:
            current = validate_public_url(urljoin(current, location))
        except ValueError as exc:
            raise ValueError(f"Redirect target blocked: {exc}") from exc
        kwargs.pop("data", None)
        kwargs.pop("json", None)
    raise ValueError("Too many redirects")
