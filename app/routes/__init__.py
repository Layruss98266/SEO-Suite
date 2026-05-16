"""
Blueprint registry.

Import and register all blueprints here so app/__init__.py
only needs one line: `from app.routes import register_blueprints`.

Migration status:
  [TODO] indexing  — routes still in app/server.py
  [TODO] audit     — routes still in app/server.py
  [TODO] tools     — routes still in app/server.py
  [TODO] reports   — routes still in app/server.py
  [TODO] settings  — routes still in app/server.py
  [TODO] misc      — routes still in app/server.py

Each TODO becomes a real Blueprint import once the route block is
extracted from server.py into its dedicated module below.
"""

from flask import Flask


def register_blueprints(app: Flask) -> None:
    """Register all blueprints with the Flask app. No-op until routes are migrated."""
    # from .indexing import indexing_bp; app.register_blueprint(indexing_bp)
    # from .audit    import audit_bp;    app.register_blueprint(audit_bp)
    # from .tools    import tools_bp;    app.register_blueprint(tools_bp)
    # from .reports  import reports_bp;  app.register_blueprint(reports_bp)
    # from .settings import settings_bp; app.register_blueprint(settings_bp)
    # from .misc     import misc_bp;     app.register_blueprint(misc_bp)
    pass
