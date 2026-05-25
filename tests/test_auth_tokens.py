"""Tests for the SQLite auth_tokens table + password reset / email verify routes."""

from __future__ import annotations

from unittest.mock import patch

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


# ── Token primitive tests ────────────────────────────────────────────────────
class TestIssueAuthToken:
    def test_returns_url_safe_token(self, db_path):
        token = db.issue_auth_token(db_path, "alice", "password_reset")
        assert isinstance(token, str)
        assert len(token) > 32
        # URL-safe charset.
        assert all(c.isalnum() or c in "-_" for c in token)

    def test_each_call_returns_unique_token(self, db_path):
        tokens = {db.issue_auth_token(db_path, "alice", "password_reset") for _ in range(10)}
        assert len(tokens) == 10

    def test_only_hash_stored(self, db_path):
        token = db.issue_auth_token(db_path, "alice", "password_reset")
        # Raw token must NOT appear anywhere in the DB.
        import sqlite3

        with sqlite3.connect(db_path) as conn:
            rows = conn.execute("SELECT token_hash FROM auth_tokens").fetchall()
        assert all(token not in row[0] for row in rows)
        # Only the SHA-256 hash is stored.
        assert all(len(row[0]) == 64 for row in rows)

    def test_revokes_prior_outstanding_tokens(self, db_path):
        """Issuing a new token of the same kind should consume previous ones."""
        old = db.issue_auth_token(db_path, "alice", "password_reset")
        new = db.issue_auth_token(db_path, "alice", "password_reset")

        # Old token must be unusable.
        assert db.consume_auth_token(db_path, old, "password_reset") is None
        # New token still works.
        assert db.consume_auth_token(db_path, new, "password_reset") == "alice"


class TestConsumeAuthToken:
    def test_valid_token_returns_username(self, db_path):
        token = db.issue_auth_token(db_path, "alice", "password_reset")
        assert db.consume_auth_token(db_path, token, "password_reset") == "alice"

    def test_consumed_token_cannot_be_reused(self, db_path):
        token = db.issue_auth_token(db_path, "alice", "password_reset")
        assert db.consume_auth_token(db_path, token, "password_reset") == "alice"
        # Second use fails.
        assert db.consume_auth_token(db_path, token, "password_reset") is None

    def test_wrong_kind_rejected(self, db_path):
        token = db.issue_auth_token(db_path, "alice", "password_reset")
        # Same token, asked under a different kind — must fail.
        assert db.consume_auth_token(db_path, token, "email_verify") is None
        # Still works under the right kind (until consumed).
        assert db.consume_auth_token(db_path, token, "password_reset") == "alice"

    def test_expired_token_rejected(self, db_path):
        # Issue with 0-second TTL.
        token = db.issue_auth_token(db_path, "alice", "password_reset", ttl_seconds=0)
        # Even with no sleep, expires_at == created_at; the comparison
        # 'expires_at < now' is true on subsequent calls.
        import time as _time

        _time.sleep(0.01)
        assert db.consume_auth_token(db_path, token, "password_reset") is None

    def test_unknown_token_rejected(self, db_path):
        db.issue_auth_token(db_path, "alice", "password_reset")
        assert db.consume_auth_token(db_path, "not-a-real-token", "password_reset") is None

    def test_empty_token_rejected(self, db_path):
        assert db.consume_auth_token(db_path, "", "password_reset") is None


# ── Password reset via DB ─────────────────────────────────────────────────────
class TestResetPasswordHash:
    def test_updates_hash(self, db_path):
        db.save_users(
            db_path,
            {
                "alice": {
                    "password_hash": "old",
                    "is_admin": False,
                    "created_at": "2026-01-01T00:00:00Z",
                }
            },
        )
        assert db.reset_password_hash(db_path, "alice", "new_hash") is True
        loaded = db.load_users(db_path)
        assert loaded["alice"]["password_hash"] == "new_hash"

    def test_returns_false_for_missing_user(self, db_path):
        db._ensure_schema(db_path)
        assert db.reset_password_hash(db_path, "ghost", "h") is False


# ── Email verified flag ──────────────────────────────────────────────────────
class TestEmailVerifiedFlag:
    def test_starts_unverified(self, db_path):
        db.save_users(
            db_path,
            {"alice": {"password_hash": "h", "is_admin": False, "created_at": ""}},
        )
        assert db.get_email_verified(db_path, "alice") is False

    def test_set_then_get(self, db_path):
        db.save_users(
            db_path,
            {"alice": {"password_hash": "h", "is_admin": False, "created_at": ""}},
        )
        assert db.set_email_verified(db_path, "alice", True) is True
        assert db.get_email_verified(db_path, "alice") is True
        assert db.set_email_verified(db_path, "alice", False) is True
        assert db.get_email_verified(db_path, "alice") is False

    def test_returns_false_for_missing_user(self, db_path):
        db._ensure_schema(db_path)
        assert db.get_email_verified(db_path, "ghost") is False


# ── HTTP endpoint integration ────────────────────────────────────────────────
class TestPasswordResetEndpoint:
    def test_routes_registered(self):
        from app import server

        paths = {str(r.rule) for r in server.app.url_map.iter_rules()}
        for path in [
            "/api/auth/request_password_reset",
            "/api/auth/reset_password",
            "/api/auth/send_verification",
            "/api/auth/verify_email",
        ]:
            assert path in paths
            # And under v1 alias
            assert f"/api/v1{path[4:]}" in paths

    def test_request_password_reset_always_returns_200(self):
        """Anti-enumeration: response must be identical for known + unknown users."""
        from app import server

        client = server.app.test_client()
        # Unknown user — always 200.
        r1 = client.post(
            "/api/auth/request_password_reset", json={"username": "nobody@example.com"}
        )
        assert r1.status_code == 200
        body1 = r1.get_json()
        assert body1["ok"] is True

        # Empty username — still 200.
        r2 = client.post("/api/auth/request_password_reset", json={"username": ""})
        assert r2.status_code == 200

    def test_reset_password_requires_token_and_password(self):
        from app import server

        client = server.app.test_client()
        r = client.post("/api/auth/reset_password", json={})
        assert r.status_code == 400

    def test_reset_password_invalid_token(self):
        from app import server

        client = server.app.test_client()
        r = client.post(
            "/api/auth/reset_password",
            json={"token": "garbage", "new_password": "longenoughpw123"},
        )
        assert r.status_code == 400
        assert "invalid" in r.get_json()["error"].lower()


class TestEmailVerifyEndpoint:
    def test_verify_email_requires_token(self):
        from app import server

        client = server.app.test_client()
        r = client.post("/api/auth/verify_email", json={})
        assert r.status_code == 400

    def test_verify_email_invalid_token(self):
        from app import server

        client = server.app.test_client()
        r = client.post("/api/auth/verify_email", json={"token": "fake"})
        assert r.status_code == 400


# ── End-to-end: request a reset token and consume it ─────────────────────────
class TestEndToEnd:
    def test_reset_flow_completes(self, tmp_path, monkeypatch):
        """Issue token, then consume + rotate password."""
        from core import auth

        users_db = tmp_path / "users.db"
        monkeypatch.setattr(auth, "_USERS_DB", users_db)
        monkeypatch.setattr(auth, "_USERS_PATH", tmp_path / "users.json")
        monkeypatch.setattr(auth, "_CONFIG_PATH", tmp_path / "config.json")
        monkeypatch.delenv("SEO_SUITE_PASSWORD_HASH", raising=False)
        monkeypatch.delenv("SEO_SUITE_USERS_BACKEND", raising=False)

        # Create a user.
        ok, _ = auth.create_user("alice@example.com", "originalpw1234")
        assert ok

        # Mint a reset token directly via db.
        token = db.issue_auth_token(users_db, "alice@example.com", "password_reset")
        # Consume + verify it returns the right user.
        consumed = db.consume_auth_token(users_db, token, "password_reset")
        assert consumed == "alice@example.com"

        # Set a new password via reset_password_hash (mimics the route's
        # behaviour after token consumption).
        new_hash = auth._hash_password("brandnewpw1234")
        assert db.reset_password_hash(users_db, "alice@example.com", new_hash) is True

        # Old password no longer works; new one does.
        assert auth.authenticate("alice@example.com", "originalpw1234") is None
        assert auth.authenticate("alice@example.com", "brandnewpw1234") is not None
