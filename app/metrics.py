"""Prometheus metrics for the SEO Suite Flask app.

Exposes a ``/metrics`` endpoint in the standard Prometheus text format. The
endpoint is intentionally **unauthenticated** so Prometheus scrapers don't
need credentials — restrict access at the network layer (e.g. Kubernetes
NetworkPolicy, nginx ``allow``/``deny``) in production.

Metrics tracked:

* ``http_requests_total`` (counter, by method/path/status)
* ``http_request_duration_seconds`` (histogram, by method/path)
* ``audit_runs_total`` (counter, by status: started/completed/cancelled/error)
* ``indexing_runs_total`` (counter, by status)
* ``audit_running`` (gauge: 0 or 1 — live status)
* ``indexing_running`` (gauge: 0 or 1)
* ``sse_subscribers`` (gauge, by stream)

Falls back to a no-op shim if ``prometheus_client`` isn't installed so the
app still boots in trimmed environments.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from flask import Flask, Response, request

from app.state import _audit_status, _audit_subscribers, _index_status, _index_subscribers

logger = logging.getLogger(__name__)

try:
    from prometheus_client import (
        CONTENT_TYPE_LATEST,
        Counter,
        Gauge,
        Histogram,
        generate_latest,
    )

    _PROMETHEUS_AVAILABLE = True
except ImportError:
    _PROMETHEUS_AVAILABLE = False
    logger.warning(
        "prometheus_client not installed — /metrics endpoint will return 503. "
        "Run `pip install prometheus-client` to enable."
    )


# ── Metric definitions ────────────────────────────────────────────────────────
# Only build these when prometheus_client is importable; otherwise the module
# exposes no-ops so the rest of the codebase doesn't need to know.
if _PROMETHEUS_AVAILABLE:
    _http_requests = Counter(
        "http_requests_total",
        "Total HTTP requests received",
        ["method", "endpoint", "status"],
    )
    _http_duration = Histogram(
        "http_request_duration_seconds",
        "HTTP request duration",
        ["method", "endpoint"],
        buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0),
    )
    _audit_runs = Counter(
        "audit_runs_total",
        "Total SEO audit runs by terminal status",
        ["status"],
    )
    _indexing_runs = Counter(
        "indexing_runs_total",
        "Total indexing-check runs by terminal status",
        ["status"],
    )
    _audit_running_g = Gauge("audit_running", "1 if an audit is currently running")
    _indexing_running_g = Gauge(
        "indexing_running", "1 if an indexing check is currently running"
    )
    _sse_subs = Gauge(
        "sse_subscribers", "Number of live SSE subscribers", ["stream"]
    )


def record_audit_event(status: str) -> None:
    """Increment the audit_runs_total counter. No-op when prom isn't installed."""
    if _PROMETHEUS_AVAILABLE:
        _audit_runs.labels(status=status).inc()


def record_indexing_event(status: str) -> None:
    """Increment the indexing_runs_total counter. No-op when prom isn't installed."""
    if _PROMETHEUS_AVAILABLE:
        _indexing_runs.labels(status=status).inc()


def _refresh_gauges() -> None:
    """Set the gauge values from live state. Called on each /metrics scrape."""
    if not _PROMETHEUS_AVAILABLE:
        return
    _audit_running_g.set(1 if _audit_status.get("running") else 0)
    _indexing_running_g.set(1 if _index_status.get("running") else 0)
    _sse_subs.labels(stream="audit").set(len(_audit_subscribers))
    _sse_subs.labels(stream="indexing").set(len(_index_subscribers))


# ── Wiring ────────────────────────────────────────────────────────────────────

def init_metrics(app: Flask) -> None:
    """Register /metrics + the per-request hooks. Idempotent."""
    if not _PROMETHEUS_AVAILABLE:
        # Still register an endpoint so the route exists; just return 503.
        @app.route("/metrics", endpoint="metrics_unavailable")
        def _metrics_unavailable() -> Any:
            return (
                "prometheus_client not installed\n",
                503,
                {"Content-Type": "text/plain"},
            )

        return

    @app.before_request
    def _start_timer() -> None:
        # Stash start time on flask.g instead of a thread-local for simplicity.
        from flask import g

        g._metrics_start = time.perf_counter()

    @app.after_request
    def _record_http(response):
        from flask import g

        start = getattr(g, "_metrics_start", None)
        # Use the route rule (e.g. "/api/reports/preview/<filename>") instead
        # of the raw path so high-cardinality URL params don't blow up the
        # metric series cardinality. Fall back to "unknown" for 404s.
        endpoint = request.url_rule.rule if request.url_rule else "unknown"
        # Skip the /metrics endpoint itself — recording its own scrapes makes
        # the rate() math noisy without telling you anything.
        if endpoint != "/metrics":
            _http_requests.labels(
                method=request.method, endpoint=endpoint, status=response.status_code
            ).inc()
            if start is not None:
                _http_duration.labels(method=request.method, endpoint=endpoint).observe(
                    time.perf_counter() - start
                )
        return response

    @app.route("/metrics")
    def metrics() -> Any:
        """Prometheus scrape endpoint. Refreshes gauges then renders text format."""
        _refresh_gauges()
        return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)
