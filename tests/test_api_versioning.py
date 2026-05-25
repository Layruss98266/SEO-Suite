"""Tests for /api/v1 versioned aliases.

The server mirrors every /api/* route under /api/v1/* so future breaking
changes can ship as /api/v2 without forcing existing clients (or the bundled
dashboard.js) to switch.
"""

from __future__ import annotations

import pytest

from app import server


@pytest.fixture
def client():
    server.app.config["TESTING"] = True
    with server.app.test_client() as c:
        yield c


class TestV1Aliases:
    def test_aliases_exist_for_unauth_get(self, client):
        """A versioned alias should respond the same way as the unversioned route."""
        # /api/use_cases is auth-gated — both should 401.
        r_unv = client.get("/api/use_cases")
        r_v1 = client.get("/api/v1/use_cases")
        assert r_unv.status_code == r_v1.status_code

    def test_aliases_exist_for_post(self, client):
        """POST endpoints should also be mirrored."""
        r_unv = client.post("/api/tools/serp_preview", json={})
        r_v1 = client.post("/api/v1/tools/serp_preview", json={})
        # Both should return the same status (401 unauth, or 400 missing url
        # if a future change lets unauth through).
        assert r_unv.status_code == r_v1.status_code

    def test_at_least_one_v1_route_registered(self):
        """Sanity check: the versioned-alias loop actually fired."""
        v1_count = sum(
            1
            for r in server.app.url_map.iter_rules()
            if str(r.rule).startswith("/api/v1/")
        )
        assert v1_count > 0

    def test_v1_count_matches_api_count(self):
        """Every /api/<path> should have a matching /api/v1/<path>.

        Subtract the v1 paths themselves and the static endpoint from the
        comparison.
        """
        api_paths = set()
        v1_paths = set()
        for r in server.app.url_map.iter_rules():
            p = str(r.rule)
            if p.startswith("/api/v1/"):
                # Strip prefix → leaves the bare "/<path>" suffix
                v1_paths.add(p[len("/api/v1") :])
            elif p.startswith("/api/"):
                api_paths.add(p[len("/api") :])

        # Every unversioned path should have a v1 mirror.
        missing = api_paths - v1_paths
        assert not missing, f"Missing /api/v1 aliases for: {sorted(missing)}"

    def test_unversioned_endpoint_still_default(self, client):
        """Unversioned routes must keep working — the v1 aliases are additive."""
        r = client.get("/health")
        assert r.status_code == 200
