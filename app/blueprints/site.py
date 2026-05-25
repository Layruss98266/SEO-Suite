"""Public marketing site routes.

These pages are unauthenticated (the dashboard at ``/app`` requires login) and
share a small template context (year + version). The contact form has POST
rate limiting applied by the caller via :func:`register`.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime

from flask import Blueprint, jsonify, render_template, request

from core.version import VERSION

logger = logging.getLogger(__name__)

bp = Blueprint("site", __name__)


def _site_ctx() -> dict:
    """Shared template context for the marketing pages."""
    return {"year": datetime.now().year, "version": VERSION}


@bp.route("/")
def site_home():
    return render_template("site/home.html", active="home", **_site_ctx())


@bp.route("/features")
def site_features():
    return render_template("site/features.html", active="features", **_site_ctx())


@bp.route("/pricing")
def site_pricing():
    return render_template("site/pricing.html", active="pricing", **_site_ctx())


@bp.route("/blog")
def site_blog():
    return render_template("site/blog.html", active="blog", **_site_ctx())


@bp.route("/about")
def site_about():
    return render_template("site/about.html", active="about", **_site_ctx())


@bp.route("/contact", methods=["GET", "POST"])
def site_contact():
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        name = (data.get("name") or "").strip()
        email = (data.get("email") or "").strip()
        message = (data.get("message") or "").strip()
        if not (name and email and message):
            return jsonify({"ok": False, "error": "All fields are required."}), 400
        if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$", email):
            return jsonify({"ok": False, "error": "Please enter a valid email."}), 400
        # No outbound mail dependency — log the enquiry; ops can wire delivery later.
        logger.info("Contact form submission from %s <%s>: %s", name, email, message[:500])
        return jsonify({"ok": True, "message": "Thanks, your message has been received."})
    return render_template("site/contact.html", active="contact", **_site_ctx())


def register(app, limiter) -> None:
    """Register the blueprint and wire the rate limit on the contact POST.

    The limiter has to be applied to the bound view function, which only exists
    after the blueprint is registered on the app — hence this factory rather
    than a decorator at definition time.
    """
    app.register_blueprint(bp)
    limiter.limit("10 per hour", methods=["POST"])(app.view_functions["site.site_contact"])
