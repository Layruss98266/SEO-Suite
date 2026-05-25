"""
SEO Suite — entry point.

Run:   python main.py
Open:  http://localhost:8080

Project layout:
  main.py                      — entry point (this file)
  app/server.py                — Flask app factory + remaining routes
                                 (indexing, audit, reports, settings, tools)
  app/state.py                 — Shared run-state, paths, helpers, constants
  app/middleware.py            — Security headers, CSRF, error handlers
  app/blueprints/site.py       — Public marketing pages
  app/blueprints/auth_views.py — Login/signup/logout, user management
  app/blueprints/misc.py       — /app dashboard, /health, /api/use_cases, /api/tasks
  app/__init__.py              — Thin `create_app()` factory (returns app.server.app)
  app/templates/               — Jinja templates (dashboard + marketing site)
  app/static/                  — CSS / JS / assets
  core/checker.py              — Indexing checker (Playwright)
  core/seo_audit.py            — Audit orchestrator + report generation
  core/auth.py                 — Multi-user session auth + account lockout
  core/security.py             — SSRF protection, DNS rebinding guard
  core/version.py              — Single source of truth for VERSION
  tools/phase1.py              — Free on-page / technical checks
  tools/phase2.py              — PageSpeed / GSC URL inspection
  tools/phase3.py              — Search Console (clicks, queries, sitemaps)
  tools/phase4.py              — Third-party APIs (backlinks, DA, rankings)
  data/                        — Runtime outputs (reports, history, profiles, uploads)
"""
import os

# Load .env before importing the app so auth env vars (SEO_SUITE_PASSWORD_HASH,
# SEO_SUITE_SECRET, SEO_SUITE_USERNAME) are in the environment before Flask init.
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv not installed — env vars must be set externally

from app.server import app
from core.version import CLI_BANNER

if __name__ == "__main__":
    # Bind to localhost by default — the server has no authentication and accepts
    # arbitrary URLs as input, so exposing it to the LAN is unsafe. Set
    # SEO_SUITE_HOST=0.0.0.0 to opt into LAN exposure once auth is in place.
    host = os.environ.get("SEO_SUITE_HOST", "127.0.0.1")
    port = int(os.environ.get("SEO_SUITE_PORT", "8080"))
    print(f"\n  {CLI_BANNER}")
    print(f"  Open: http://{host if host != '0.0.0.0' else 'localhost'}:{port}\n")
    app.run(host=host, port=port, debug=False, threaded=True)
