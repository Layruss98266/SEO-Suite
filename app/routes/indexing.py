"""
Indexing blueprint — /api/index/* routes.

Migration: copy the ROUTES — Indexing block from app/server.py here,
replace `@app.route` with `@indexing_bp.route`, and remove the
corresponding block from server.py.

Shared state imports (replace server.py globals with these):
    from app.state import (
        CFG, index_status, index_queue, index_subscribers,
        index_cancel, index_paused, state_lock,
        update_last_index_run, replace_last_index_run,
        reset_last_index_run, snapshot_last_index_run,
        subscribe, unsubscribe, ERROR_STATUSES, ERROR_PREFIXES,
    )
"""

from flask import Blueprint

indexing_bp = Blueprint("indexing", __name__)

# TODO: migrate routes from server.py
