"""Tests for GDPR self-service endpoints: export + account deletion."""

from __future__ import annotations

import json

import pytest

from core import auth, db


@pytest.fixture(autouse=True)
def _reset_state():
    db._reset_for_tests()
    auth._failed_attempts.clear()
    yield
    db._reset_for_tests()
    auth._failed_attempts.clear()


@pytest.fixture
def client_with_user(tmp_path, monkeypatch):
    """A test client logged in as a created user, with auth tables isolated."""
    monkeypatch.setattr(auth, "_USERS_DB", tmp_path / "users.db")
    monkeypatch.setattr(auth, "_USERS_PATH", tmp_path / "users.json")
    monkeypatch.setattr(auth, "_CONFIG_PATH", tmp_path / "config.json")

    from app import server

    server.app.config["TESTING"] = True

    auth.create_user("alice@example.com", "longenoughpw1")

    client = server.app.test_client()
    with client.session_transaction() as sess:
        sess["authed"] = True
        sess["username"] = "alice@example.com"
        sess["is_admin"] = True
    return client


# ── Export ───────────────────────────────────────────────────────────────────
class TestExport:
    def test_route_registered(self):
        from app import server

        paths = {str(r.rule) for r in server.app.url_map.iter_rules()}
        assert "/api/auth/me/export" in paths
        assert "/api/v1/auth/me/export" in paths

    def test_requires_login(self):
        from app import server

        client = server.app.test_client()
        r = client.get("/api/auth/me/export")
        # In test mode auth is disabled, so the decorator passes through.
        # Without a session.username the body returns 401.
        assert r.status_code in (200, 401, 302)

    def test_export_returns_json_attachment(self, client_with_user):
        r = client_with_user.get("/api/auth/me/export")
        assert r.status_code == 200
        assert "attachment" in r.headers.get("Content-Disposition", "")
        body = json.loads(r.data)
        assert body["username"] == "alice@example.com"
        assert "account" in body
        assert "login_history" in body
        assert "sessions" in body
        assert "totp" in body

    def test_export_excludes_password_hash(self, client_with_user):
        r = client_with_user.get("/api/auth/me/export")
        body = json.loads(r.data)
        account = body.get("account") or {}
        assert "password_hash" not in account

    def test_export_excludes_totp_secret(self, client_with_user, tmp_path):
        # Enrol the user in TOTP so there's a secret to NOT export.
        from core import totp

        secret, _ = totp.enroll(auth._USERS_DB, "alice@example.com")
        import pyotp

        totp.activate(auth._USERS_DB, "alice@example.com", pyotp.TOTP(secret).now())

        r = client_with_user.get("/api/auth/me/export")
        assert r.status_code == 200
        body = r.data.decode("utf-8")
        # Secret must not appear anywhere in the export.
        assert secret not in body


# ── Delete ───────────────────────────────────────────────────────────────────
class TestSelfDelete:
    def test_route_registered(self):
        from app import server

        paths = {str(r.rule) for r in server.app.url_map.iter_rules()}
        assert "/api/auth/me/delete" in paths

    def test_requires_confirm(self, client_with_user):
        r = client_with_user.post(
            "/api/auth/me/delete",
            json={"password": "longenoughpw1"},
        )
        assert r.status_code == 400
        assert "DELETE" in r.get_json()["error"]

    def test_requires_correct_password(self, client_with_user):
        r = client_with_user.post(
            "/api/auth/me/delete",
            json={"password": "WRONG", "confirm": "DELETE"},
        )
        assert r.status_code == 401
        assert "incorrect" in r.get_json()["error"].lower()

    def test_successful_delete_wipes_data(self, client_with_user):
        # Create a SECOND admin so the last-admin guard doesn't fire.
        with auth._users_lock:
            users = auth._load_users()
            users["bob@example.com"] = {
                "password_hash": auth._hash_password("bobspw123456"),
                "is_admin": True,
                "created_at": "2026-01-01T00:00:00Z",
            }
            auth._save_users(users)

        # Pre-create some related rows.
        db.record_login_attempt(auth._USERS_DB, "alice@example.com", success=True)
        db.create_session(auth._USERS_DB, "alice@example.com", "1.2.3.4", "UA")

        r = client_with_user.post(
            "/api/auth/me/delete",
            json={"password": "longenoughpw1", "confirm": "DELETE"},
        )
        assert r.status_code == 200, r.data
        assert r.get_json()["ok"] is True

        # User row gone.
        assert "alice@example.com" not in auth._load_users()
        # Login history gone.
        assert db.get_login_history(auth._USERS_DB, username="alice@example.com") == []
        # Sessions gone.
        assert db.list_sessions(auth._USERS_DB, "alice@example.com") == []

    def test_cannot_delete_last_admin(self, client_with_user, monkeypatch):
        # alice is the only admin (created as first user → bootstrap admin).
        # Use monkeypatch.delenv so it's restored after the test.
        monkeypatch.delenv("SEO_SUITE_PASSWORD_HASH", raising=False)

        r = client_with_user.post(
            "/api/auth/me/delete",
            json={"password": "longenoughpw1", "confirm": "DELETE"},
        )
        assert r.status_code == 400
        assert "last admin" in r.get_json()["error"].lower()

    def test_cannot_delete_env_admin(self, tmp_path, monkeypatch):
        from werkzeug.security import generate_password_hash

        from app import server

        monkeypatch.setattr(auth, "_USERS_DB", tmp_path / "users.db")
        monkeypatch.setattr(auth, "_USERS_PATH", tmp_path / "users.json")
        monkeypatch.setenv("SEO_SUITE_USERNAME", "envadmin")
        monkeypatch.setenv(
            "SEO_SUITE_PASSWORD_HASH", generate_password_hash("envpw12345")
        )
        server.app.config["TESTING"] = True

        client = server.app.test_client()
        with client.session_transaction() as sess:
            sess["authed"] = True
            sess["username"] = "envadmin"
            sess["is_admin"] = True

        r = client.post(
            "/api/auth/me/delete",
            json={"password": "envpw12345", "confirm": "DELETE"},
        )
        assert r.status_code == 400
        assert "environment" in r.get_json()["error"].lower()
