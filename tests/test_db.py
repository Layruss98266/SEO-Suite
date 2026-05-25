"""Tests for core/db.py — SQLite user store + JSON migration."""

from __future__ import annotations

import json
import sqlite3

import pytest

from core import db


@pytest.fixture(autouse=True)
def _isolate_db_state():
    """Reset the per-path init cache before and after each test."""
    db._reset_for_tests()
    yield
    db._reset_for_tests()


def _make_db(tmp_path):
    return tmp_path / "test.db"


def _make_json(tmp_path, payload: dict):
    p = tmp_path / "users.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    return p


class TestSchema:
    def test_creates_users_table(self, tmp_path):
        dbp = _make_db(tmp_path)
        db._ensure_schema(dbp)
        with sqlite3.connect(dbp) as conn:
            tables = {r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()}
        assert "users" in tables
        assert "schema_version" in tables

    def test_schema_idempotent(self, tmp_path):
        dbp = _make_db(tmp_path)
        db._ensure_schema(dbp)
        db._ensure_schema(dbp)  # second call must not error
        db._reset_for_tests()
        db._ensure_schema(dbp)  # after cache reset, must still work


class TestSaveAndLoad:
    def test_round_trip(self, tmp_path):
        dbp = _make_db(tmp_path)
        users = {
            "alice": {
                "password_hash": "hash1",
                "is_admin": True,
                "created_at": "2026-01-01T00:00:00Z",
            },
            "bob": {
                "password_hash": "hash2",
                "is_admin": False,
                "created_at": "2026-01-02T00:00:00Z",
            },
        }
        db.save_users(dbp, users)
        loaded = db.load_users(dbp)
        assert loaded == users

    def test_load_empty_returns_empty_dict(self, tmp_path):
        dbp = _make_db(tmp_path)
        assert db.load_users(dbp) == {}

    def test_save_replaces_existing(self, tmp_path):
        dbp = _make_db(tmp_path)
        db.save_users(dbp, {"alice": {"password_hash": "h", "is_admin": False, "created_at": ""}})
        db.save_users(dbp, {"bob": {"password_hash": "h2", "is_admin": False, "created_at": ""}})
        loaded = db.load_users(dbp)
        assert "alice" not in loaded
        assert "bob" in loaded

    def test_save_atomic_on_failure(self, tmp_path, monkeypatch):
        """If a mid-insert exception fires, the DELETE must roll back."""
        dbp = _make_db(tmp_path)
        db.save_users(dbp, {"alice": {"password_hash": "h", "is_admin": True, "created_at": ""}})

        # Simulate a crash by passing an unserialisable value through.
        bad = {"bob": {"password_hash": object(), "is_admin": False, "created_at": ""}}
        with pytest.raises(Exception):
            db.save_users(dbp, bad)
        # The original row should still be there (transaction rolled back).
        loaded = db.load_users(dbp)
        assert "alice" in loaded


class TestMigration:
    def test_imports_users_json_on_first_load(self, tmp_path):
        dbp = _make_db(tmp_path)
        json_path = _make_json(
            tmp_path,
            {
                "alice": {
                    "password_hash": "hash1",
                    "is_admin": True,
                    "created_at": "2026-01-01T00:00:00Z",
                }
            },
        )
        loaded = db.load_users(dbp, json_path=json_path)
        assert "alice" in loaded
        # JSON file should be renamed after successful migration.
        assert not json_path.exists()
        assert json_path.with_suffix(".json.migrated").exists()

    def test_skips_migration_when_table_populated(self, tmp_path):
        dbp = _make_db(tmp_path)
        # Pre-populate SQLite.
        db.save_users(
            dbp,
            {"existing": {"password_hash": "h", "is_admin": False, "created_at": ""}},
        )
        # Now write a users.json — it should NOT be imported (table non-empty).
        json_path = _make_json(
            tmp_path,
            {"newcomer": {"password_hash": "h2", "is_admin": True, "created_at": ""}},
        )
        loaded = db.load_users(dbp, json_path=json_path)
        assert "existing" in loaded
        assert "newcomer" not in loaded
        # JSON file is untouched (not renamed).
        assert json_path.exists()

    def test_handles_invalid_json_gracefully(self, tmp_path):
        dbp = _make_db(tmp_path)
        json_path = tmp_path / "users.json"
        json_path.write_text("{not valid json", encoding="utf-8")
        # Should not raise — load_users returns {} and leaves the file alone.
        loaded = db.load_users(dbp, json_path=json_path)
        assert loaded == {}
        assert json_path.exists()  # unchanged

    def test_no_json_no_migration(self, tmp_path):
        dbp = _make_db(tmp_path)
        json_path = tmp_path / "users.json"  # never created
        loaded = db.load_users(dbp, json_path=json_path)
        assert loaded == {}

    def test_skips_entries_without_password_hash(self, tmp_path):
        dbp = _make_db(tmp_path)
        json_path = _make_json(
            tmp_path,
            {
                "good": {"password_hash": "h", "is_admin": False, "created_at": ""},
                "broken": {"is_admin": True},  # missing password_hash
            },
        )
        loaded = db.load_users(dbp, json_path=json_path)
        assert "good" in loaded
        assert "broken" not in loaded
