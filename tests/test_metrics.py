"""Tests for /metrics endpoint and the metrics module."""

from __future__ import annotations

import pytest

from app import server


@pytest.fixture
def client():
    server.app.config["TESTING"] = True
    with server.app.test_client() as c:
        yield c


class TestMetricsEndpoint:
    def test_metrics_route_exists(self, client):
        r = client.get("/metrics")
        # 200 if prometheus_client is installed (CI installs it), else 503.
        assert r.status_code in (200, 503)

    def test_metrics_returns_text_format(self, client):
        r = client.get("/metrics")
        if r.status_code == 503:
            pytest.skip("prometheus_client not installed")
        # Prometheus text format starts with comment lines (# HELP, # TYPE).
        body = r.data.decode("utf-8", errors="replace")
        assert "# HELP" in body or "# TYPE" in body

    def test_metrics_unauthenticated(self, client):
        """No auth required — Prometheus scrapers don't have credentials."""
        r = client.get("/metrics")
        # Should NOT be 401 (would mean a login_required snuck in).
        assert r.status_code != 401

    def test_http_counter_incremented_on_request(self, client):
        """A request to a normal route should bump http_requests_total."""
        r1 = client.get("/metrics")
        if r1.status_code == 503:
            pytest.skip("prometheus_client not installed")
        # Hit /health then scrape again — the new metric line should reflect a
        # /health request (might be at value >=1, exact value depends on
        # whether other tests have hit it already).
        client.get("/health")
        r2 = client.get("/metrics")
        body = r2.data.decode("utf-8", errors="replace")
        # Find any line referencing /health
        assert "/health" in body

    def test_metrics_endpoint_itself_not_counted(self, client):
        """Hitting /metrics shouldn't generate a /metrics row — avoids
        observer-effect noise in rate() queries."""
        r = client.get("/metrics")
        if r.status_code == 503:
            pytest.skip("prometheus_client not installed")
        body = r.data.decode("utf-8", errors="replace")
        # The endpoint string should not appear as a label value.
        assert 'endpoint="/metrics"' not in body


class TestMetricsHelpers:
    def test_record_audit_event_no_error(self):
        """record_audit_event must not raise even without prometheus."""
        from app.metrics import record_audit_event

        record_audit_event("completed")
        record_audit_event("error")
        record_audit_event("cancelled")

    def test_record_indexing_event_no_error(self):
        from app.metrics import record_indexing_event

        record_indexing_event("completed")
        record_indexing_event("error")
