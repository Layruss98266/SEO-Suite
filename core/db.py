"""
SQLite-backed persistence for state that needs atomic writes and indexed reads.

Currently backs:

* **Users** — username, password hash, admin flag, created_at

Why SQLite (and not just JSON):

* **Atomic writes** — sqlite3 commits or rolls back. ``json.dump`` can leave
  a torn file behind if the process crashes mid-write.
* **Concurrent reads** — sqlite3 supports many concurrent readers via WAL.
  JSON has to be re-read top-to-bottom under a lock every time.
* **Indexed lookups** — ``SELECT ... WHERE username = ?`` is O(log n).
* **Schema** — types are enforced. ``users.json`` could silently grow
  malformed fields and the bug would not surface until login time.

Migration is opportunistic: the first call to :func:`load_users` reads
``data/users.json`` if the SQLite table is empty, copies the rows over, and
backs up the JSON as ``users.json.migrated`` so it isn't re-imported on the
next restart. The JSON path is still respected as a fallback for environments
where sqlite3 is unavailable (in practice, never — it ships with Python).

The single-process app (gunicorn ``--workers 1``) means we don't need fancy
connection pooling. We open a connection per call, use a short busy-timeout,
and rely on WAL for read concurrency.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

logger = logging.getLogger(__name__)

# Bumped when the schema changes — guides automatic ALTER TABLE migrations.
_SCHEMA_VERSION = 1

_init_lock = threading.Lock()
_initialised: dict[Path, bool] = {}


# ── Connection management ────────────────────────────────────────────────────

@contextmanager
def _connect(db_path: Path) -> Iterator[sqlite3.Connection]:
    """Yield a sqlite3 connection with sane defaults.

    * ``isolation_level=None`` — autocommit mode; we use explicit BEGIN/COMMIT
      where we need transactions, which is clearer than implicit ones.
    * ``timeout=5.0`` — wait up to 5s if another writer holds the lock.
    * ``check_same_thread=False`` — Flask threads share the app instance.
    * WAL journal mode for read concurrency.
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(
        db_path,
        timeout=5.0,
        isolation_level=None,
        check_same_thread=False,
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
    finally:
        conn.close()


def _ensure_schema(db_path: Path) -> None:
    """Create tables on first use. Idempotent + thread-safe.

    Cached per-path so the schema check only runs once per process per
    database file.
    """
    if _initialised.get(db_path):
        return
    with _init_lock:
        if _initialised.get(db_path):  # double-check under lock
            return
        with _connect(db_path) as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS schema_version (
                    version INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS users (
                    username      TEXT PRIMARY KEY,
                    password_hash TEXT NOT NULL,
                    is_admin      INTEGER NOT NULL DEFAULT 0,
                    created_at    TEXT NOT NULL
                );
                """
            )
            # Seed version row if empty.
            row = conn.execute("SELECT version FROM schema_version").fetchone()
            if row is None:
                conn.execute("INSERT INTO schema_version (version) VALUES (?)", (_SCHEMA_VERSION,))
        _initialised[db_path] = True


# ── One-time JSON → SQLite migration ─────────────────────────────────────────

def _maybe_migrate_users_json(db_path: Path, json_path: Path) -> int:
    """If the users table is empty and a users.json exists, import it.

    Returns the number of users imported. Renames the JSON to
    ``users.json.migrated`` after a successful import so it isn't re-imported
    on the next restart. A torn JSON file (invalid JSON) is left untouched
    and just produces a warning.
    """
    _ensure_schema(db_path)
    with _connect(db_path) as conn:
        count = conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"]
    if count > 0 or not json_path.is_file():
        return 0
    try:
        raw = json.loads(json_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("users.json present but unreadable, skipping migration: %s", e)
        return 0
    if not isinstance(raw, dict) or not raw:
        return 0

    imported = 0
    with _connect(db_path) as conn:
        conn.execute("BEGIN")
        try:
            for username, info in raw.items():
                if not isinstance(info, dict) or not info.get("password_hash"):
                    continue
                conn.execute(
                    """
                    INSERT INTO users (username, password_hash, is_admin, created_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        username,
                        info.get("password_hash", ""),
                        1 if info.get("is_admin") else 0,
                        info.get("created_at") or "",
                    ),
                )
                imported += 1
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
    # Rename the JSON so we don't re-import. Best-effort — if rename fails the
    # table is already populated, so the count check above will skip next time.
    try:
        json_path.rename(json_path.with_suffix(".json.migrated"))
        logger.info("Migrated %d users from %s to SQLite", imported, json_path.name)
    except OSError as e:
        logger.warning("Could not rename %s after migration: %s", json_path, e)
    return imported


# ── Public API: dict-compatible user store ────────────────────────────────────
# These functions match the JSON-era contract so callers in core/auth.py don't
# need to know SQLite exists. The on-disk shape changes; the in-memory dict
# shape stays identical.

def load_users(db_path: Path, json_path: Path | None = None) -> dict:
    """Return ``{username: {password_hash, is_admin, created_at}}``.

    On first call, opportunistically migrates ``users.json`` if present and
    the users table is empty.
    """
    _ensure_schema(db_path)
    if json_path is not None:
        _maybe_migrate_users_json(db_path, json_path)
    out: dict = {}
    try:
        with _connect(db_path) as conn:
            rows = conn.execute(
                "SELECT username, password_hash, is_admin, created_at FROM users"
            ).fetchall()
    except sqlite3.Error as e:
        logger.error("load_users failed: %s", e)
        return {}
    for row in rows:
        out[row["username"]] = {
            "password_hash": row["password_hash"],
            "is_admin": bool(row["is_admin"]),
            "created_at": row["created_at"],
        }
    return out


def save_users(db_path: Path, users: dict) -> None:
    """Replace the entire users table with the supplied dict.

    The whole-table replacement matches the JSON-era semantics where every
    save rewrote the file. A more granular API (``upsert_user``,
    ``delete_user``) is possible but would require changing every caller in
    ``core/auth.py``; the wholesale replace keeps this drop-in.

    Wrapped in a transaction so an exception mid-rewrite rolls back to the
    previous state instead of leaving the table half-empty.
    """
    _ensure_schema(db_path)
    with _connect(db_path) as conn:
        conn.execute("BEGIN")
        try:
            conn.execute("DELETE FROM users")
            for username, info in (users or {}).items():
                if not isinstance(info, dict):
                    continue
                conn.execute(
                    """
                    INSERT INTO users (username, password_hash, is_admin, created_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        username,
                        info.get("password_hash", ""),
                        1 if info.get("is_admin") else 0,
                        info.get("created_at") or "",
                    ),
                )
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise


# Test helpers — clear the initialised cache so a fresh tmp_path is picked up.
def _reset_for_tests() -> None:
    """Forget the per-path initialisation cache. Test-only."""
    _initialised.clear()
