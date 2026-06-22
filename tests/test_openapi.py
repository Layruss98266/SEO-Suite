"""Tests for the /openapi.yaml spec and /docs Swagger UI viewer."""

from __future__ import annotations

import pytest

from app import server


@pytest.fixture
def client():
    server.app.config["TESTING"] = True
    with server.app.test_client() as c:
        yield c


class TestOpenAPI:
    def test_spec_served_as_yaml(self, client):
        r = client.get("/openapi.yaml")
        assert r.status_code == 200
        assert "yaml" in r.content_type
        body = r.data.decode("utf-8", errors="replace")
        assert body.startswith("openapi:")
        assert "SEO Suite API" in body

    def test_spec_publicly_accessible(self, client):
        """Integrators should be able to discover the API without auth."""
        r = client.get("/openapi.yaml")
        assert r.status_code == 200  # not 401

    def test_swagger_ui_served(self, client):
        r = client.get("/docs")
        assert r.status_code == 200
        assert "text/html" in r.content_type
        body = r.data.decode("utf-8", errors="replace")
        assert "swagger-ui" in body.lower()
        # Loads the spec via JS
        assert "/openapi.yaml" in body

    def test_swagger_ui_has_csp(self, client):
        """The /docs page must set a Content-Security-Policy header."""
        r = client.get("/docs")
        assert "Content-Security-Policy" in r.headers

    def test_spec_mentions_versioned_paths(self, client):
        r = client.get("/openapi.yaml")
        body = r.data.decode("utf-8", errors="replace")
        # Doesn't have to list every v1 path, but should mention versioning.
        assert "/api/v1" in body or "Versioning" in body
