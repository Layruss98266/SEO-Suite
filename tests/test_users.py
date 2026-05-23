"""Tests for the multi-user store in core.auth."""

import importlib

import pytest

import core.auth as auth


@pytest.fixture
def store(tmp_path, monkeypatch):
    """Isolate the user store + config to tmp files, no env admin."""
    users = tmp_path / "users.json"
    cfg   = tmp_path / "config.json"
    monkeypatch.setattr(auth, "_USERS_PATH", users)
    monkeypatch.setattr(auth, "_CONFIG_PATH", cfg)
    monkeypatch.delenv("SEO_SUITE_PASSWORD_HASH", raising=False)
    monkeypatch.delenv("SEO_SUITE_USERNAME", raising=False)
    return auth, users, cfg


class TestCreateUser:
    def test_first_user_becomes_admin(self, store):
        a, _, _ = store
        ok, err = a.create_user("alice", "longenoughpw1")
        assert ok and err is None
        assert a.list_users()[0]["is_admin"] is True

    def test_second_user_is_regular(self, store):
        a, _, _ = store
        a.create_user("alice", "longenoughpw1")
        a.create_user("bob", "longenoughpw2")
        bob = next(u for u in a.list_users() if u["username"] == "bob")
        assert bob["is_admin"] is False

    def test_short_password_rejected(self, store):
        a, _, _ = store
        ok, err = a.create_user("alice", "short")
        assert not ok and "12" in err

    def test_bad_username_rejected(self, store):
        a, _, _ = store
        ok, err = a.create_user("a b!", "longenoughpw1")
        assert not ok

    def test_duplicate_rejected(self, store):
        a, _, _ = store
        a.create_user("alice", "longenoughpw1")
        ok, err = a.create_user("alice", "anotherlongpw1")
        assert not ok and "exists" in err.lower()

    def test_password_not_stored_plaintext(self, store):
        a, users, _ = store
        a.create_user("alice", "longenoughpw1")
        assert "longenoughpw1" not in users.read_text()


class TestAuthenticate:
    def test_correct_password(self, store):
        a, _, _ = store
        a.create_user("alice", "longenoughpw1")
        res = a.authenticate("alice", "longenoughpw1")
        assert res and res["username"] == "alice" and res["is_admin"] is True

    def test_wrong_password(self, store):
        a, _, _ = store
        a.create_user("alice", "longenoughpw1")
        assert a.authenticate("alice", "nope") is None

    def test_unknown_user(self, store):
        a, _, _ = store
        assert a.authenticate("ghost", "whatever12345") is None


class TestDeleteUser:
    def test_delete_regular_user(self, store):
        a, _, _ = store
        a.create_user("alice", "longenoughpw1")  # admin
        a.create_user("bob", "longenoughpw2")
        ok, err = a.delete_user("bob")
        assert ok and err is None
        assert all(u["username"] != "bob" for u in a.list_users())

    def test_cannot_delete_last_admin(self, store):
        a, _, _ = store
        a.create_user("alice", "longenoughpw1")  # the only admin
        ok, err = a.delete_user("alice")
        assert not ok and "last admin" in err.lower()


class TestEnvAdminBootstrap:
    def test_env_admin_is_superadmin_and_first_signup_not_forced_admin(self, store, monkeypatch):
        a, _, _ = store
        monkeypatch.setenv("SEO_SUITE_PASSWORD_HASH", "x")  # env admin present
        monkeypatch.setenv("SEO_SUITE_USERNAME", "root")
        ok, _ = a.create_user("alice", "longenoughpw1")
        assert ok
        alice = next(u for u in a.list_users() if u["username"] == "alice")
        assert alice["is_admin"] is False           # not forced admin (env admin exists)
        assert any(u["username"] == "root" and u["source"] == "env" for u in a.list_users())

    def test_cannot_create_user_matching_env_admin(self, store, monkeypatch):
        a, _, _ = store
        monkeypatch.setenv("SEO_SUITE_PASSWORD_HASH", "x")
        monkeypatch.setenv("SEO_SUITE_USERNAME", "root")
        ok, err = a.create_user("root", "longenoughpw1")
        assert not ok and "reserved" in err.lower()


class TestSignupToggle:
    def test_default_allowed(self, store):
        a, _, _ = store
        assert a.signup_allowed() is True

    def test_disabled_via_config(self, store):
        a, _, cfg = store
        cfg.write_text('{"allow_signup": false}')
        assert a.signup_allowed() is False


class TestAuthEnabled:
    def test_off_when_no_admin_no_users(self, store):
        a, _, _ = store
        assert a.auth_enabled() is False

    def test_on_once_a_user_exists(self, store):
        a, _, _ = store
        a.create_user("alice", "longenoughpw1")
        assert a.auth_enabled() is True
