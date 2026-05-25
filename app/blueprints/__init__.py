"""Flask blueprints for the SEO Suite app.

Route groups live here as separate blueprints so each module owns a coherent
slice of the URL space. Each blueprint module exposes a single ``bp`` symbol
(or a ``register(app, limiter)`` factory for blueprints that need limiter
access) which ``app/server.py`` imports and registers on the Flask app.
"""
