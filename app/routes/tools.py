"""
Tools blueprint — /api/tools/* routes.

Covers: quick tools, GSC analytics, GSC opportunities, Bing,
        IndexNow, sitemap audit, schema validate, keyword research,
        performance opportunities, AI assist, generators,
        notify_test.

Shared state imports:
    from app.state import CFG
"""

from flask import Blueprint

tools_bp = Blueprint("tools", __name__)

# TODO: migrate routes from server.py
