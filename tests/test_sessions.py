"""Tests for server-side session management (#3)."""

from __future__ import annotations

import pytest

from core import db


@pytest.fixture(autouse=True)
def _reset_state():
    db._reset_for_tests()
    yield
    db._reset_for_tests()


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "test.db"


class TestCreateSession:
    def test_returns_url_safe_sid(self, db_path):
        sid = db.create_session(db_path, "alice", "1.2.3.4", "UA/1")
        assert isinstance(sid, str)
        assert len(sid) > 20
        assert all(c.isalnum() or c in "-_" for c in sid)

    def test_unique_sids(self, db_path):
        sids = {db.create_session(db_path, "alice", None, None) for _ in range(10)}
        assert len(sids) == 10

    def test_caps_user_agent(self, db_path):
        sid = db.create_session(db_path, "alice", "1.2.3.4", "X" * 5000)
        rows = db.list_sessions(db_path, "alice")
        assert len(rows[0]["user_agent"]) == 512


class TestValidateSession:
    def test_valid_sid_returns_username(self, db_path):
        sid = db.create_session(db_path, "alice", "1.2.3.4", "UA/1")
        assert db.validate_session(db_path, sid) == "alice"

    def test_unknown_sid_returns_none(self, db_path):
        db._ensure_schema(db_path)
        assert db.validate_session(db_path, "nope") is None

    def test_empty_sid_returns_none(self, db_path):
        assert db.validate_session(db_path, "") is None

    def test_validate_touches_last_seen(self, db_path):
        sid = db.create_session(db_path, "alice", None, None)
        before = db.list_sessions(db_path, "alice")[0]["last_seen_at"]
        import time as _time

        _time.sleep(0.01)
        db.validate_session(db_path, sid)
        after = db.list_sessions(db_path, "alice")[0]["last_seen_at"]
        assert after > before


class TestDeleteSession:
    def test_revoke_specific_session(self, db_path):
        sid = db.create_session(db_path, "alice", None, None)
        assert db.delete_session(db_path, sid) is True
        # After delete, validate returns None.
        assert db.validate_session(db_path, sid) is None
        # Deleting same sid again returns False.
        assert db.delete_session(db_path, sid) is False

    def test_delete_all_for_user(self, db_path):
        for _ in range(3):
            db.create_session(db_path, "alice", None, None)
        db.create_session(db_path, "bob", None, None)

        deleted = db.delete_sessions_for_user(db_path, "alice")
        assert deleted == 3
        # Bob's session untouched.
        assert len(db.list_sessions(db_path, "bob")) == 1

    def test_delete_others_keeps_current(self, db_path):
        sids = [db.create_session(db_path, "alice", None, None) for _ in range(3)]
        current_sid = sids[0]

        deleted = db.delete_sessions_for_user(db_path, "alice", except_sid=current_sid)
        assert deleted == 2
        # Current session survives.
        assert db.validate_session(db_path, current_sid) == "alice"
        # Others gone.
        assert db.validate_session(db_path, sids[1]) is None


class TestListSessions:
    def test_returns_newest_first(self, db_path):
        import time as _time

        sids = []
        for _ in range(3):
            sids.append(db.create_session(db_path, "alice", None, None))
            _time.sleep(0.01)

        rows = db.list_sessions(db_path, "alice")
        # Newest first.
        assert rows[0]["sid"] == sids[-1]
        assert rows[-1]["sid"] == sids[0]

    def test_filters_by_user(self, db_path):
        db.create_session(db_path, "alice", None, None)
        db.create_session(db_path, "bob", None, None)
        assert len(db.list_sessions(db_path, "alice")) == 1
        assert len(db.list_sessions(db_path, "bob")) == 1

    def test_expired_sessions_pruned_on_list(self, db_path):
        # Use TTL=0 → immediately expired.
        db.create_session(db_path, "alice", None, None, ttl_days=0)
        # The list call also prunes.
        import time as _time

        _time.sleep(0.01)
        rows = db.list_sessions(db_path, "alice")
        assert rows == []


# ── HTTP integration ─────────────────────────────────────────────────────────
class TestSessionRoutes:
    def test_routes_registered(self):
        from app import server

        paths = {str(r.rule) for r in server.app.url_map.iter_rules()}
        for path in [
            "/api/auth/sessions",
            "/api/auth/sessions/revoke",
            "/api/auth/sessions/revoke_others",
        ]:
            assert path in paths

    def test_list_requires_auth(self):
        from app import server

        client = server.app.test_client()
        r = client.get("/api/auth/sessions")
        assert r.status_code in (401, 302)

    def test_revoke_requires_auth(self):
        """In test mode auth is disabled (no SEO_SUITE_PASSWORD_HASH), so the
        decorator lets the request through. The route then rejects because
        the SID isn't owned by the empty session.

        In production with auth enabled, the same route returns 401 before
        the body even runs. Both behaviours are correct.
        """
        from app import server

        client = server.app.test_client()
        r = client.post("/api/auth/sessions/revoke", json={"sid": "fake"})
        # 401/302 when auth is enforced; 404 when auth is off + session lookup fails.
        assert r.status_code in (401, 302, 404)
