# Tools & Generators Production Hardening — Design

**Date:** 2026-05-23
**Status:** Approved, pending implementation plan
**Scope:** `tools/quick_tools.py`, `tools/generators.py`, `tools/sitemap_audit.py`, `tools/schema_validator.py`, `tools/ai_assist.py` + new `tools/_common.py`

## Goal

Bring the analysis tools and generators to production-level quality across three
dimensions simultaneously: **correctness & safety**, **reliability**, and
**richer output**. Single pass covering all tool modules and the AI layer.

## Constraints

- **Extend existing response shapes** — additive fields only. No redesign of
  shapes the frontend (`app/static/js/dashboard.js`) or tests already read.
  The one exception: a shape that is genuinely broken or self-contradictory may
  be fixed in place, with its specific consumers updated.
- **No new tools.** Improve the tools that exist.
- **No unrelated refactoring** or frontend changes beyond what a fixed shape requires.
- All 142 existing tests must remain green.

## Architecture — shared `tools/_common.py` layer

Every tool currently re-implements the same fetch boilerplate and the same
`except Exception as e: return {"ok": False, "error": str(e)}` pattern. That
duplication is where the bugs and leaks live. Centralize it:

```
tools/_common.py

  HEADERS              # single canonical User-Agent dict
  DEFAULT_TIMEOUT      # 15s
  MAX_RESPONSE_BYTES   # 5_000_000 (5 MB)

  class ToolFetchError(Exception): ...

  fetch_html(url, *, max_bytes=MAX_RESPONSE_BYTES, timeout=DEFAULT_TIMEOUT,
             retries=2, headers=None) -> requests.Response
      • Uses core.security.safe_requests_get (SSRF + per-hop redirect validation
        + process-wide DNS-rebinding guard already apply).
      • Streams the body; aborts if Content-Length header OR cumulative bytes
        read exceed max_bytes -> raises ToolFetchError("Response too large ...").
      • Retries up to `retries` times on ConnectionError / Timeout / HTTP 5xx,
        with short exponential backoff (0.5s, 1s).
      • Raises ToolFetchError with a clean message on final failure.

  safe_error(exc) -> str
      • Maps an exception to user-safe text. Never returns raw tracebacks,
        socket internals, or filesystem paths. Known types
        (ToolFetchError, ValueError, Timeout, ConnectionError) get specific
        friendly text; everything else -> "Request failed. Please try again."

  xml_text(value) -> str
      • XML-escapes & < > " ' for safe interpolation into generated XML.
```

All tools import from this module instead of defining their own constants and
error handling.

## Per-module changes

### `quick_tools.py` (9 live-fetch tools)

- Route all live fetches through `fetch_html` → inherit size cap + retry.
- **Bug fix:** `hreflang_validator` (line ~830) and `broken_link_checker`
  (line ~929/932) pass `allow_redirects=True` to `safe_requests_get`, which
  pops and ignores that kwarg — so redirects are NOT followed as the code
  intends. `safe_requests_get`/`safe_requests_head` already follow redirects
  with per-hop validation, so the fix is to remove the misleading kwarg and
  rely on the wrapper's built-in redirect following (final URL is on
  `resp.url`). Verify `redirect_to` detection still works against `resp.url`.
- Replace every bare `str(e)` in tool returns with `safe_error(e)`.
- `serp_snippet_preview`: resolve the real favicon from
  `<link rel="icon">` / `<link rel="shortcut icon">` when present; fall back to
  `/favicon.ico`. Additive — keep `favicon_url`, populate it more accurately.

### `generators.py` (injection + validation surface)

- **`generate_sitemap`**: XML-escape `loc`, `lastmod`, `changefreq`, `priority`
  via `xml_text`. Validate each URL has an http/https scheme (skip + count
  invalid). Validate `priority` parses to a float in [0.0, 1.0]; `changefreq`
  is in the allowed enum (`always|hourly|daily|weekly|monthly|yearly|never`).
  Invalid optional fields are dropped (not emitted), surfaced in an additive
  `warnings` list. Response keeps `ok`, `content`, `url_count`; adds `warnings`.
- **`generate_hreflang`**: validate locale matches `^([a-z]{2,3}(-[A-Za-z0-9]{2,8})?|x-default)$`
  (case-insensitive on region); validate URL scheme. Invalid pairs dropped and
  reported in `warnings`. Escape attribute values.
- **`generate_robots_txt`**: validate `crawl_delay` is numeric (drop + warn if
  not); keep paths as-is but strip newlines/CR to prevent directive injection.
  Adds `warnings`.
- **Schema generators (`generate_schema`)**: before emitting, check the
  template's `required: True` fields are present and non-empty. Missing required
  fields go into an additive `warnings` list (do not block generation — the user
  may be drafting). Existing `ok`, `schema_type`, `markup`, `json` keys unchanged.

### `sitemap_audit.py`

- **Bug fix:** today it fetches raw bytes via `safe_requests_get` AND calls
  `fetch_sitemap_urls(sitemap_url)` which fetches the same URL a second time.
  Parse URLs from the already-fetched bytes for the single (non-index) case;
  only fall back to `fetch_sitemap_urls` for sitemap-index recursion. Net: at
  most one extra fetch for index files, zero redundant fetch for plain sitemaps.
- Validate `<lastmod>` values are real ISO-8601 dates; add `invalid_lastmod`
  count to the `summary` block (additive).

### `schema_validator.py`

- Size-capped fetch via `fetch_html`; replace `str(e)` with `safe_error(e)`.
  Response shape unchanged.

### `ai_assist.py`

- `_chat`: retry on HTTP 429 (and 5xx) with backoff, respecting `Retry-After`
  when present; cap total attempts at 3.
- `draft_meta`: `validate_public_url(url)` before using the URL in the prompt;
  return `{"ok": False, "error": ...}` on failure.
- Replace `str(exc)` returns with `safe_error(exc)`.

## Error-handling contract

Every tool continues to return `{"ok": False, "error": "<message>"}`. The
message is now sanitised — no raw tracebacks, socket details, or paths.
Validation failures return specific, actionable text
(e.g. `"priority must be between 0.0 and 1.0"`).

## Testing

- `tests/test_common.py` (new): `fetch_html` size cap, retry behaviour
  (mocked), `safe_error` never leaks internals, `xml_text` escaping.
- `tests/test_quick_tools.py` (expand): redirect-following fix, favicon
  resolution, error sanitisation.
- generator validation tests: XML injection in sitemap blocked; out-of-range
  priority / bad changefreq / bad locale rejected and reported in `warnings`;
  schema required-field warnings present.
- `sitemap_audit`: single-fetch for plain sitemaps (assert fetch count);
  invalid-lastmod detection.
- All 142 existing tests stay green.

## Out of scope

- New tools or new routes.
- Response-shape redesigns (additive only).
- Frontend changes except where a genuinely broken shape forces a consumer update.
- Changes to `phase1–4.py`, `bing_webmaster.py`, `indexnow.py`,
  `keyword_research.py` (those are API-integration tools, not in this pass).
