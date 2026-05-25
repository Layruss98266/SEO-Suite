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
3. Disable the rate limiter so tests are not throttled.
"""
import os

# 1. Force the server module to initialise (triggers load_dotenv inside load_config).
from app import server as _server  # noqa: F401

# 2. Set auth vars to empty string so load_dotenv never re-populates them.
#    bool("") == False, so auth_enabled() returns False for every test.
os.environ["SEO_SUITE_PASSWORD_HASH"] = ""
os.environ["SEO_SUITE_USERNAME"] = ""
os.environ["SEO_SUITE_SECRET"] = ""

# 3. Disable rate limiting during tests.
_server.limiter.enabled = False
