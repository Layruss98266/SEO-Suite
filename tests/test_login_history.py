"""Tests for the login_attempts table and history routes."""

from __future__ import annotations

import pytest

from core import db


@pytest.fixture(autouse=True)
def _reset_db_state():
    """Reset SQLite path cache + auth's in-memory lockout dict before/after each test.

    The auth module tracks failed-attempt counters in a process-local dict
    (`_failed_attempts`). Without clearing it between tests, the
    ``test_locked_out_attempt_is_recorded`` case below leaks lockouts into
    later tests in this file and the wider suite (e.g. ``test_users.py``).
    """
    from core import auth as _auth

    db._reset_for_tests()
    _auth._failed_attempts.clear()
    yield
    db._reset_for_tests()
    _auth._failed_attempts.clear()


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "test.db"


class TestRecordLoginAttempt:
    def test_writes_success_row(self, db_path):
        db.record_login_attempt(
            db_path, "alice", success=True, ip="1.2.3.4", user_agent="UA/1", reason="ok"
        )
        rows = db.get_login_history(db_path, username="alice")
        assert len(rows) == 1
        assert rows[0]["username"] == "alice"
        assert rows[0]["success"] is True
        assert rows[0]["ip"] == "1.2.3.4"
        assert rows[0]["user_agent"] == "UA/1"
        assert rows[0]["reason"] == "ok"

    def test_writes_failure_row(self, db_path):
        db.record_login_attempt(
            db_path, "alice", success=False, ip="9.9.9.9", reason="bad_password"
        )
        rows = db.get_login_history(db_path, username="alice")
        assert rows[0]["success"] is False
        assert rows[0]["reason"] == "bad_password"

    def test_caps_long_user_agent(self, db_path):
        long_ua = "X" * 5000
        db.record_login_attempt(db_path, "alice", success=True, user_agent=long_ua)
        rows = db.get_login_history(db_path, username="alice")
        assert len(rows[0]["user_agent"]) == 512

    def test_handles_null_ip_and_ua(self, db_path):
        db.record_login_attempt(db_path, "alice", success=True)
        rows = db.get_login_history(db_path, username="alice")
        assert rows[0]["ip"] is None
        assert rows[0]["user_agent"] is None


class TestGetLoginHistory:
    def test_orders_newest_first(self, db_path):
        for i in range(5):
            db.record_login_attempt(db_path, "alice", success=True, reason=f"r{i}")
        rows = db.get_login_history(db_path, username="alice")
        # First (newest) row should have the highest-numbered reason.
        assert rows[0]["reason"] == "r4"
        assert rows[-1]["reason"] == "r0"

    def test_filters_by_username(self, db_path):
        db.record_login_attempt(db_path, "alice", success=True)
        db.record_login_attempt(db_path, "bob", success=True)
        rows = db.get_login_history(db_path, username="alice")
        assert all(r["username"] == "alice" for r in rows)
        assert len(rows) == 1

    def test_filters_by_success(self, db_path):
        db.record_login_attempt(db_path, "alice", success=True)
        db.record_login_attempt(db_path, "alice", success=False)
        db.record_login_attempt(db_path, "alice", success=False)
        ok = db.get_login_history(db_path, success=True)
        fails = db.get_login_history(db_path, success=False)
        assert len(ok) == 1
        assert len(fails) == 2

    def test_respects_limit(self, db_path):
        for _ in range(10):
            db.record_login_attempt(db_path, "alice", success=True)
        rows = db.get_login_history(db_path, limit=3)
        assert len(rows) == 3

    def test_limit_capped_at_max(self, db_path):
        # _LOGIN_HISTORY_MAX_ROWS is 500; passing 99999 should clamp to 500.
        for _ in range(5):
            db.record_login_attempt(db_path, "alice", success=True)
        rows = db.get_login_history(db_path, limit=99999)
        assert len(rows) <= 500


class TestCountRecentFailures:
    def test_counts_failures_in_window(self, db_path):
        for _ in range(3):
            db.record_login_attempt(db_path, "alice", success=False)
        n = db.count_recent_failures(db_path, "alice", window_seconds=3600)
        assert n == 3

    def test_excludes_successes(self, db_path):
        db.record_login_attempt(db_path, "alice", success=True)
        db.record_login_attempt(db_path, "alice", success=False)
        assert db.count_recent_failures(db_path, "alice") == 1


class TestUpdateLastLogin:
    def test_sets_fields(self, db_path):
        db.save_users(
            db_path,
            {
                "alice": {
                    "password_hash": "h",
                    "is_admin": False,
                    "created_at": "2026-01-01T00:00:00Z",
                }
            },
        )
        db.update_last_login(db_path, "alice", "2026-05-25T10:00:00Z", "1.2.3.4")
        user = db.get_user(db_path, "alice")
        assert user["last_login_at"] == "2026-05-25T10:00:00Z"
        assert user["last_login_ip"] == "1.2.3.4"

    def test_get_user_returns_none_for_missing(self, db_path):
        db._ensure_schema(db_path)
        assert db.get_user(db_path, "ghost") is None


class TestAuthIntegration:
    """End-to-end: authenticate() records into login_attempts."""

    def test_failed_attempt_recorded(self, tmp_path, monkeypatch):
        from core import auth

        users_db = tmp_path / "users.db"
        monkeypatch.setattr(auth, "_USERS_DB", users_db)
        monkeypatch.setattr(auth, "_USERS_PATH", tmp_path / "users.json")
        monkeypatch.setattr(auth, "_CONFIG_PATH", tmp_path / "config.json")
        monkeypatch.delenv("SEO_SUITE_PASSWORD_HASH", raising=False)
        monkeypatch.delenv("SEO_SUITE_USERS_BACKEND", raising=False)
        db._reset_for_tests()

        # Create a user so authenticate doesn't short-circuit on "unknown user".
        auth.create_user("alice", "longenoughpw1")
        # Attempt with wrong password.
        result = auth.authenticate("alice", "wrong", ip="1.2.3.4", user_agent="UA/Test")
        assert result is None

        rows = db.get_login_history(users_db, username="alice")
        # Should include both the create (auto-records on first successful auth
        # if any happens internally) and the failed attempt. At minimum, a
        # failure row exists.
        failures = [r for r in rows if not r["success"]]
        assert any(f["reason"] == "bad_password" for f in failures)
        assert any(f["ip"] == "1.2.3.4" for f in failures)

    def test_successful_attempt_updates_last_login(self, tmp_path, monkeypatch):
        from core import auth

        users_db = tmp_path / "users.db"
        monkeypatch.setattr(auth, "_USERS_DB", users_db)
        monkeypatch.setattr(auth, "_USERS_PATH", tmp_path / "users.json")
        monkeypatch.setattr(auth, "_CONFIG_PATH", tmp_path / "config.json")
        monkeypatch.delenv("SEO_SUITE_PASSWORD_HASH", raising=False)
        monkeypatch.delenv("SEO_SUITE_USERS_BACKEND", raising=False)
        db._reset_for_tests()

        auth.create_user("alice", "longenoughpw1")
        identity = auth.authenticate(
            "alice", "longenoughpw1", ip="5.5.5.5", user_agent="UA/Test"
        )
        assert identity is not None
        assert identity["username"] == "alice"

        user = db.get_user(users_db, "alice")
        assert user["last_login_at"] is not None
        assert user["last_login_ip"] == "5.5.5.5"

    def test_locked_out_attempt_is_recorded(self, tmp_path, monkeypatch):
        from core import auth

        users_db = tmp_path / "users.db"
        monkeypatch.setattr(auth, "_USERS_DB", users_db)
        monkeypatch.setattr(auth, "_USERS_PATH", tmp_path / "users.json")
        monkeypatch.setattr(auth, "_CONFIG_PATH", tmp_path / "config.json")
        monkeypatch.delenv("SEO_SUITE_PASSWORD_HASH", raising=False)
        monkeypatch.delenv("SEO_SUITE_USERS_BACKEND", raising=False)
        db._reset_for_tests()

        # Force the lockout state.
        for _ in range(auth._LOCKOUT_THRESHOLD):
            auth._record_failed_login("alice")
        assert auth._is_locked_out("alice")

        result = auth.authenticate("alice", "anything", ip="9.9.9.9")
        assert result is None

        rows = db.get_login_history(users_db, username="alice")
        lockout_rows = [r for r in rows if r["reason"] == "locked_out"]
        assert len(lockout_rows) >= 1
