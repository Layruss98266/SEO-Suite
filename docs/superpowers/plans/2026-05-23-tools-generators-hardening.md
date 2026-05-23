# Tools & Generators Production Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Harden all analysis tools and generators for production across correctness/safety, reliability, and richer output — via a shared `tools/_common.py` layer.

**Architecture:** Add one shared utility module (`tools/_common.py`) for size-capped retrying fetches, error sanitisation, and XML escaping. Refactor each tool module to use it. Add input validation and additive `warnings` fields to generators. Fix concrete bugs (ignored `allow_redirects`, double-fetch in sitemap audit).

**Tech Stack:** Python 3.10+, Flask, requests, BeautifulSoup4 (lxml), pytest. Linting via ruff, types via mypy.

---

## Conventions for every task

- Run a single test: `python -m pytest tests/<file>::<Class>::<test> -v`
- Run a module's tests: `python -m pytest tests/<file> -v`
- Full suite (must stay green, currently 142 passing): `python -m pytest tests/ -q`
- All file reads/writes use UTF-8 (`encoding="utf-8"`).
- Commit messages end with the Co-Authored-By trailer used in the repo.

---

## Task 1: Create `tools/_common.py` — constants, error sanitiser, XML escaper

**Files:**
- Create: `tools/_common.py`
- Test: `tests/test_common.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_common.py
import pytest

from tools._common import safe_error, xml_text, ToolFetchError, HEADERS, DEFAULT_TIMEOUT, MAX_RESPONSE_BYTES


class TestSafeError:
    def test_tool_fetch_error_message_preserved(self):
        assert safe_error(ToolFetchError("Response too large (6 MB)")) == "Response too large (6 MB)"

    def test_value_error_message_preserved(self):
        assert safe_error(ValueError("priority must be between 0.0 and 1.0")) == "priority must be between 0.0 and 1.0"

    def test_unknown_exception_is_generic(self):
        msg = safe_error(KeyError("internal_dict_key"))
        assert "internal_dict_key" not in msg
        assert msg == "Request failed. Please try again."

    def test_timeout_is_friendly(self):
        import requests
        assert safe_error(requests.Timeout("HTTPSConnectionPool host timed out")) == "The request timed out. Try again."


class TestXmlText:
    def test_escapes_all_xml_specials(self):
        assert xml_text('a&b<c>d"e\'f') == "a&amp;b&lt;c&gt;d&quot;e&#x27;f"

    def test_non_string_coerced(self):
        assert xml_text(0.8) == "0.8"

    def test_none_is_empty(self):
        assert xml_text(None) == ""


class TestConstants:
    def test_constants_present(self):
        assert "User-Agent" in HEADERS
        assert DEFAULT_TIMEOUT == 15
        assert MAX_RESPONSE_BYTES == 5_000_000
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_common.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'tools._common'`

- [ ] **Step 3: Write minimal implementation**

```python
# tools/_common.py
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_common.py -v`
Expected: PASS (all tests in TestSafeError, TestXmlText, TestConstants)

- [ ] **Step 5: Commit**

```bash
git add tools/_common.py tests/test_common.py
git commit -m "$(cat <<'EOF'
feat: add tools/_common.py with safe_error and xml_text helpers

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Add `fetch_html` to `tools/_common.py` (size cap + retry)

**Files:**
- Modify: `tools/_common.py`
- Test: `tests/test_common.py`

- [ ] **Step 1: Write the failing test**

```python
# Append to tests/test_common.py
from unittest.mock import patch, MagicMock

from tools._common import fetch_html


def _fake_response(*, status=200, headers=None, chunks=(b"<html></html>",)):
    resp = MagicMock()
    resp.status_code = status
    resp.headers = headers or {}
    resp.iter_content = MagicMock(return_value=iter(chunks))
    resp.close = MagicMock()
    return resp


class TestFetchHtml:
    def test_returns_response_under_cap(self):
        fake = _fake_response(chunks=(b"abc", b"def"))
        with patch("tools._common.safe_requests_get", return_value=fake):
            resp = fetch_html("https://example.com")
        assert resp is fake

    def test_aborts_when_content_length_exceeds_cap(self):
        fake = _fake_response(headers={"Content-Length": str(10_000_000)})
        with patch("tools._common.safe_requests_get", return_value=fake):
            with pytest.raises(ToolFetchError) as ei:
                fetch_html("https://example.com", max_bytes=5_000_000)
        assert "too large" in str(ei.value).lower()

    def test_aborts_when_streamed_bytes_exceed_cap(self):
        big = b"x" * 3_000_000
        fake = _fake_response(chunks=(big, big))  # 6 MB across chunks, no Content-Length
        with patch("tools._common.safe_requests_get", return_value=fake):
            with pytest.raises(ToolFetchError) as ei:
                fetch_html("https://example.com", max_bytes=5_000_000)
        assert "too large" in str(ei.value).lower()

    def test_retries_on_connection_error_then_succeeds(self):
        good = _fake_response()
        seq = [requests.ConnectionError("boom"), good]
        with patch("tools._common.safe_requests_get", side_effect=seq), \
             patch("tools._common.time.sleep"):
            resp = fetch_html("https://example.com", retries=2)
        assert resp is good

    def test_raises_tool_fetch_error_after_exhausting_retries(self):
        with patch("tools._common.safe_requests_get", side_effect=requests.ConnectionError("boom")), \
             patch("tools._common.time.sleep"):
            with pytest.raises(ToolFetchError):
                fetch_html("https://example.com", retries=2)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_common.py::TestFetchHtml -v`
Expected: FAIL with `ImportError: cannot import name 'fetch_html'`

- [ ] **Step 3: Write minimal implementation**

Add to `tools/_common.py` (after the constants, before `safe_error`):

```python
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
    # Unreachable, but keeps type-checkers happy
    raise ToolFetchError(safe_error(last_exc) if last_exc else "Fetch failed")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_common.py::TestFetchHtml -v`
Expected: PASS (all 5 tests)

- [ ] **Step 5: Commit**

```bash
git add tools/_common.py tests/test_common.py
git commit -m "$(cat <<'EOF'
feat: add size-capped retrying fetch_html to tools/_common.py

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Fix `generate_sitemap` — XML escaping + validation

**Files:**
- Modify: `tools/generators.py` (function `generate_sitemap`, ~line 724)
- Test: `tests/test_generators.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_generators.py
from tools.generators import generate_sitemap, generate_hreflang, generate_robots_txt, generate_schema


class TestGenerateSitemap:
    def test_escapes_xml_in_loc(self):
        r = generate_sitemap({"urls": [{"url": "https://e.com/?a=1&b=2"}]})
        assert r["ok"] is True
        assert "<loc>https://e.com/?a=1&amp;b=2</loc>" in r["content"]
        assert "&b=2" not in r["content"].replace("&amp;", "")  # raw & gone

    def test_injection_attempt_is_escaped(self):
        r = generate_sitemap({"urls": [{"url": "https://e.com/</loc><script>x</script>"}]})
        assert "<script>" not in r["content"]
        assert "&lt;script&gt;" in r["content"]

    def test_invalid_scheme_url_skipped_and_warned(self):
        r = generate_sitemap({"urls": [
            {"url": "https://good.com/"},
            {"url": "javascript:alert(1)"},
        ]})
        assert r["url_count"] == 1
        assert any("scheme" in w.lower() for w in r["warnings"])

    def test_priority_out_of_range_dropped_and_warned(self):
        r = generate_sitemap({"urls": [{"url": "https://e.com/", "priority": "5"}]})
        assert "<priority>" not in r["content"]
        assert any("priority" in w.lower() for w in r["warnings"])

    def test_bad_changefreq_dropped_and_warned(self):
        r = generate_sitemap({"urls": [{"url": "https://e.com/", "changefreq": "often"}]})
        assert "<changefreq>" not in r["content"]
        assert any("changefreq" in w.lower() for w in r["warnings"])

    def test_valid_optional_fields_emitted(self):
        r = generate_sitemap({"urls": [{"url": "https://e.com/", "priority": "0.8", "changefreq": "daily"}]})
        assert "<priority>0.8</priority>" in r["content"]
        assert "<changefreq>daily</changefreq>" in r["content"]
        assert r["warnings"] == []

    def test_no_urls_is_error(self):
        assert generate_sitemap({"urls": []})["ok"] is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_generators.py::TestGenerateSitemap -v`
Expected: FAIL — escaping/warnings not present (raw `&` in output, no `warnings` key)

- [ ] **Step 3: Write minimal implementation**

Replace the body of `generate_sitemap` in `tools/generators.py` with:

```python
def generate_sitemap(data: dict) -> dict:
    """
    Build an XML sitemap from a list of URL entries.
    data keys:
      urls: [{url, lastmod, changefreq, priority}]
    """
    from urllib.parse import urlparse
    from tools._common import xml_text

    _VALID_CHANGEFREQ = {"always", "hourly", "daily", "weekly", "monthly", "yearly", "never"}
    try:
        urls = data.get("urls", [])
        if not urls:
            return {"ok": False, "error": "At least one URL is required"}

        warnings: list[str] = []
        lines = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
        ]
        count = 0
        for entry in urls:
            url = (entry.get("url") or "").strip()
            if not url:
                continue
            if urlparse(url).scheme not in ("http", "https"):
                warnings.append(f"Skipped URL with invalid scheme: {url}")
                continue
            lines.append("  <url>")
            lines.append(f"    <loc>{xml_text(url)}</loc>")
            if entry.get("lastmod"):
                lines.append(f"    <lastmod>{xml_text(entry['lastmod'])}</lastmod>")
            cf = (entry.get("changefreq") or "").strip().lower()
            if cf:
                if cf in _VALID_CHANGEFREQ:
                    lines.append(f"    <changefreq>{xml_text(cf)}</changefreq>")
                else:
                    warnings.append(f"Dropped invalid changefreq '{cf}' for {url}")
            pr = entry.get("priority")
            if pr not in (None, ""):
                try:
                    pf = float(pr)
                    if 0.0 <= pf <= 1.0:
                        lines.append(f"    <priority>{xml_text(pr)}</priority>")
                    else:
                        warnings.append(f"Dropped out-of-range priority '{pr}' for {url} (must be 0.0-1.0)")
                except (TypeError, ValueError):
                    warnings.append(f"Dropped non-numeric priority '{pr}' for {url}")
            lines.append("  </url>")
            count += 1

        lines.append("</urlset>")
        return {"ok": True, "content": "\n".join(lines), "url_count": count, "warnings": warnings}
    except Exception as e:
        from tools._common import safe_error
        return {"ok": False, "error": safe_error(e)}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_generators.py::TestGenerateSitemap -v`
Expected: PASS (all 7 tests)

- [ ] **Step 5: Commit**

```bash
git add tools/generators.py tests/test_generators.py
git commit -m "$(cat <<'EOF'
fix: XML-escape and validate sitemap generator output

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Fix `generate_hreflang` — locale/URL validation + escaping

**Files:**
- Modify: `tools/generators.py` (function `generate_hreflang`, ~line 763)
- Test: `tests/test_generators.py`

- [ ] **Step 1: Write the failing test**

```python
# Append to tests/test_generators.py
class TestGenerateHreflang:
    def test_valid_pair_emitted_and_escaped(self):
        r = generate_hreflang({"items": [{"locale": "en-US", "url": "https://e.com/?a=1&b=2"}]})
        assert r["ok"] is True
        assert 'hreflang="en-US"' in r["html_tags"]
        assert "&amp;b=2" in r["html_tags"]

    def test_invalid_locale_dropped_and_warned(self):
        r = generate_hreflang({"items": [
            {"locale": "english", "url": "https://e.com/"},
            {"locale": "fr", "url": "https://e.com/fr"},
        ]})
        assert r["count"] == 1
        assert any("english" in w for w in r["warnings"])

    def test_invalid_url_scheme_dropped(self):
        r = generate_hreflang({"items": [{"locale": "en", "url": "javascript:x"}]})
        assert r["ok"] is False or r["count"] == 0

    def test_xdefault_accepted(self):
        r = generate_hreflang({"items": [{"locale": "x-default", "url": "https://e.com/"}]})
        assert 'hreflang="x-default"' in r["html_tags"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_generators.py::TestGenerateHreflang -v`
Expected: FAIL — no validation/escaping/`warnings` key present

- [ ] **Step 3: Write minimal implementation**

Replace the body of `generate_hreflang` in `tools/generators.py` with:

```python
def generate_hreflang(data: dict) -> dict:
    """
    Build hreflang link elements from a list of {locale, url} pairs.
    data keys:
      items: [{locale, url}]
      include_xdefault: bool
      xdefault_url: str
    """
    import re
    from urllib.parse import urlparse
    from tools._common import xml_text

    _LOCALE_RE = re.compile(r"^([a-z]{2,3}(-[A-Za-z0-9]{2,8})?|x-default)$", re.IGNORECASE)
    try:
        items = data.get("items", [])
        if not items:
            return {"ok": False, "error": "At least one locale/URL pair is required"}

        warnings: list[str] = []
        tags: list[str] = []
        header_vals: list[str] = []
        for item in items:
            locale = (item.get("locale") or "").strip()
            url = (item.get("url") or "").strip()
            if not locale or not url:
                continue
            if not _LOCALE_RE.match(locale):
                warnings.append(f"Dropped invalid locale '{locale}' (expected e.g. en, en-US, x-default)")
                continue
            if urlparse(url).scheme not in ("http", "https"):
                warnings.append(f"Dropped URL with invalid scheme for locale '{locale}': {url}")
                continue
            tags.append(f'<link rel="alternate" hreflang="{xml_text(locale)}" href="{xml_text(url)}">')
            header_vals.append(f'<{xml_text(url)}>; rel="alternate"; hreflang="{xml_text(locale)}"')

        if data.get("include_xdefault") and data.get("xdefault_url"):
            xd = str(data["xdefault_url"]).strip()
            if urlparse(xd).scheme in ("http", "https"):
                tags.append(f'<link rel="alternate" hreflang="x-default" href="{xml_text(xd)}">')
            else:
                warnings.append(f"Dropped x-default URL with invalid scheme: {xd}")

        if not tags:
            return {"ok": False, "error": "No valid locale/URL pairs found", "warnings": warnings}

        return {
            "ok": True,
            "html_tags": "\n".join(tags),
            "http_header": "Link: " + ", ".join(header_vals) if header_vals else "",
            "count": len(tags),
            "warnings": warnings,
        }
    except Exception as e:
        from tools._common import safe_error
        return {"ok": False, "error": safe_error(e)}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_generators.py::TestGenerateHreflang -v`
Expected: PASS (all 4 tests)

- [ ] **Step 5: Commit**

```bash
git add tools/generators.py tests/test_generators.py
git commit -m "$(cat <<'EOF'
fix: validate and escape hreflang generator output

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Fix `generate_robots_txt` — crawl_delay validation + injection guard

**Files:**
- Modify: `tools/generators.py` (function `generate_robots_txt`, ~line 684)
- Test: `tests/test_generators.py`

- [ ] **Step 1: Write the failing test**

```python
# Append to tests/test_generators.py
class TestGenerateRobotsTxt:
    def test_numeric_crawl_delay_emitted(self):
        r = generate_robots_txt({"rules": [{"user_agent": "*", "disallow": ["/admin"], "crawl_delay": "5"}]})
        assert "Crawl-delay: 5" in r["content"]
        assert r["warnings"] == []

    def test_non_numeric_crawl_delay_dropped_and_warned(self):
        r = generate_robots_txt({"rules": [{"user_agent": "*", "crawl_delay": "soon"}]})
        assert "Crawl-delay" not in r["content"]
        assert any("crawl" in w.lower() for w in r["warnings"])

    def test_newline_in_path_is_stripped(self):
        r = generate_robots_txt({"rules": [{"user_agent": "*", "disallow": ["/a\nUser-agent: evil"]}]})
        # Injected directive must not appear on its own line
        assert "User-agent: evil" not in r["content"].splitlines()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_generators.py::TestGenerateRobotsTxt -v`
Expected: FAIL — no `warnings` key; crawl_delay not validated; newline not stripped

- [ ] **Step 3: Write minimal implementation**

Replace the body of `generate_robots_txt` in `tools/generators.py` with:

```python
def generate_robots_txt(data: dict) -> dict:
    """
    Build a robots.txt from structured form data.
    data keys:
      rules:  [{user_agent, allow:[], disallow:[]}]
      sitemap: str (optional sitemap URL)
      crawl_delay: int (optional)
    """
    def _clean(s: object) -> str:
        # Strip CR/LF so a value can't inject a new directive line
        return str(s).replace("\r", " ").replace("\n", " ").strip()

    try:
        warnings: list[str] = []
        lines: list[str] = []
        rules = data.get("rules", [])
        if not rules:
            rules = [{"user_agent": "*", "disallow": [], "allow": []}]

        for rule in rules:
            ua = _clean(rule.get("user_agent", "*")) or "*"
            lines.append(f"User-agent: {ua}")
            raw_delay = rule.get("crawl_delay", "") or data.get("crawl_delay", "")
            for path in rule.get("disallow") or []:
                if path:
                    lines.append(f"Disallow: {_clean(path)}")
            for path in rule.get("allow") or []:
                if path:
                    lines.append(f"Allow: {_clean(path)}")
            if raw_delay not in (None, ""):
                try:
                    float(raw_delay)
                    lines.append(f"Crawl-delay: {_clean(raw_delay)}")
                except (TypeError, ValueError):
                    warnings.append(f"Dropped non-numeric crawl_delay '{raw_delay}' for {ua}")
            lines.append("")

        if data.get("sitemap"):
            lines.append(f"Sitemap: {_clean(data['sitemap'])}")

        return {"ok": True, "content": "\n".join(lines).strip(), "warnings": warnings}
    except Exception as e:
        from tools._common import safe_error
        return {"ok": False, "error": safe_error(e)}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_generators.py::TestGenerateRobotsTxt -v`
Expected: PASS (all 3 tests)

- [ ] **Step 5: Commit**

```bash
git add tools/generators.py tests/test_generators.py
git commit -m "$(cat <<'EOF'
fix: validate crawl_delay and block directive injection in robots.txt generator

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Add required-field warnings to `generate_schema`

**Files:**
- Modify: `tools/generators.py` (function `generate_schema`, ~line 247 — add a post-build validation block before the `return {"ok": True, ...}` at ~line 668)
- Test: `tests/test_generators.py`

- [ ] **Step 1: Write the failing test**

```python
# Append to tests/test_generators.py
class TestGenerateSchemaWarnings:
    def test_missing_required_field_warned(self):
        # Article requires headline, description, author, publisher, date_published, url
        r = generate_schema("article", {"headline": "Hi"})
        assert r["ok"] is True
        assert "warnings" in r
        assert any("author" in w.lower() for w in r["warnings"])

    def test_all_required_present_no_warnings(self):
        r = generate_schema("article", {
            "headline": "Hi", "description": "d", "author": "A",
            "publisher": "P", "date_published": "2026-01-01", "url": "https://e.com/",
        })
        assert r["ok"] is True
        assert r["warnings"] == []

    def test_unknown_type_unchanged(self):
        assert generate_schema("nope", {})["ok"] is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_generators.py::TestGenerateSchemaWarnings -v`
Expected: FAIL with `KeyError: 'warnings'`

- [ ] **Step 3: Write minimal implementation**

In `tools/generators.py`, find the success return at the end of `generate_schema` (currently around line 668):

```python
        markup = f'<script type="application/ld+json">\n{json.dumps(obj, indent=2)}\n</script>'
        return {"ok": True, "schema_type": schema_type, "markup": markup, "json": obj}
```

Replace it with:

```python
        markup = f'<script type="application/ld+json">\n{json.dumps(obj, indent=2)}\n</script>'
        warnings = []
        for field in SCHEMA_TEMPLATES[schema_type]["fields"]:
            if field.get("required") and not str(data.get(field["id"], "")).strip():
                warnings.append(f"Missing required field: {field['label']}")
        return {"ok": True, "schema_type": schema_type, "markup": markup, "json": obj, "warnings": warnings}
```

Note: the repeater field types (`faq_items`, `items`, `steps`) hold lists, not
strings; `str([]).strip()` is `"[]"` which is non-empty, so a present-but-empty
list won't false-warn. An absent key yields `""` → warns. This matches intent.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_generators.py::TestGenerateSchemaWarnings -v`
Expected: PASS (all 3 tests)

- [ ] **Step 5: Commit**

```bash
git add tools/generators.py tests/test_generators.py
git commit -m "$(cat <<'EOF'
feat: surface missing required fields as warnings in schema generator

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: Fix `quick_tools.py` redirect-following bug + error sanitisation

**Files:**
- Modify: `tools/quick_tools.py` (`hreflang_validator` ~line 830; `_check_link` ~line 929/932; replace `HEADERS`/`TIMEOUT` usage and `str(e)` returns)
- Test: `tests/test_quick_tools.py`

- [ ] **Step 1: Write the failing test**

```python
# Append to tests/test_quick_tools.py
from unittest.mock import patch, MagicMock

from tools.quick_tools import _check_link


def _resp(status=200, url="https://e.com/", headers=None):
    m = MagicMock()
    m.status_code = status
    m.url = url
    m.headers = headers or {}
    return m


class TestCheckLink:
    def test_redirect_detected_via_final_url(self):
        final = _resp(status=200, url="https://e.com/new")
        with patch("tools.quick_tools.safe_requests_head", return_value=final):
            r = _check_link("https://e.com/old", "e.com")
        assert r["redirect_to"] == "https://e.com/new"
        assert r["ok"] is True

    def test_405_falls_back_to_get(self):
        head = _resp(status=405, url="https://e.com/x")
        get  = _resp(status=200, url="https://e.com/x")
        with patch("tools.quick_tools.safe_requests_head", return_value=head), \
             patch("tools.quick_tools.safe_requests_get", return_value=get):
            r = _check_link("https://e.com/x", "e.com")
        assert r["status"] == 200
        assert r["ok"] is True

    def test_non_http_scheme_skipped(self):
        r = _check_link("mailto:a@b.com", "e.com")
        assert r["type"] == "skip"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_quick_tools.py::TestCheckLink -v`
Expected: FAIL — `safe_requests_head` is currently called with `allow_redirects=True`, and the mock signature/behaviour differs; the 405-fallback path passes `allow_redirects=True` to `safe_requests_get` which is ignored. Tests assert the corrected calls.

- [ ] **Step 3: Write minimal implementation**

In `tools/quick_tools.py`, update `_check_link` (around line 929). Change:

```python
        resp = safe_requests_head(href, headers=_LINK_HEALTH_HEADERS, timeout=8, allow_redirects=True)
        status = resp.status_code
        if status == 405:
            resp   = safe_requests_get(href, headers=_LINK_HEALTH_HEADERS, timeout=8, allow_redirects=True)
            status = resp.status_code
```

to (remove the ignored `allow_redirects` kwarg — the safe_* wrappers already follow + revalidate each hop):

```python
        resp = safe_requests_head(href, headers=_LINK_HEALTH_HEADERS, timeout=8)
        status = resp.status_code
        if status == 405:
            resp   = safe_requests_get(href, headers=_LINK_HEALTH_HEADERS, timeout=8)
            status = resp.status_code
```

In `hreflang_validator._check_url` (around line 830), change:

```python
            r = safe_requests_get(alt_url, headers=HEADERS, timeout=8, allow_redirects=True)
```

to:

```python
            r = safe_requests_get(alt_url, headers=HEADERS, timeout=8)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_quick_tools.py::TestCheckLink -v`
Expected: PASS (all 3 tests)

- [ ] **Step 5: Commit**

```bash
git add tools/quick_tools.py tests/test_quick_tools.py
git commit -m "$(cat <<'EOF'
fix: drop ignored allow_redirects kwarg in link/hreflang checkers

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: Route `schema_validator.py` through `fetch_html` + `safe_error`

**Files:**
- Modify: `tools/schema_validator.py` (`validate_url`, ~line 169-191)
- Test: `tests/test_generators.py` (new class) or `tests/test_new_tools.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_schema_validator.py
from unittest.mock import patch, MagicMock

from tools.schema_validator import validate_url


def _resp(text, status=200):
    m = MagicMock()
    m.status_code = status
    m.text = text
    m.url = "https://e.com/"
    return m


class TestValidateUrl:
    def test_rejects_private_url(self):
        r = validate_url("http://127.0.0.1/")
        assert r["ok"] is False

    def test_parses_jsonld_block(self):
        html = '<script type="application/ld+json">{"@context":"https://schema.org","@type":"Article","headline":"x","author":"a","datePublished":"2026-01-01"}</script>'
        with patch("tools.schema_validator.fetch_html", return_value=_resp(html)):
            r = validate_url("https://e.com/")
        assert r["ok"] is True
        assert "Article" in r["types_found"]

    def test_fetch_error_is_sanitised(self):
        from tools._common import ToolFetchError
        with patch("tools.schema_validator.fetch_html", side_effect=ToolFetchError("Response too large (>5 MB)")):
            r = validate_url("https://e.com/")
        assert r["ok"] is False
        assert "too large" in r["error"].lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_schema_validator.py -v`
Expected: FAIL — `validate_url` imports/uses `safe_requests_get`, not `fetch_html`; patch target missing

- [ ] **Step 3: Write minimal implementation**

In `tools/schema_validator.py`, update the import line (top of file):

```python
from core.security import validate_public_url
from tools._common import fetch_html, safe_error
```

(Remove `safe_requests_get` from the `core.security` import.)

Then in `validate_url`, replace the fetch block (currently ~line 178-191):

```python
    try:
        resp = safe_requests_get(
            url,
            timeout=timeout,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; SEO-Suite/2.0; +https://seo-suite.local)"
            },
        )
    except Exception as e:
        return {"ok": False, "error": f"Fetch failed: {e}"}
```

with:

```python
    try:
        resp = fetch_html(
            url,
            timeout=timeout,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; SEO-Suite/2.0; +https://seo-suite.local)"
            },
        )
    except Exception as e:
        return {"ok": False, "error": safe_error(e)}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_schema_validator.py -v`
Expected: PASS (all 3 tests)

- [ ] **Step 5: Commit**

```bash
git add tools/schema_validator.py tests/test_schema_validator.py
git commit -m "$(cat <<'EOF'
refactor: route schema_validator fetch through size-capped fetch_html

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: Fix `sitemap_audit.py` double-fetch + invalid-lastmod detection

**Files:**
- Modify: `tools/sitemap_audit.py` (`audit_sitemap`, ~line 60-199)
- Test: `tests/test_sitemap_audit.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_sitemap_audit.py
from unittest.mock import patch, MagicMock

from tools.sitemap_audit import audit_sitemap

_PLAIN = b'''<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://e.com/a</loc><lastmod>2026-01-01</lastmod></url>
  <url><loc>https://e.com/b</loc><lastmod>not-a-date</lastmod></url>
</urlset>'''


def _resp(content, status=200, url="https://e.com/sitemap.xml"):
    m = MagicMock()
    m.status_code = status
    m.content = content
    m.url = url
    return m


class TestAuditSitemap:
    def test_plain_sitemap_fetched_once(self):
        with patch("tools.sitemap_audit.fetch_html", return_value=_resp(_PLAIN)) as fh, \
             patch("tools.sitemap_audit.fetch_sitemap_urls") as fsu:
            r = audit_sitemap("https://e.com/sitemap.xml")
        assert r["ok"] is True
        assert fh.call_count == 1
        # For a plain (non-index) sitemap, the second network fetch must NOT happen
        assert fsu.call_count == 0
        assert r["total_urls"] == 2

    def test_invalid_lastmod_counted(self):
        with patch("tools.sitemap_audit.fetch_html", return_value=_resp(_PLAIN)), \
             patch("tools.sitemap_audit.fetch_sitemap_urls"):
            r = audit_sitemap("https://e.com/sitemap.xml")
        assert r["summary"]["invalid_lastmod"] == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_sitemap_audit.py -v`
Expected: FAIL — current code calls `fetch_sitemap_urls` (second fetch), uses `safe_requests_get` not `fetch_html`, and has no `invalid_lastmod` key

- [ ] **Step 3: Write minimal implementation**

In `tools/sitemap_audit.py`, update imports at the top:

```python
from core.checker import fetch_sitemap_urls
from core.security import validate_public_url
from tools._common import fetch_html, safe_error
```

(Remove `safe_requests_get` from the `core.security` import.)

Replace the fetch + parse section (currently lines ~78-97) so it fetches once
and only recurses for sitemap-index files. Replace:

```python
    # ── Fetch raw XML ────────────────────────────────────────────────────────
    try:
        resp = safe_requests_get(
            sitemap_url,
            timeout=timeout,
            headers={"User-Agent": "Mozilla/5.0 (compatible; SEO-Suite/2.0)"},
        )
    except Exception as e:
        return {"ok": False, "error": f"Fetch failed: {e}"}

    if resp.status_code >= 400:
        return {"ok": False, "error": f"HTTP {resp.status_code} from {sitemap_url}"}

    raw_bytes = resp.content
    size_bytes = len(raw_bytes)
    size_mb    = round(size_bytes / 1024 / 1024, 2)

    # ── Parse URLs via existing checker (handles sitemap-index recursion) ───
    all_urls: list[str] = fetch_sitemap_urls(sitemap_url)
    total_urls = len(all_urls)
```

with:

```python
    # ── Fetch raw XML once ─────────────────────────────────────────────────────
    try:
        resp = fetch_html(
            sitemap_url,
            timeout=timeout,
            headers={"User-Agent": "Mozilla/5.0 (compatible; SEO-Suite/2.0)"},
        )
    except Exception as e:
        return {"ok": False, "error": safe_error(e)}

    if resp.status_code >= 400:
        return {"ok": False, "error": f"HTTP {resp.status_code} from {sitemap_url}"}

    raw_bytes = resp.content
    size_bytes = len(raw_bytes)
    size_mb    = round(size_bytes / 1024 / 1024, 2)
    xml_text_body = raw_bytes.decode("utf-8", errors="replace")

    # ── Parse URLs from the already-fetched bytes ──────────────────────────────
    # Only recurse via fetch_sitemap_urls for a sitemap-index (extra fetches
    # are unavoidable there). A plain <urlset> is parsed locally — no re-fetch.
    is_index = "<sitemapindex" in xml_text_body.lower()
    if is_index:
        all_urls = fetch_sitemap_urls(sitemap_url)
    else:
        all_urls = re.findall(r"<loc>\s*(.*?)\s*</loc>", xml_text_body, re.IGNORECASE | re.DOTALL)
        all_urls = [u.strip() for u in all_urls if u.strip()]
    total_urls = len(all_urls)
```

Then add invalid-lastmod detection. Find the optional-field section (currently
~line 159-163) that reads:

```python
    # ── Optional field coverage (spot-check raw XML) ────────────────────────
    xml_text = raw_bytes.decode("utf-8", errors="replace")
    has_lastmod   = "<lastmod>"   in xml_text
    has_changefreq = "<changefreq>" in xml_text
    has_priority  = "<priority>"  in xml_text
```

Replace with (reuse `xml_text_body`, add lastmod validation):

```python
    # ── Optional field coverage (spot-check raw XML) ────────────────────────
    has_lastmod    = "<lastmod>"    in xml_text_body
    has_changefreq = "<changefreq>" in xml_text_body
    has_priority   = "<priority>"   in xml_text_body

    # Validate each <lastmod> is a parseable ISO-8601 date
    invalid_lastmod = 0
    for lm in re.findall(r"<lastmod>\s*(.*?)\s*</lastmod>", xml_text_body, re.IGNORECASE | re.DOTALL):
        lm = lm.strip()
        if not lm:
            continue
        try:
            from datetime import datetime
            datetime.fromisoformat(lm.replace("Z", "+00:00"))
        except ValueError:
            invalid_lastmod += 1
    if invalid_lastmod:
        issues.append({
            "level": "warning",
            "message": f"{invalid_lastmod} <lastmod> value(s) are not valid ISO-8601 dates.",
        })
```

Finally, add `"invalid_lastmod": invalid_lastmod` to the `summary` dict in the
return value (after `"has_priority": has_priority,`):

```python
            "has_priority": has_priority,
            "invalid_lastmod": invalid_lastmod,
```

Note: `error_count`/`warning_count`/`score` are computed from `issues` AFTER the
oversized/http/duplicate checks but the lastmod block above must run BEFORE the
score computation. Place the lastmod block immediately before the
`# ── Overall score ──` section so its warning is counted.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_sitemap_audit.py -v`
Expected: PASS (both tests)

- [ ] **Step 5: Commit**

```bash
git add tools/sitemap_audit.py tests/test_sitemap_audit.py
git commit -m "$(cat <<'EOF'
fix: single-fetch sitemap audit + validate lastmod dates

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 10: Harden `ai_assist.py` — 429/5xx retry + URL validation + safe_error

**Files:**
- Modify: `tools/ai_assist.py` (`_chat` ~line 24-40; `draft_meta` ~line 137-206; error returns in both)
- Test: `tests/test_ai_assist.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_ai_assist.py
from unittest.mock import patch, MagicMock

from tools.ai_assist import draft_meta, _chat


def _resp(status=200, payload=None, headers=None):
    m = MagicMock()
    m.status_code = status
    m.headers = headers or {}
    m.json.return_value = payload or {"choices": [{"message": {"content": "ok"}}]}
    def _raise():
        import requests
        if status >= 400:
            raise requests.HTTPError(f"{status}")
    m.raise_for_status.side_effect = _raise
    return m


class TestChatRetry:
    def test_retries_on_429_then_succeeds(self):
        seq = [_resp(status=429, headers={"Retry-After": "0"}), _resp(status=200)]
        with patch("tools.ai_assist.safe_requests_post", side_effect=seq), \
             patch("tools.ai_assist.time.sleep"):
            out = _chat([{"role": "user", "content": "hi"}], "key")
        assert out == "ok"


class TestDraftMeta:
    def test_rejects_private_url(self):
        r = draft_meta("http://127.0.0.1/", "t", "d", [], "key")
        assert r["ok"] is False

    def test_missing_api_key(self):
        r = draft_meta("https://e.com/", "t", "d", [], "")
        assert r["ok"] is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_ai_assist.py -v`
Expected: FAIL — `_chat` has no retry and no `time` import to patch; `draft_meta` does not validate the URL

- [ ] **Step 3: Write minimal implementation**

In `tools/ai_assist.py`, update imports at the top:

```python
import json
import time

from core.security import safe_requests_post, validate_public_url
from tools._common import safe_error
```

Replace `_chat` (lines ~24-40) with a retrying version:

```python
def _chat(messages: list[dict], api_key: str, model: str = _DEFAULT_MODEL,
          temperature: float = 0.4, max_tokens: int = 800) -> str:
    """Send a chat completion request to Groq. Retries on 429/5xx. Returns reply text."""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type":  "application/json",
    }
    body = {
        "model":       model,
        "messages":    messages,
        "temperature": temperature,
        "max_tokens":  max_tokens,
    }
    last_status = None
    for attempt in range(3):
        resp = safe_requests_post(_GROQ_CHAT_URL, headers=headers, json=body, timeout=30)
        last_status = resp.status_code
        if resp.status_code in (429,) or resp.status_code >= 500:
            if attempt < 2:
                retry_after = resp.headers.get("Retry-After")
                delay = float(retry_after) if (retry_after and retry_after.replace(".", "", 1).isdigit()) else 0.5 * (2 ** attempt)
                time.sleep(delay)
                continue
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"].strip()
    raise RuntimeError(f"Groq API unavailable (HTTP {last_status})")
```

In `draft_meta` (after the `if not api_key:` guard, ~line 147), add URL validation:

```python
    if not api_key:
        return {"ok": False, "error": "Groq API key not configured (Settings → groq_api_key)"}
    try:
        url = validate_public_url(url)
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
```

In both `explain_audit` and `draft_meta`, replace the final
`except Exception as exc: return {"ok": False, "error": str(exc)}` with:

```python
    except Exception as exc:
        return {"ok": False, "error": safe_error(exc)}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_ai_assist.py -v`
Expected: PASS (all 3 tests)

- [ ] **Step 5: Commit**

```bash
git add tools/ai_assist.py tests/test_ai_assist.py
git commit -m "$(cat <<'EOF'
feat: retry Groq calls on 429/5xx; validate URL in draft_meta

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 11: Route remaining `quick_tools.py` fetches through `fetch_html` + `safe_error`

**Files:**
- Modify: `tools/quick_tools.py` (the 6 Phase-A tools: `serp_snippet_preview`, `http_headers`, `keyword_density`, `code_to_text_ratio`, `compression_headers`, `robots_tester` — replace `safe_requests_get(...)` body fetches with `fetch_html`, and `str(e)` with `safe_error(e)`)
- Test: `tests/test_quick_tools.py`

- [ ] **Step 1: Write the failing test**

```python
# Append to tests/test_quick_tools.py
from tools.quick_tools import code_to_text_ratio


class TestCodeToTextRatio:
    def test_oversized_response_sanitised(self):
        from tools._common import ToolFetchError
        with patch("tools.quick_tools.fetch_html", side_effect=ToolFetchError("Response too large (>5 MB)")):
            r = code_to_text_ratio("https://e.com/")
        assert r["ok"] is False
        assert "too large" in r["error"].lower()

    def test_basic_ratio_computed(self):
        m = MagicMock()
        m.status_code = 200
        m.url = "https://e.com/"
        m.text = "<html><body>" + ("hello world " * 50) + "</body></html>"
        with patch("tools.quick_tools.fetch_html", return_value=m):
            r = code_to_text_ratio("https://e.com/")
        assert r["ok"] is True
        assert r["ratio_pct"] > 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_quick_tools.py::TestCodeToTextRatio -v`
Expected: FAIL — `code_to_text_ratio` uses `safe_requests_get`, not `fetch_html`; patch target missing

- [ ] **Step 3: Write minimal implementation**

In `tools/quick_tools.py`, update the import (top of file, ~line 15):

```python
from core.security import safe_requests_get, safe_requests_head, validate_public_url
from tools._common import fetch_html, safe_error
```

For each of the 6 Phase-A tools, make two mechanical changes:
1. Replace `resp = safe_requests_get(url, headers=HEADERS, timeout=TIMEOUT)` (and
   the `compression_headers` variant `headers=req_headers`) with
   `resp = fetch_html(url, headers=HEADERS)` (keep the custom headers arg where
   one is passed, e.g. `fetch_html(url, headers=req_headers)`).
2. Replace the trailing `except Exception as e: return {"ok": False, "error": str(e)}`
   with `except Exception as e: return {"ok": False, "error": safe_error(e)}`.

Concretely, the lines to change (current → new):

- `serp_snippet_preview` (~line 52): `resp = safe_requests_get(url, headers=HEADERS, timeout=TIMEOUT)` → `resp = fetch_html(url, headers=HEADERS)`
- `http_headers` (~line 237): same substitution
- `keyword_density` (~line 421): same substitution
- `code_to_text_ratio` (~line 478): same substitution
- `compression_headers` (~line 527): `resp = safe_requests_get(url, headers=req_headers, timeout=TIMEOUT)` → `resp = fetch_html(url, headers=req_headers)`
- `robots_tester` (~line 608): `resp = safe_requests_get(robots_url, headers=HEADERS, timeout=TIMEOUT)` → `resp = fetch_html(robots_url, headers=HEADERS)`

And in each of those 6 functions, change the final `str(e)` to `safe_error(e)`.

Leave `redirect_chain` (uses its own per-hop `requests.Session`), `broken_link_checker`,
and `hreflang_validator` fetch internals as they are — they were addressed in
Task 7 and rely on streaming/HEAD behaviour that `fetch_html` does not model.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_quick_tools.py::TestCodeToTextRatio -v`
Expected: PASS (both tests)

- [ ] **Step 5: Commit**

```bash
git add tools/quick_tools.py tests/test_quick_tools.py
git commit -m "$(cat <<'EOF'
refactor: route Phase-A quick tools through size-capped fetch_html

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 12: Improve `serp_snippet_preview` favicon resolution

**Files:**
- Modify: `tools/quick_tools.py` (`serp_snippet_preview`, ~line 70 favicon block)
- Test: `tests/test_quick_tools.py`

- [ ] **Step 1: Write the failing test**

```python
# Append to tests/test_quick_tools.py
from tools.quick_tools import serp_snippet_preview


class TestSerpFavicon:
    def test_uses_declared_icon_link(self):
        html = (
            '<html><head><title>T</title>'
            '<link rel="icon" href="/assets/fav.png">'
            '</head><body></body></html>'
        )
        m = MagicMock(); m.status_code = 200; m.url = "https://e.com/page"; m.text = html
        with patch("tools.quick_tools.fetch_html", return_value=m):
            r = serp_snippet_preview("https://e.com/page")
        assert r["ok"] is True
        assert r["favicon_url"] == "https://e.com/assets/fav.png"

    def test_falls_back_to_root_favicon(self):
        html = '<html><head><title>T</title></head><body></body></html>'
        m = MagicMock(); m.status_code = 200; m.url = "https://e.com/page"; m.text = html
        with patch("tools.quick_tools.fetch_html", return_value=m):
            r = serp_snippet_preview("https://e.com/page")
        assert r["favicon_url"] == "https://e.com/favicon.ico"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_quick_tools.py::TestSerpFavicon -v`
Expected: FAIL — `test_uses_declared_icon_link` fails (current code always returns `/favicon.ico`)

- [ ] **Step 3: Write minimal implementation**

In `serp_snippet_preview`, replace the favicon line (~line 70):

```python
        favicon_url = f"{parsed.scheme}://{parsed.netloc}/favicon.ico"
```

with:

```python
        icon_tag = (
            soup.find("link", rel=lambda v: v and "icon" in v.lower())
        )
        icon_href = _attr_text(icon_tag, "href") if icon_tag else ""
        if icon_href:
            favicon_url = urljoin(final_url, icon_href)
        else:
            favicon_url = f"{parsed.scheme}://{parsed.netloc}/favicon.ico"
```

(`urljoin` is already imported at the top of `quick_tools.py`.)

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_quick_tools.py::TestSerpFavicon -v`
Expected: PASS (both tests)

- [ ] **Step 5: Commit**

```bash
git add tools/quick_tools.py tests/test_quick_tools.py
git commit -m "$(cat <<'EOF'
feat: resolve declared favicon link in serp_snippet_preview

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 13: Full regression + lint pass

**Files:** none (verification only)

- [ ] **Step 1: Run the full test suite**

Run: `python -m pytest tests/ -q`
Expected: PASS — 142 prior tests + all new tests (test_common, test_generators, test_schema_validator, test_sitemap_audit, test_ai_assist, expanded test_quick_tools). Zero failures.

- [ ] **Step 2: Run ruff lint on changed modules**

Run: `python -m ruff check tools/_common.py tools/generators.py tools/quick_tools.py tools/sitemap_audit.py tools/schema_validator.py tools/ai_assist.py`
Expected: No errors. Fix any reported issues (unused imports, etc.) and re-run.

- [ ] **Step 3: Confirm app still imports**

Run: `python -c "import app.server; import tools.generators, tools.quick_tools, tools.sitemap_audit, tools.schema_validator, tools.ai_assist, tools._common; print('imports OK')"`
Expected: `imports OK`

- [ ] **Step 4: Commit any lint fixes**

```bash
git add -A
git commit -m "$(cat <<'EOF'
chore: lint fixes for tools hardening pass

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

(Skip this commit if there were no lint fixes.)

---

## Self-Review Notes (for the implementer)

- **Spec coverage:** `_common.py` (Tasks 1-2) ✓; quick_tools redirect fix (7), fetch routing (11), favicon (12) ✓; generators XML/validation (3-6) ✓; sitemap_audit double-fetch + lastmod (9) ✓; schema_validator (8) ✓; ai_assist retry+validate (10) ✓; error contract via `safe_error` throughout ✓; testing (every task + Task 13) ✓.
- **Additive-only shapes:** generators gain a `warnings` key (new); sitemap_audit gains `summary.invalid_lastmod` (new); all existing keys preserved. No consumer breakage.
- **Type consistency:** `fetch_html`, `safe_error`, `xml_text`, `ToolFetchError` names are used identically across Tasks 1-12. `fetch_html` always returns a `requests.Response` with `._content` populated so callers can use `.text`/`.content`/`.url`/`.status_code` unchanged.
- **Out of scope confirmed:** phase1-4, bing_webmaster, indexnow, keyword_research untouched.
