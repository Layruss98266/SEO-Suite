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
_SCHEMA_VERSION = 5

# Login history retention — attempts older than this are pruned at write time.
# 90 days is a sensible default: long enough for audit / forensics, short
# enough to limit PII exposure (IPs + user-agents are quasi-identifying).
_LOGIN_HISTORY_RETENTION_DAYS = 90

# Cap per-user login-history list responses so the dashboard never has to
# render an unbounded table. The full history stays in SQLite either way.
_LOGIN_HISTORY_MAX_ROWS = 500

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
                    username        TEXT PRIMARY KEY,
                    password_hash   TEXT NOT NULL,
                    is_admin        INTEGER NOT NULL DEFAULT 0,
                    created_at      TEXT NOT NULL,
                    last_login_at   TEXT,
                    last_login_ip   TEXT
                );

                CREATE TABLE IF NOT EXISTS login_attempts (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    username    TEXT NOT NULL,
                    ts          TEXT NOT NULL,
                    ip          TEXT,
                    user_agent  TEXT,
                    success     INTEGER NOT NULL,
                    reason      TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_login_attempts_username_ts
                    ON login_attempts(username, ts DESC);
                CREATE INDEX IF NOT EXISTS idx_login_attempts_ts
                    ON login_attempts(ts DESC);

                -- Single-use tokens for password reset + email verification.
                -- We store only the SHA-256 hash so a database leak can't be
                -- used to mint a working reset link. Tokens are short-lived
                -- (default 1h) and consumed-on-use.
                CREATE TABLE IF NOT EXISTS auth_tokens (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    username    TEXT NOT NULL,
                    kind        TEXT NOT NULL,   -- 'password_reset' | 'email_verify'
                    token_hash  TEXT NOT NULL,
                    created_at  TEXT NOT NULL,
                    expires_at  TEXT NOT NULL,
                    consumed_at TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_auth_tokens_hash
                    ON auth_tokens(token_hash);
                CREATE INDEX IF NOT EXISTS idx_auth_tokens_username_kind
                    ON auth_tokens(username, kind);

                -- Server-side sessions. The session_id Flask puts in the
                -- cookie is just an opaque pointer into this table; logout
                -- here deletes the row, making the cookie immediately
                -- useless even though the cookie itself stays valid in the
                -- browser. Lets admins (and the user themselves) revoke a
                -- specific device's access without invalidating every
                -- session globally.
                CREATE TABLE IF NOT EXISTS sessions (
                    sid          TEXT PRIMARY KEY,
                    username     TEXT NOT NULL,
                    created_at   TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    expires_at   TEXT NOT NULL,
                    ip           TEXT,
                    user_agent   TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_sessions_username
                    ON sessions(username);
                CREATE INDEX IF NOT EXISTS idx_sessions_expires
                    ON sessions(expires_at);

                -- TOTP 2FA. One row per enrolled user. `secret` is the
                -- base32 shared secret (RFC 6238); `enabled` is the boolean
                -- that gates the login check (so we can stage enrolment
                -- separately from enforcement). `backup_codes` is a JSON
                -- array of single-use recovery codes hashed with SHA-256.
                CREATE TABLE IF NOT EXISTS totp_secrets (
                    username       TEXT PRIMARY KEY,
                    secret         TEXT NOT NULL,
                    enabled        INTEGER NOT NULL DEFAULT 0,
                    created_at     TEXT NOT NULL,
                    enabled_at     TEXT,
                    backup_codes   TEXT NOT NULL DEFAULT '[]'
                );
                """
            )
            # Migrate existing v1 databases that don't have the new user
            # columns. ALTER TABLE ADD COLUMN is cheap and idempotent here
            # because we wrap in try/except — sqlite3 raises if the column
            # already exists.
            for col_sql in (
                "ALTER TABLE users ADD COLUMN last_login_at TEXT",
                "ALTER TABLE users ADD COLUMN last_login_ip TEXT",
            ):
                try:
                    conn.execute(col_sql)
                except sqlite3.OperationalError:
                    pass  # column already exists

            # Seed or update version row.
            row = conn.execute("SELECT version FROM schema_version").fetchone()
            if row is None:
                conn.execute(
                    "INSERT INTO schema_version (version) VALUES (?)",
                    (_SCHEMA_VERSION,),
                )
            else:
                conn.execute("UPDATE schema_version SET version = ?", (_SCHEMA_VERSION,))
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


def get_user(db_path: Path, username: str) -> dict | None:
    """Return a single user dict (with last_login_at/ip) or None if absent."""
    _ensure_schema(db_path)
    try:
        with _connect(db_path) as conn:
            row = conn.execute(
                "SELECT username, password_hash, is_admin, created_at, "
                "last_login_at, last_login_ip FROM users WHERE username = ?",
                (username,),
            ).fetchone()
    except sqlite3.Error as e:
        logger.error("get_user failed: %s", e)
        return None
    if row is None:
        return None
    return {
        "username": row["username"],
        "password_hash": row["password_hash"],
        "is_admin": bool(row["is_admin"]),
        "created_at": row["created_at"],
        "last_login_at": row["last_login_at"],
        "last_login_ip": row["last_login_ip"],
    }


def update_last_login(db_path: Path, username: str, ts: str, ip: str | None) -> None:
    """Record successful login on the users row. Cheap UPDATE, no transaction
    needed (atomicity-of-one-row is implicit)."""
    _ensure_schema(db_path)
    try:
        with _connect(db_path) as conn:
            conn.execute(
                "UPDATE users SET last_login_at = ?, last_login_ip = ? WHERE username = ?",
                (ts, ip, username),
            )
    except sqlite3.Error as e:
        logger.warning("update_last_login failed for %s: %s", username, e)


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


# ── Login attempt history ────────────────────────────────────────────────────
# Every authenticate() call lands a row here — successes and failures alike.
# Useful for: account-takeover detection, audit trail, "last login" display,
# and revealing brute-force patterns at a finer grain than the per-process
# lockout map.
#
# Records are pruned to _LOGIN_HISTORY_RETENTION_DAYS on each write so the
# table stays bounded without a separate cron job.

def record_login_attempt(
    db_path: Path,
    username: str,
    success: bool,
    ip: str | None = None,
    user_agent: str | None = None,
    reason: str | None = None,
) -> None:
    """Append a single login-attempt row + prune anything older than retention.

    All fields are optional except username and success. ``reason`` is a short
    code like ``"locked_out"`` / ``"bad_password"`` / ``"ok"`` — keep it
    machine-readable so admins can filter the history view.
    """
    _ensure_schema(db_path)
    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc)
    ts = now.isoformat()
    cutoff = (now - timedelta(days=_LOGIN_HISTORY_RETENTION_DAYS)).isoformat()

    try:
        with _connect(db_path) as conn:
            conn.execute(
                """
                INSERT INTO login_attempts
                    (username, ts, ip, user_agent, success, reason)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    username,
                    ts,
                    ip,
                    user_agent[:512] if user_agent else None,  # cap UA length
                    1 if success else 0,
                    reason,
                ),
            )
            # Best-effort retention sweep on every write. Cheap on indexed ts.
            conn.execute("DELETE FROM login_attempts WHERE ts < ?", (cutoff,))
    except sqlite3.Error as e:
        # Logging a failed login should never raise back into the auth path.
        logger.warning("record_login_attempt failed: %s", e)


def get_login_history(
    db_path: Path,
    username: str | None = None,
    success: bool | None = None,
    limit: int = 100,
) -> list[dict]:
    """Return recent login attempts, newest first.

    Filter by ``username`` to view one account's history; leave None for
    admin-wide view. ``success=False`` filters to failures only (useful for
    spotting brute force).
    """
    _ensure_schema(db_path)
    limit = max(1, min(limit, _LOGIN_HISTORY_MAX_ROWS))

    clauses = []
    params: list = []
    if username is not None:
        clauses.append("username = ?")
        params.append(username)
    if success is not None:
        clauses.append("success = ?")
        params.append(1 if success else 0)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    params.append(limit)

    try:
        with _connect(db_path) as conn:
            rows = conn.execute(
                f"SELECT id, username, ts, ip, user_agent, success, reason "
                f"FROM login_attempts {where} ORDER BY ts DESC LIMIT ?",
                params,
            ).fetchall()
    except sqlite3.Error as e:
        logger.error("get_login_history failed: %s", e)
        return []

    return [
        {
            "id": r["id"],
            "username": r["username"],
            "ts": r["ts"],
            "ip": r["ip"],
            "user_agent": r["user_agent"],
            "success": bool(r["success"]),
            "reason": r["reason"],
        }
        for r in rows
    ]


def count_recent_failures(
    db_path: Path, username: str, window_seconds: int = 900
) -> int:
    """Count failed attempts for *username* in the last *window_seconds*.

    Lets the auth layer cross-check its in-memory lockout state against
    persistent records — important after a process restart, when the
    in-memory ``_failed_attempts`` dict is empty but the SQLite history isn't.
    """
    _ensure_schema(db_path)
    from datetime import datetime, timedelta, timezone

    cutoff = (
        datetime.now(timezone.utc) - timedelta(seconds=window_seconds)
    ).isoformat()
    try:
        with _connect(db_path) as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM login_attempts "
                "WHERE username = ? AND success = 0 AND ts >= ?",
                (username, cutoff),
            ).fetchone()
    except sqlite3.Error as e:
        logger.error("count_recent_failures failed: %s", e)
        return 0
    return int(row["n"] or 0)


# ── Auth tokens (password reset + email verification) ───────────────────────
# We store SHA-256 of the raw token so a DB leak can't mint working links.
# Tokens are single-use: the consume path marks consumed_at and any later
# verify on the same token fails.

def _hash_token(token: str) -> str:
    import hashlib

    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def issue_auth_token(
    db_path: Path, username: str, kind: str, ttl_seconds: int = 3600
) -> str:
    """Mint a fresh single-use token. Returns the RAW token (only time it's exposed).

    Caller is responsible for transmitting the raw token via a side channel
    (email, signed URL parameter, etc.) — we only store the hash.

    Invalidates any existing un-consumed tokens of the same kind for the same
    user so a stolen previous token can't be reused after a new one is issued.
    """
    import secrets
    from datetime import datetime, timedelta, timezone

    _ensure_schema(db_path)
    raw = secrets.token_urlsafe(48)  # ~64 chars of base64url
    h = _hash_token(raw)
    now = datetime.now(timezone.utc)
    expires = now + timedelta(seconds=ttl_seconds)

    try:
        with _connect(db_path) as conn:
            conn.execute("BEGIN")
            # Revoke older outstanding tokens of this kind for the same user.
            conn.execute(
                """
                UPDATE auth_tokens
                   SET consumed_at = ?
                 WHERE username = ?
                   AND kind = ?
                   AND consumed_at IS NULL
                """,
                (now.isoformat(), username, kind),
            )
            conn.execute(
                """
                INSERT INTO auth_tokens
                    (username, kind, token_hash, created_at, expires_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (username, kind, h, now.isoformat(), expires.isoformat()),
            )
            conn.execute("COMMIT")
    except Exception:
        # Don't swallow — caller needs to know if the token issuance failed.
        raise
    return raw


def peek_auth_token(db_path: Path, token: str, kind: str) -> str | None:
    """Validate a token and return the associated username WITHOUT consuming it.

    Used to run policy checks (password strength, etc.) before the token is
    burned so a failed policy check doesn't invalidate the user's reset link.
    Call consume_auth_token() immediately after the policy check passes.
    """
    from datetime import datetime, timezone

    _ensure_schema(db_path)
    if not token:
        return None
    h = _hash_token(token)
    now = datetime.now(timezone.utc).isoformat()
    try:
        with _connect(db_path) as conn:
            row = conn.execute(
                """
                SELECT username, expires_at, consumed_at
                  FROM auth_tokens
                 WHERE token_hash = ? AND kind = ?
                """,
                (h, kind),
            ).fetchone()
            if row is None or row["consumed_at"] is not None:
                return None
            if row["expires_at"] < now:
                return None
            return row["username"]
    except sqlite3.Error as e:
        logger.error("peek_auth_token failed: %s", e)
        return None


def consume_auth_token(db_path: Path, token: str, kind: str) -> str | None:
    """Verify, consume, and return the associated username if valid; else None.

    Atomic check-and-set under a transaction so the same token can't be used
    by two concurrent requests (e.g. a double-click). Expired tokens fail
    cleanly. Already-consumed tokens fail.
    """
    from datetime import datetime, timezone

    _ensure_schema(db_path)
    if not token:
        return None
    h = _hash_token(token)
    now = datetime.now(timezone.utc).isoformat()

    try:
        with _connect(db_path) as conn:
            conn.execute("BEGIN")
            row = conn.execute(
                """
                SELECT id, username, expires_at, consumed_at
                  FROM auth_tokens
                 WHERE token_hash = ? AND kind = ?
                """,
                (h, kind),
            ).fetchone()
            if row is None or row["consumed_at"] is not None:
                conn.execute("ROLLBACK")
                return None
            if row["expires_at"] < now:
                conn.execute("ROLLBACK")
                return None
            conn.execute(
                "UPDATE auth_tokens SET consumed_at = ? WHERE id = ?",
                (now, row["id"]),
            )
            conn.execute("COMMIT")
            return row["username"]
    except sqlite3.Error as e:
        logger.error("consume_auth_token failed: %s", e)
        return None


def reset_password_hash(db_path: Path, username: str, new_hash: str) -> bool:
    """Update a user's password hash directly. Used by the password-reset flow
    (we've already verified the reset token; the user doesn't need to supply
    their old password).
    """
    _ensure_schema(db_path)
    try:
        with _connect(db_path) as conn:
            cur = conn.execute(
                "UPDATE users SET password_hash = ? WHERE username = ?",
                (new_hash, username),
            )
            return cur.rowcount == 1
    except sqlite3.Error as e:
        logger.error("reset_password_hash failed: %s", e)
        return False


# ── Email verification flag ──────────────────────────────────────────────────
def set_email_verified(db_path: Path, username: str, verified: bool = True) -> bool:
    """Flag a user's email as verified. Adds the column if it's missing."""
    _ensure_schema(db_path)
    try:
        with _connect(db_path) as conn:
            try:
                conn.execute("ALTER TABLE users ADD COLUMN email_verified INTEGER NOT NULL DEFAULT 0")
            except sqlite3.OperationalError:
                pass  # column already exists
            cur = conn.execute(
                "UPDATE users SET email_verified = ? WHERE username = ?",
                (1 if verified else 0, username),
            )
            return cur.rowcount == 1
    except sqlite3.Error as e:
        logger.error("set_email_verified failed: %s", e)
        return False


def get_email_verified(db_path: Path, username: str) -> bool:
    _ensure_schema(db_path)
    try:
        with _connect(db_path) as conn:
            try:
                row = conn.execute(
                    "SELECT email_verified FROM users WHERE username = ?",
                    (username,),
                ).fetchone()
            except sqlite3.OperationalError:
                return False
            return bool(row and row["email_verified"])
    except sqlite3.Error:
        return False


# ── Sessions (server-side, revocable) ───────────────────────────────────────
# We let Flask manage the signed cookie + secret rotation but pin every
# request to a database row keyed by a server-issued opaque session_id.
# Logging out (or an admin revoking a session) deletes the row, making the
# cookie immediately useless. The session is *also* expired by the cookie's
# own lifetime — both must be valid for a request to succeed.

_SESSION_TTL_DAYS = 30


def create_session(
    db_path: Path,
    username: str,
    ip: str | None,
    user_agent: str | None,
    ttl_days: int = _SESSION_TTL_DAYS,
) -> str:
    """Mint a new session row. Returns the opaque session ID.

    The session ID is base64url, ~32 bytes of entropy. Caller is responsible
    for putting it in the Flask session cookie under the agreed key.
    """
    import secrets
    from datetime import datetime, timedelta, timezone

    _ensure_schema(db_path)
    sid = secrets.token_urlsafe(24)
    now = datetime.now(timezone.utc)
    expires = now + timedelta(days=ttl_days)
    try:
        with _connect(db_path) as conn:
            conn.execute(
                """
                INSERT INTO sessions
                    (sid, username, created_at, last_seen_at, expires_at, ip, user_agent)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    sid,
                    username,
                    now.isoformat(),
                    now.isoformat(),
                    expires.isoformat(),
                    ip,
                    (user_agent or "")[:512] or None,
                ),
            )
    except sqlite3.Error as e:
        logger.error("create_session failed: %s", e)
        raise
    return sid


def validate_session(db_path: Path, sid: str) -> str | None:
    """Return the username for *sid* if the session is live and not expired.

    Also touches ``last_seen_at`` for activity tracking. Returns None for
    unknown / expired sessions.
    """
    from datetime import datetime, timezone

    if not sid:
        return None
    _ensure_schema(db_path)
    now = datetime.now(timezone.utc).isoformat()
    try:
        with _connect(db_path) as conn:
            row = conn.execute(
                "SELECT username, expires_at FROM sessions WHERE sid = ?",
                (sid,),
            ).fetchone()
            if row is None:
                return None
            if row["expires_at"] < now:
                # Best-effort cleanup of the expired row so it doesn't
                # accumulate indefinitely.
                conn.execute("DELETE FROM sessions WHERE sid = ?", (sid,))
                return None
            conn.execute(
                "UPDATE sessions SET last_seen_at = ? WHERE sid = ?", (now, sid)
            )
            return row["username"]
    except sqlite3.Error as e:
        logger.error("validate_session failed: %s", e)
        return None


def delete_session(db_path: Path, sid: str) -> bool:
    """Revoke a single session. Returns True if a row was deleted."""
    _ensure_schema(db_path)
    try:
        with _connect(db_path) as conn:
            cur = conn.execute("DELETE FROM sessions WHERE sid = ?", (sid,))
            return cur.rowcount > 0
    except sqlite3.Error:
        return False


def delete_sessions_for_user(db_path: Path, username: str, except_sid: str | None = None) -> int:
    """Revoke every active session for *username* (optionally keeping one).

    Used by "sign out everywhere" and by the password-change flow (a stolen
    cookie should stop working as soon as the password is rotated).
    """
    _ensure_schema(db_path)
    try:
        with _connect(db_path) as conn:
            if except_sid:
                cur = conn.execute(
                    "DELETE FROM sessions WHERE username = ? AND sid != ?",
                    (username, except_sid),
                )
            else:
                cur = conn.execute("DELETE FROM sessions WHERE username = ?", (username,))
            return cur.rowcount
    except sqlite3.Error:
        return 0


def list_sessions(db_path: Path, username: str) -> list[dict]:
    """Return all live sessions for a user, newest first."""
    from datetime import datetime, timezone

    _ensure_schema(db_path)
    now = datetime.now(timezone.utc).isoformat()
    try:
        with _connect(db_path) as conn:
            # Drop expired rows on read so the list stays clean.
            conn.execute("DELETE FROM sessions WHERE expires_at < ?", (now,))
            rows = conn.execute(
                """
                SELECT sid, username, created_at, last_seen_at, expires_at, ip, user_agent
                  FROM sessions
                 WHERE username = ?
                 ORDER BY last_seen_at DESC
                """,
                (username,),
            ).fetchall()
    except sqlite3.Error:
        return []
    return [
        {
            "sid": r["sid"],
            "username": r["username"],
            "created_at": r["created_at"],
            "last_seen_at": r["last_seen_at"],
            "expires_at": r["expires_at"],
            "ip": r["ip"],
            "user_agent": r["user_agent"],
        }
        for r in rows
    ]


# Test helpers — clear the initialised cache so a fresh tmp_path is picked up.
def _reset_for_tests() -> None:
    """Forget the per-path initialisation cache. Test-only."""
    _initialised.clear()
