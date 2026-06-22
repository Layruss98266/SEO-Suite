"""
Pytest configuration for SEO Suite tests.

Strategy:
1. Force-import app.server here so load_dotenv() inside load_config() fires
   before any test module import (Python caches modules — no re-import later).
2. Set auth env vars to empty strings (NOT pop them). load_dotenv() uses
   override=False by default, so it will NOT overwrite existing keys — even
   empty-string ones. Any background threads that call load_config() during
   a test run will also call load_dotenv(), which will see the keys already
   present and leave them empty. auth_enabled() → bool("") → False throughout.
3. Set SEO_SUITE_NO_AUTH=1 so that auth_enabled() short-circuits to False even
   when data/seo_suite.db contains real users. This prevents ~50 tests from
   getting 401 on @login_required endpoints. Tests that need auth ON must call
   monkeypatch.delenv("SEO_SUITE_NO_AUTH", raising=False) in their fixture.
4. Disable the rate limiter so tests are not throttled.
"""
import os

# 1. Force the server module to initialise (triggers load_dotenv inside load_config).
from app import server as _server  # noqa: F401

# 2. Set auth vars to empty string so load_dotenv never re-populates them.
os.environ["SEO_SUITE_PASSWORD_HASH"] = ""
os.environ["SEO_SUITE_USERNAME"] = ""
os.environ["SEO_SUITE_SECRET"] = ""

# 3. Disable auth globally. auth_enabled() checks NO_AUTH before reading the DB,
#    so _load_users() is never called from auth_enabled() — user CRUD in isolated
#    fixtures (test_auth_hardening, test_gdpr, etc.) is unaffected.
os.environ["SEO_SUITE_NO_AUTH"] = "1"

# 3a. Make /openapi.yaml and /docs publicly accessible in tests (they default
#     to requiring auth so they 401 without a session or this flag).
os.environ["SEO_SUITE_PUBLIC_DOCS"] = "1"

# 4. Disable rate limiting during tests.
_server.limiter.enabled = False

# 5. Disable password-strength + breach checks during tests.
os.environ["SEO_SUITE_DISABLE_ZXCVBN"] = "1"
os.environ["SEO_SUITE_DISABLE_HIBP"] = "1"
