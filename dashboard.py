"""
Compatibility shim — the real Flask app lives in `app.server`.
Kept so external runners (uvicorn, supervisord, etc.) that reference
`dashboard:app` keep working. New code should `from app.server import app`.
"""
from app.server import app  # noqa: F401
