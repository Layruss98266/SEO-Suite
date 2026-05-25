"""Tests for login-notification + force env-admin rotation (#7, #8)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

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
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(auth, "_USERS_DB", tmp_path / "users.db")
    monkeypatch.setattr(auth, "_USERS_PATH", tmp_path / "users.json")
    monkeypatch.setattr(auth, "_CONFIG_PATH", tmp_path / "config.json")
    monkeypatch.delenv("SEO_SUITE_PASSWORD_HASH", raising=False)
    monkeypatch.delenv("SEO_SUITE_USERNAME", raising=False)
    monkeypatch.delenv("SEO_SUITE_USERS_BACKEND", raising=False)
    monkeypatch.delenv("SEO_SUITE_SKIP_ENV_ADMIN_ROTATION", raising=False)
    return auth, tmp_path


# ── Novelty detection for login notifications ────────────────────────────────
class TestIsNovelLogin:
    def test_first_login_is_novel(self, isolated):
        a, _ = isolated
        # No prior history.
        assert a._is_novel_login("alice@example.com", "1.2.3.4", "UA/1") is True

    def test_repeat_ip_and_ua_not_novel(self, isolated):
        a, _ = isolated
        db.record_login_attempt(
            a._USERS_DB,
            "alice@example.com",
            success=True,
            ip="1.2.3.4",
            user_agent="UA/1",
        )
        assert a._is_novel_login("alice@example.com", "1.2.3.4", "UA/1") is False

    def test_new_ip_is_novel(self, isolated):
        a, _ = isolated
        db.record_login_attempt(
            a._USERS_DB,
            "alice@example.com",
            success=True,
            ip="1.2.3.4",
            user_agent="UA/1",
        )
        assert a._is_novel_login("alice@example.com", "9.9.9.9", "UA/1") is True

    def test_new_user_agent_is_novel(self, isolated):
        a, _ = isolated
        db.record_login_attempt(
            a._USERS_DB,
            "alice@example.com",
            success=True,
            ip="1.2.3.4",
            user_agent="UA/1",
        )
        assert a._is_novel_login("alice@example.com", "1.2.3.4", "UA/2") is True

    def test_failed_attempts_dont_count_as_seen(self, isolated):
        a, _ = isolated
        # A failure from this IP shouldn't mark it as "seen".
        db.record_login_attempt(
            a._USERS_DB,
            "alice@example.com",
            success=False,
            ip="1.2.3.4",
            user_agent="UA/1",
            reason="bad_password",
        )
        assert a._is_novel_login("alice@example.com", "1.2.3.4", "UA/1") is True


# ── End-to-end: successful novel login sends notification ────────────────────
class TestLoginNotificationIntegration:
    def test_notification_sent_on_novel_login(self, isolated):
        a, _ = isolated
        ok, _ = a.create_user("alice@example.com", "originalpw1234")
        assert ok

        with patch.object(a, "_send_login_notification") as mock_send:
            identity = a.authenticate(
                "alice@example.com", "originalpw1234", ip="1.2.3.4", user_agent="UA/1"
            )
        assert identity is not None
        mock_send.assert_called_once()

    def test_notification_not_sent_on_repeat_login(self, isolated):
        a, _ = isolated
        a.create_user("alice@example.com", "originalpw1234")
        # First login establishes the IP+UA as seen.
        a.authenticate(
            "alice@example.com", "originalpw1234", ip="1.2.3.4", user_agent="UA/1"
        )

        with patch.object(a, "_send_login_notification") as mock_send:
            a.authenticate(
                "alice@example.com", "originalpw1234", ip="1.2.3.4", user_agent="UA/1"
            )
        mock_send.assert_not_called()

    def test_notification_skipped_for_non_email_username(self, isolated):
        """The send function bails when the username has no @."""
        a, _ = isolated
        # _send_login_notification is direct here — bypasses authenticate.
        with patch("core.notifier.NotificationService") as mock_svc:
            a._send_login_notification("plainuser", "1.2.3.4", "UA/1")
        mock_svc.assert_not_called()


# ── Force env-admin rotation (#8) ────────────────────────────────────────────
class TestEnvAdminRotation:
    def test_env_admin_login_returns_must_rotate(self, isolated, monkeypatch):
        from werkzeug.security import generate_password_hash

        a, _ = isolated
        monkeypatch.setenv("SEO_SUITE_USERNAME", "envadmin")
        monkeypatch.setenv("SEO_SUITE_PASSWORD_HASH", generate_password_hash("envpw12345"))

        identity = a.authenticate("envadmin", "envpw12345")
        assert identity is not None
        assert identity.get("must_rotate_password") is True

    def test_env_admin_skip_via_env_var(self, isolated, monkeypatch):
        from werkzeug.security import generate_password_hash

        a, _ = isolated
        monkeypatch.setenv("SEO_SUITE_USERNAME", "envadmin")
        monkeypatch.setenv("SEO_SUITE_PASSWORD_HASH", generate_password_hash("envpw12345"))
        monkeypatch.setenv("SEO_SUITE_SKIP_ENV_ADMIN_ROTATION", "1")

        identity = a.authenticate("envadmin", "envpw12345")
        assert identity is not None
        # Flag absent when opt-out is set.
        assert "must_rotate_password" not in identity

    def test_must_rotate_clears_once_file_user_exists(self, isolated, monkeypatch):
        """After the operator creates a real file user with the same name,
        the rotation flag goes away."""
        from werkzeug.security import generate_password_hash

        a, tmp_path = isolated
        monkeypatch.setenv("SEO_SUITE_USERNAME", "envadmin")
        monkeypatch.setenv("SEO_SUITE_PASSWORD_HASH", generate_password_hash("envpw12345"))

        # Initially needs rotation.
        assert a._should_force_env_admin_rotation("envadmin") is True

        # Operator creates a real file user with the same username.
        # create_user normally rejects the env admin's username — bypass for
        # this test by writing directly.
        with a._users_lock:
            users = a._load_users()
            users["envadmin"] = {
                "password_hash": a._hash_password("newproperpw1234"),
                "is_admin": True,
                "created_at": "2026-01-01T00:00:00Z",
            }
            a._save_users(users)

        assert a._should_force_env_admin_rotation("envadmin") is False

    def test_non_env_user_doesnt_need_rotation(self, isolated):
        a, _ = isolated
        # No env admin configured at all.
        assert a._should_force_env_admin_rotation("anybody") is False
