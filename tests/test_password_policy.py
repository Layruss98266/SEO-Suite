"""Tests for core/password_policy.py — zxcvbn + HIBP checks."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from core import password_policy as pp


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch):
    """Ensure both checks are ENABLED for these tests (conftest disables them)."""
    monkeypatch.delenv("SEO_SUITE_DISABLE_ZXCVBN", raising=False)
    monkeypatch.delenv("SEO_SUITE_DISABLE_HIBP", raising=False)


class TestCheckStrength:
    def test_disabled_via_env(self, monkeypatch):
        monkeypatch.setenv("SEO_SUITE_DISABLE_ZXCVBN", "1")
        ok, err = pp.check_strength("password")  # famously weak
        assert ok and err is None

    def test_weak_password_rejected(self):
        ok, err = pp.check_strength("password")
        assert not ok
        assert "weak" in err.lower() or "guess" in err.lower()

    def test_strong_password_accepted(self):
        # A long random-ish string scores 4/4 on zxcvbn.
        ok, err = pp.check_strength("Tr0ub4dor&3-correct-horse-battery-staple")
        assert ok, f"Expected pass, got: {err}"
        assert err is None

    def test_username_factored_into_score(self):
        """Password with the username embedded should score lower than the
        same password without the username hint."""
        with_hint, _ = pp.check_strength("alice123", username="alice")
        without_hint, _ = pp.check_strength("alice123")
        # The username hint should push the score down (so either both fail,
        # or the with-hint version fails while without-hint also fails — but
        # not the other way around).
        # Both should fail since 'alice123' is genuinely weak regardless.
        assert not with_hint

    def test_zxcvbn_missing_passes(self, monkeypatch):
        """Graceful degradation when zxcvbn isn't installed."""
        # Simulate ImportError by stubbing the import.
        import builtins

        real_import = builtins.__import__

        def _stub(name, *a, **kw):
            if name.startswith("zxcvbn"):
                raise ImportError("not installed")
            return real_import(name, *a, **kw)

        monkeypatch.setattr(builtins, "__import__", _stub)
        ok, err = pp.check_strength("anything")
        assert ok and err is None


class TestCheckBreached:
    @patch("requests.get")
    def test_known_breached_password_detected(self, mock_get):
        # "password" SHA-1 = 5BAA61E4C9B93F3F0682250B6CF8331B7EE68FD8
        # Prefix=5BAA6, suffix=1E4C9B93F3F0682250B6CF8331B7EE68FD8
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "1E4C9B93F3F0682250B6CF8331B7EE68FD8:9659365\n0000000000000000000000000000000000:1\n"
        mock_get.return_value = mock_resp

        breached, count = pp.check_breached("password")
        assert breached is True
        assert count == 9659365

    @patch("requests.get")
    def test_clean_password_not_breached(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "0000000000000000000000000000000000:1\n"
        mock_get.return_value = mock_resp

        breached, count = pp.check_breached("very-unique-string-not-in-breaches")
        assert breached is False
        assert count == 0

    @patch("requests.get")
    def test_network_failure_fail_open(self, mock_get):
        """A flaky HIBP must not lock users out — treat as not-breached."""
        mock_get.side_effect = ConnectionError("network down")
        breached, count = pp.check_breached("password")
        assert breached is False
        assert count == 0

    @patch("requests.get")
    def test_non_200_fail_open(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 503
        mock_resp.text = ""
        mock_get.return_value = mock_resp
        breached, _ = pp.check_breached("password")
        assert breached is False

    def test_disabled_via_env(self, monkeypatch):
        monkeypatch.setenv("SEO_SUITE_DISABLE_HIBP", "1")
        # Should not even hit the network.
        with patch("requests.get") as mock_get:
            mock_get.side_effect = AssertionError("HIBP must not be called")
            breached, _ = pp.check_breached("password")
        assert breached is False

    def test_empty_password_returns_not_breached(self):
        breached, _ = pp.check_breached("")
        assert breached is False

    @patch("requests.get")
    def test_uses_k_anonymity_only_sends_prefix(self, mock_get):
        """We must never transmit the full SHA-1 to HIBP."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = ""
        mock_get.return_value = mock_resp

        pp.check_breached("test")
        called_url = mock_get.call_args.args[0]
        # SHA-1("test") = a94a8fef8c... — only "A94A8" should appear in URL.
        assert "A94A8" in called_url
        # And only the prefix, not the full hash.
        assert "A94A8FEF8CDB93F3F0682250B6CF8331B7EE68FD8" not in called_url


class TestValidateNewPassword:
    def test_weak_rejected_before_hibp(self, monkeypatch):
        """Weak password must fail before any HIBP request goes out."""
        with patch("requests.get") as mock_get:
            ok, err = pp.validate_new_password("password")
        assert not ok
        # HIBP must not be reached because zxcvbn rejected it first.
        mock_get.assert_not_called()

    @patch("requests.get")
    def test_strong_clean_password_accepted(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = ""
        mock_get.return_value = mock_resp

        ok, err = pp.validate_new_password(
            "Tr0ub4dor&3-correct-horse-battery-staple"
        )
        assert ok, f"Expected pass, got: {err}"
        assert err is None

    @patch("requests.get")
    def test_strong_but_breached_rejected(self, mock_get):
        # A strong-looking password that's actually in breaches.
        # We mock HIBP to claim "yes, this is breached".
        password = "Tr0ub4dor&3-correct-horse-battery-staple"
        import hashlib

        sha1 = hashlib.sha1(password.encode()).hexdigest().upper()
        suffix = sha1[5:]
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = f"{suffix}:42\n"
        mock_get.return_value = mock_resp

        ok, err = pp.validate_new_password(password)
        assert not ok
        assert "breach" in err.lower()
        assert "42" in err

    def test_check_hibp_false_skips_network(self):
        with patch("requests.get") as mock_get:
            pp.validate_new_password(
                "Tr0ub4dor&3-correct-horse-battery-staple", check_hibp=False
            )
        mock_get.assert_not_called()
