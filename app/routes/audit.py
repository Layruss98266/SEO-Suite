"""
Audit blueprint — /api/audit/* routes.

Migration: copy the ROUTES — SEO Audit + ROUTES — Individual phase execution
blocks from app/server.py here.

Shared state imports:
    from app.state import (
        CFG, audit_status, audit_queue, audit_subscribers,
        audit_cancel, audit_paused, state_lock,
        audit_partial, audit_full_results,
        subscribe, unsubscribe, MAX_AUDIT_RESULTS,
    )
"""

from flask import Blueprint

audit_bp = Blueprint("audit", __name__)

# TODO: migrate routes from server.py
