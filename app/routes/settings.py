"""
Settings blueprint — /api/settings, /api/profiles, /api/upload,
                     /api/auth_status, /api/auth/change_credentials.

Shared state imports:
    from app.state import CFG, CONFIG_PATH, DATA_DIR, reload_cfg
"""

from flask import Blueprint

settings_bp = Blueprint("settings", __name__)

# TODO: migrate routes from server.py
