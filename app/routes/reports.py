"""
Reports blueprint — /api/reports/*, /api/history, /api/compare.

Shared state imports:
    from app.state import REPORTS_DIR, DATA_DIR, CFG
"""

from flask import Blueprint

reports_bp = Blueprint("reports", __name__)

# TODO: migrate routes from server.py
