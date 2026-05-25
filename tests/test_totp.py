"""Tests for TOTP 2FA: enrolment, activation, login challenge, backup codes."""

from __future__ import annotations

import pyotp
import pytest

from core import auth, db, totp


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
    monkeypatch.delenv("SEO_SUITE_USERS_BACKEND", raising=False)
    return auth, tmp_path / "users.db"


# ── Enrolment + activation ───────────────────────────────────────────────────
class TestEnroll:
    def test_returns_base32_secret_and_uri(self, isolated):
        _, db_path = isolated
        secret, uri = totp.enroll(db_path, "alice")
        # base32 chars only
        assert all(c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567" for c in secret)
        assert uri.startswith("otpauth://totp/")
        assert "issuer=SEO%20Suite" in uri
        assert "alice" in uri

    def test_enrol_starts_disabled(self, isolated):
        _, db_path = isolated
        totp.enroll(db_path, "alice")
        assert not totp.is_enabled(db_path, "alice")

    def test_re_enrol_regenerates_secret(self, isolated):
        _, db_path = isolated
        s1, _ = totp.enroll(db_path, "alice")
        s2, _ = totp.enroll(db_path, "alice")
        assert s1 != s2


class TestActivate:
    def test_valid_code_enables_and_returns_backup_codes(self, isolated):
        _, db_path = isolated
        secret, _ = totp.enroll(db_path, "alice")
        valid_code = pyotp.TOTP(secret).now()

        ok, codes = totp.activate(db_path, "alice", valid_code)
        assert ok is True
        assert codes is not None
        assert len(codes) == 10
        # Codes are unique.
        assert len(set(codes)) == 10
        assert totp.is_enabled(db_path, "alice")

    def test_invalid_code_does_not_enable(self, isolated):
        _, db_path = isolated
        totp.enroll(db_path, "alice")
        ok, codes = totp.activate(db_path, "alice", "000000")
        assert ok is False
        assert codes is None
        assert not totp.is_enabled(db_path, "alice")

    def test_activate_for_unknown_user_fails(self, isolated):
        _, db_path = isolated
        ok, _ = totp.activate(db_path, "ghost", "123456")
        assert ok is False

    def test_double_activate_rejected(self, isolated):
        _, db_path = isolated
        secret, _ = totp.enroll(db_path, "alice")
        valid_code = pyotp.TOTP(secret).now()
        totp.activate(db_path, "alice", valid_code)
        # Second activate must fail — already enabled.
        ok, _ = totp.activate(db_path, "alice", valid_code)
        assert ok is False


# ── Verification ─────────────────────────────────────────────────────────────
class TestVerifyCode:
    def test_current_code_verifies(self, isolated):
        _, db_path = isolated
        secret, _ = totp.enroll(db_path, "alice")
        totp.activate(db_path, "alice", pyotp.TOTP(secret).now())

        assert totp.verify_code(db_path, "alice", pyotp.TOTP(secret).now())

    def test_wrong_code_rejected(self, isolated):
        _, db_path = isolated
        secret, _ = totp.enroll(db_path, "alice")
        totp.activate(db_path, "alice", pyotp.TOTP(secret).now())
        assert not totp.verify_code(db_path, "alice", "000000")

    def test_verify_for_disabled_user_fails(self, isolated):
        _, db_path = isolated
        secret, _ = totp.enroll(db_path, "alice")
        # Don't activate. Verification should fail even with a valid code.
        valid_code = pyotp.TOTP(secret).now()
        assert not totp.verify_code(db_path, "alice", valid_code)

    def test_verify_for_unknown_user_fails(self, isolated):
        _, db_path = isolated
        assert not totp.verify_code(db_path, "ghost", "123456")

    def test_empty_code_rejected(self, isolated):
        _, db_path = isolated
        secret, _ = totp.enroll(db_path, "alice")
        totp.activate(db_path, "alice", pyotp.TOTP(secret).now())
        assert not totp.verify_code(db_path, "alice", "")


# ── Backup codes ─────────────────────────────────────────────────────────────
class TestBackupCodes:
    def test_backup_code_consumes(self, isolated):
        _, db_path = isolated
        secret, _ = totp.enroll(db_path, "alice")
        _, codes = totp.activate(db_path, "alice", pyotp.TOTP(secret).now())
        assert totp.remaining_backup_codes(db_path, "alice") == 10

        # Use one.
        assert totp.consume_backup_code(db_path, "alice", codes[0]) is True
        assert totp.remaining_backup_codes(db_path, "alice") == 9
        # Same code can't be reused.
        assert totp.consume_backup_code(db_path, "alice", codes[0]) is False

    def test_unknown_backup_code_rejected(self, isolated):
        _, db_path = isolated
        secret, _ = totp.enroll(db_path, "alice")
        totp.activate(db_path, "alice", pyotp.TOTP(secret).now())
        assert not totp.consume_backup_code(db_path, "alice", "NOTACODE12")

    def test_backup_codes_only_stored_hashed(self, isolated):
        _, db_path = isolated
        secret, _ = totp.enroll(db_path, "alice")
        _, codes = totp.activate(db_path, "alice", pyotp.TOTP(secret).now())

        # Read the raw row — none of the plaintext codes should appear.
        row = totp.get_row(db_path, "alice")
        assert row is not None
        stored_blob = row["backup_codes"]
        for c in codes:
            assert c not in stored_blob


# ── Disable ──────────────────────────────────────────────────────────────────
class TestDisable:
    def test_disable_removes_row(self, isolated):
        _, db_path = isolated
        secret, _ = totp.enroll(db_path, "alice")
        totp.activate(db_path, "alice", pyotp.TOTP(secret).now())
        assert totp.disable(db_path, "alice") is True
        assert not totp.is_enabled(db_path, "alice")

    def test_disable_unknown_user_returns_false(self, isolated):
        _, db_path = isolated
        assert totp.disable(db_path, "ghost") is False


# ── Auth integration ─────────────────────────────────────────────────────────
class TestAuthFlowWithTOTP:
    def test_authenticate_returns_totp_required(self, isolated):
        a, db_path = isolated
        a.create_user("alice", "originalpw1234")
        secret, _ = totp.enroll(db_path, "alice")
        totp.activate(db_path, "alice", pyotp.TOTP(secret).now())

        identity = a.authenticate("alice", "originalpw1234")
        assert identity is not None
        assert identity.get("totp_required") is True

    def test_authenticate_no_totp_flag_when_disabled(self, isolated):
        a, _ = isolated
        a.create_user("alice", "originalpw1234")
        identity = a.authenticate("alice", "originalpw1234")
        assert identity is not None
        assert "totp_required" not in identity


# ── HTTP endpoint smoke ──────────────────────────────────────────────────────
class TestRoutesRegistered:
    def test_all_totp_routes_exist(self):
        from app import server

        paths = {str(r.rule) for r in server.app.url_map.iter_rules()}
        for path in [
            "/login/totp",
            "/api/auth/totp/status",
            "/api/auth/totp/enroll",
            "/api/auth/totp/activate",
            "/api/auth/totp/disable",
        ]:
            assert path in paths
        # v1 aliases (except for /login/totp which is form-based, not API).
        for path in [
            "/api/v1/auth/totp/status",
            "/api/v1/auth/totp/enroll",
            "/api/v1/auth/totp/activate",
            "/api/v1/auth/totp/disable",
        ]:
            assert path in paths

    def test_totp_challenge_redirects_without_pending_session(self):
        from app import server

        client = server.app.test_client()
        r = client.get("/login/totp")
        # No pending half-session → redirect to /login.
        assert r.status_code == 302
        assert "/login" in r.headers["Location"]
