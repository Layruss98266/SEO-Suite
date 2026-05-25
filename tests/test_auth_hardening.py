"""Tests for the auth hardening sprint:

* argon2id hashing for new passwords + scrypt backward compatibility
* anti-enumeration dummy-hash run for unknown usernames
* constant-time username comparison against env admin
* /api/auth/change_password endpoint
"""

from __future__ import annotations

import time
from statistics import median

import pytest

from core import auth, db


@pytest.fixture(autouse=True)
def _reset_state():
    """Reset shared module state before/after each test."""
    db._reset_for_tests()
    auth._failed_attempts.clear()
    yield
    db._reset_for_tests()
    auth._failed_attempts.clear()


@pytest.fixture
def isolated_auth(tmp_path, monkeypatch):
    """Point auth at tmp files with no env admin."""
    monkeypatch.setattr(auth, "_USERS_DB", tmp_path / "users.db")
    monkeypatch.setattr(auth, "_USERS_PATH", tmp_path / "users.json")
    monkeypatch.setattr(auth, "_CONFIG_PATH", tmp_path / "config.json")
    monkeypatch.delenv("SEO_SUITE_PASSWORD_HASH", raising=False)
    monkeypatch.delenv("SEO_SUITE_USERNAME", raising=False)
    monkeypatch.delenv("SEO_SUITE_USERS_BACKEND", raising=False)
    return auth


# ── Argon2 + backward compatibility ──────────────────────────────────────────
class TestArgon2:
    def test_new_passwords_use_argon2(self, isolated_auth):
        h = isolated_auth._hash_password("longenoughpw1")
        # argon2-cffi PHC format starts with $argon2.
        assert h.startswith("$argon2"), (
            f"Expected argon2 hash, got {h[:20]!r}. Is argon2-cffi installed?"
        )

    def test_argon2_verifies_correctly(self, isolated_auth):
        h = isolated_auth._hash_password("longenoughpw1")
        assert isolated_auth._verify_password(h, "longenoughpw1")
        assert not isolated_auth._verify_password(h, "wrongpassword")

    def test_legacy_scrypt_hashes_still_verify(self, isolated_auth):
        """Old scrypt hashes from pre-argon2 installs must still authenticate."""
        from werkzeug.security import generate_password_hash

        legacy = generate_password_hash("legacypw1234")
        assert legacy.startswith("scrypt:")
        assert isolated_auth._verify_password(legacy, "legacypw1234")
        assert not isolated_auth._verify_password(legacy, "wrong")

    def test_create_user_stores_argon2(self, isolated_auth):
        ok, _ = isolated_auth.create_user("alice", "longenoughpw1")
        assert ok
        users = isolated_auth._load_users()
        assert users["alice"]["password_hash"].startswith("$argon2")

    def test_corrupt_hash_returns_false_not_raise(self, isolated_auth):
        # Garbled hash must not raise — defensive against DB corruption.
        assert not isolated_auth._verify_password("not-a-valid-hash", "anything")
        assert not isolated_auth._verify_password("", "anything")


# ── Anti-enumeration via dummy hash ──────────────────────────────────────────
class TestAntiEnumeration:
    def test_unknown_user_returns_none_not_distinguishable(self, isolated_auth):
        # Both should return None; the only difference is the audit log reason.
        isolated_auth.create_user("alice", "longenoughpw1")
        assert isolated_auth.authenticate("alice", "wrongpw") is None
        assert isolated_auth.authenticate("ghost", "wrongpw") is None

    def test_timing_similar_for_known_vs_unknown_user(self, isolated_auth):
        """Unknown-user path runs a dummy hash so wall-clock cost matches.

        We use a generous tolerance because argon2 timing is environment-
        dependent. The point is *not* to assert constant-time to the nanosecond
        — it's that the unknown-user path isn't ~1000x faster than the known
        path (which would happen without the dummy hash).
        """
        isolated_auth.create_user("alice", "longenoughpw1")

        def _time_call(username: str) -> float:
            t0 = time.perf_counter()
            isolated_auth.authenticate(username, "wrongpw")
            return time.perf_counter() - t0

        # Warm caches first.
        _time_call("alice")
        _time_call("ghost")

        known = median(_time_call("alice") for _ in range(3))
        unknown = median(_time_call("ghost") for _ in range(3))

        # Known and unknown should be within an order of magnitude of each
        # other. Without the dummy hash, unknown would be ~50-500x faster.
        ratio = max(known, unknown) / min(known, unknown)
        assert ratio < 5.0, (
            f"Timing leak: known={known:.4f}s vs unknown={unknown:.4f}s "
            f"(ratio {ratio:.1f}). Anti-enumeration dummy hash may be missing."
        )

    def test_locked_account_recorded_with_correct_reason(self, isolated_auth):
        isolated_auth.create_user("alice", "longenoughpw1")
        for _ in range(isolated_auth._LOCKOUT_THRESHOLD):
            isolated_auth._record_failed_login("alice")
        assert isolated_auth._is_locked_out("alice")

        # Even the correct password fails while locked.
        result = isolated_auth.authenticate("alice", "longenoughpw1")
        assert result is None

        rows = db.get_login_history(isolated_auth._USERS_DB, username="alice")
        assert any(r["reason"] == "locked_out" for r in rows)


# ── Constant-time username compare against env admin ─────────────────────────
class TestConstantTimeUsernameCompare:
    def test_env_admin_compared_constant_time(self, tmp_path, monkeypatch):
        """hmac.compare_digest is used so we can't leak username via timing.

        Hard to assert directly — instead we verify the env admin path is
        reachable and rejects unknown users without falling into the file
        store comparison loop.
        """
        from werkzeug.security import generate_password_hash

        env_hash = generate_password_hash("envadminpw12")
        monkeypatch.setenv("SEO_SUITE_USERNAME", "envadmin")
        monkeypatch.setenv("SEO_SUITE_PASSWORD_HASH", env_hash)
        monkeypatch.setattr(auth, "_USERS_DB", tmp_path / "users.db")
        monkeypatch.setattr(auth, "_USERS_PATH", tmp_path / "users.json")

        # Correct env admin login works.
        result = auth.authenticate("envadmin", "envadminpw12")
        assert result is not None
        assert result["is_admin"] is True

        # Wrong password for env admin fails.
        assert auth.authenticate("envadmin", "wrong") is None

        # Different-username path doesn't accidentally pass through env admin
        # logic (would happen if `==` short-circuit was loose).
        assert auth.authenticate("notadmin", "envadminpw12") is None


# ── change_password ──────────────────────────────────────────────────────────
class TestChangePassword:
    def test_happy_path(self, isolated_auth):
        isolated_auth.create_user("alice", "originalpw1234")
        ok, err = isolated_auth.change_password("alice", "originalpw1234", "newpassword12")
        assert ok and err is None

        # Old password no longer works.
        assert isolated_auth.authenticate("alice", "originalpw1234") is None
        # New password does.
        assert isolated_auth.authenticate("alice", "newpassword12") is not None

    def test_wrong_current_password_rejected(self, isolated_auth):
        isolated_auth.create_user("alice", "originalpw1234")
        ok, err = isolated_auth.change_password("alice", "WRONG", "newpassword12")
        assert not ok
        assert "incorrect" in err.lower()

    def test_short_new_password_rejected(self, isolated_auth):
        isolated_auth.create_user("alice", "originalpw1234")
        ok, err = isolated_auth.change_password("alice", "originalpw1234", "short")
        assert not ok
        assert "12 characters" in err

    def test_same_as_current_rejected(self, isolated_auth):
        isolated_auth.create_user("alice", "originalpw1234")
        ok, err = isolated_auth.change_password("alice", "originalpw1234", "originalpw1234")
        assert not ok
        assert "differ" in err.lower()

    def test_unknown_user_rejected_with_dummy_hash(self, isolated_auth):
        ok, err = isolated_auth.change_password("ghost", "anything12345", "newpassword12")
        assert not ok
        # Same wording as "wrong current password" — anti-enumeration.
        assert "incorrect" in err.lower()

    def test_env_admin_change_refused(self, tmp_path, monkeypatch):
        from werkzeug.security import generate_password_hash

        monkeypatch.setenv("SEO_SUITE_USERNAME", "envadmin")
        monkeypatch.setenv("SEO_SUITE_PASSWORD_HASH", generate_password_hash("envpw12345"))
        monkeypatch.setattr(auth, "_USERS_DB", tmp_path / "users.db")
        monkeypatch.setattr(auth, "_USERS_PATH", tmp_path / "users.json")

        ok, err = auth.change_password("envadmin", "envpw12345", "newpassword12")
        assert not ok
        assert "environment" in err.lower() or "env" in err.lower()

    def test_clears_lockout_counter(self, isolated_auth):
        isolated_auth.create_user("alice", "originalpw1234")
        # Bump some failures.
        for _ in range(3):
            isolated_auth._record_failed_login("alice")
        assert "alice" in isolated_auth._failed_attempts

        isolated_auth.change_password("alice", "originalpw1234", "newpassword12")
        # After successful change, lockout counter is cleared.
        assert "alice" not in isolated_auth._failed_attempts

    def test_new_password_stored_as_argon2(self, isolated_auth):
        """change_password should also use the preferred algorithm."""
        from werkzeug.security import generate_password_hash

        # Manually seed a legacy scrypt hash to simulate a pre-argon2 user.
        with isolated_auth._users_lock:
            users = isolated_auth._load_users()
            users["legacy"] = {
                "password_hash": generate_password_hash("legacypw12345"),
                "is_admin": False,
                "created_at": "2026-01-01T00:00:00Z",
            }
            isolated_auth._save_users(users)

        ok, _ = isolated_auth.change_password("legacy", "legacypw12345", "newpassword12")
        assert ok

        users = isolated_auth._load_users()
        # After change, hash is now argon2.
        assert users["legacy"]["password_hash"].startswith("$argon2")


# ── HTTP endpoint integration ────────────────────────────────────────────────
class TestChangePasswordEndpoint:
    def test_requires_login(self):
        from app import server

        client = server.app.test_client()
        r = client.post("/api/auth/change_password", json={
            "current_password": "x", "new_password": "y" * 12
        })
        assert r.status_code in (401, 302)

    def test_route_registered_under_v1_alias(self):
        from app import server

        paths = {str(r.rule) for r in server.app.url_map.iter_rules()}
        assert "/api/auth/change_password" in paths
        assert "/api/v1/auth/change_password" in paths
