"""
TOTP (Time-based One-Time Password) 2FA via pyotp + SQLite.

Flow:

1. **Enrol** — user hits ``POST /api/auth/totp/enroll``. We mint a fresh
   base32 secret, store it in ``totp_secrets`` with ``enabled=0``, and return
   the secret + an ``otpauth://`` provisioning URI. The user scans/types it
   into their authenticator app (Google Authenticator, 1Password, Authy,
   etc.).

2. **Verify + activate** — user submits the first 6-digit code from their
   app via ``POST /api/auth/totp/activate``. We verify it via pyotp; if it
   matches we flip ``enabled=1`` and generate 10 single-use backup codes.

3. **Login** — once enabled, the login flow asks for a TOTP code after the
   password succeeds. ``verify_code(username, code)`` checks the current
   30s window ± 1 step (so a code accepted right at the boundary still works).

4. **Backup codes** — if the user loses their authenticator they can supply
   a one-time backup code instead. Each code is SHA-256 hashed at issue;
   verification compares hashes and immediately consumes the matching one.

5. **Disable** — ``POST /api/auth/totp/disable`` clears the row after
   re-verifying the user's password (so a stolen session can't permanently
   weaken the account).

We don't render the QR server-side — the provisioning URI is short enough
to put through any JS QR library client-side, and rendering server-side
means the secret transits more places than it has to.
"""

from __future__ import annotations

import hashlib
import json
import logging
import secrets
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

# Number of single-use backup codes minted at activation.
_BACKUP_CODE_COUNT = 10
_BACKUP_CODE_BYTES = 6  # 12 hex chars

# How many ±30-second windows to accept on either side of "now". RFC 6238
# recommends 1 — accounts for small clock drift between phone + server
# without unduly extending the brute-force window.
_TOTP_VALID_WINDOW = 1

# Issuer name shown in the user's authenticator app.
_TOTP_ISSUER = "SEO Suite"


# ── Persistence ──────────────────────────────────────────────────────────────

def _ensure_schema(db_path: Path) -> None:
    """Defer to core.db so we don't duplicate the schema definition."""
    from core import db as _db

    _db._ensure_schema(db_path)


def _hash_backup_code(code: str) -> str:
    return hashlib.sha256(code.upper().encode("utf-8")).hexdigest()


def get_row(db_path: Path, username: str) -> dict | None:
    """Return the raw totp_secrets row for *username*, or None."""
    _ensure_schema(db_path)
    try:
        from core.db import _connect

        with _connect(db_path) as conn:
            row = conn.execute(
                "SELECT username, secret, enabled, created_at, enabled_at, backup_codes "
                "FROM totp_secrets WHERE username = ?",
                (username,),
            ).fetchone()
    except sqlite3.Error as e:
        logger.error("totp.get_row failed: %s", e)
        return None
    if row is None:
        return None
    return {
        "username": row["username"],
        "secret": row["secret"],
        "enabled": bool(row["enabled"]),
        "created_at": row["created_at"],
        "enabled_at": row["enabled_at"],
        "backup_codes": row["backup_codes"],
    }


def is_enabled(db_path: Path, username: str) -> bool:
    row = get_row(db_path, username)
    return bool(row and row["enabled"])


def enroll(db_path: Path, username: str) -> tuple[str, str]:
    """Mint a fresh secret + provisioning URI. Idempotent on existing rows
    (re-enrolling regenerates the secret, which invalidates the old one).

    Returns ``(secret, otpauth_uri)``. ``enabled`` stays False until the user
    verifies their first code via :func:`activate`.
    """
    _ensure_schema(db_path)
    try:
        import pyotp
    except ImportError as e:
        raise RuntimeError("pyotp not installed — install via `pip install pyotp`") from e

    secret = pyotp.random_base32()
    now = datetime.now(timezone.utc).isoformat()
    try:
        from core.db import _connect

        with _connect(db_path) as conn:
            # INSERT OR REPLACE wipes the old row + backup codes; re-enrolling
            # is always a fresh start.
            conn.execute(
                """
                INSERT OR REPLACE INTO totp_secrets
                    (username, secret, enabled, created_at, enabled_at, backup_codes)
                VALUES (?, ?, 0, ?, NULL, '[]')
                """,
                (username, secret, now),
            )
    except sqlite3.Error as e:
        logger.error("totp.enroll failed: %s", e)
        raise

    uri = pyotp.totp.TOTP(secret).provisioning_uri(name=username, issuer_name=_TOTP_ISSUER)
    return secret, uri


def activate(db_path: Path, username: str, code: str) -> tuple[bool, list[str] | None]:
    """Verify the user's first TOTP code and flip ``enabled=1``.

    Returns ``(ok, backup_codes_or_None)``. The plaintext backup codes are
    returned **only here, only once** — the user must save them now. The DB
    stores hashes only.
    """
    _ensure_schema(db_path)
    row = get_row(db_path, username)
    if row is None:
        return False, None
    if row["enabled"]:
        return False, None  # Already enabled — must disable first to re-activate

    if not verify_code_against_secret(row["secret"], code):
        return False, None

    # Generate backup codes.
    plaintext_codes = [secrets.token_hex(_BACKUP_CODE_BYTES).upper() for _ in range(_BACKUP_CODE_COUNT)]
    hashed = [_hash_backup_code(c) for c in plaintext_codes]
    now = datetime.now(timezone.utc).isoformat()

    try:
        from core.db import _connect

        with _connect(db_path) as conn:
            conn.execute(
                """
                UPDATE totp_secrets
                   SET enabled = 1, enabled_at = ?, backup_codes = ?
                 WHERE username = ?
                """,
                (now, json.dumps(hashed), username),
            )
    except sqlite3.Error as e:
        logger.error("totp.activate failed: %s", e)
        return False, None

    return True, plaintext_codes


def disable(db_path: Path, username: str) -> bool:
    """Remove the user's TOTP secret entirely. Caller is responsible for
    re-verifying the user's password before invoking this (we don't do it
    here so the call stays usable from admin endpoints too)."""
    _ensure_schema(db_path)
    try:
        from core.db import _connect

        with _connect(db_path) as conn:
            cur = conn.execute("DELETE FROM totp_secrets WHERE username = ?", (username,))
            return cur.rowcount > 0
    except sqlite3.Error:
        return False


# ── Verification ─────────────────────────────────────────────────────────────

def verify_code_against_secret(secret: str, code: str) -> bool:
    """Pure verification — no DB hit. Used during the activation flow."""
    try:
        import pyotp
    except ImportError:
        return False
    if not code:
        return False
    code = code.strip().replace(" ", "")
    try:
        return pyotp.TOTP(secret).verify(code, valid_window=_TOTP_VALID_WINDOW)
    except Exception:
        return False


def verify_code(db_path: Path, username: str, code: str) -> bool:
    """Verify a 6-digit TOTP code against the user's stored secret.

    Only succeeds for users whose 2FA is enabled. Doesn't consume backup
    codes — :func:`consume_backup_code` is the separate path for those.
    """
    row = get_row(db_path, username)
    if not row or not row["enabled"]:
        return False
    return verify_code_against_secret(row["secret"], code)


def consume_backup_code(db_path: Path, username: str, code: str) -> bool:
    """Verify *code* against the stored hashes and remove it on success.

    Each backup code works exactly once. The DB write is wrapped in a
    transaction so two concurrent submissions of the same code can't both
    succeed.
    """
    row = get_row(db_path, username)
    if not row or not row["enabled"] or not code:
        return False

    target_hash = _hash_backup_code(code.strip())
    try:
        from core.db import _connect

        with _connect(db_path) as conn:
            conn.execute("BEGIN")
            cur_row = conn.execute(
                "SELECT backup_codes FROM totp_secrets WHERE username = ?",
                (username,),
            ).fetchone()
            if cur_row is None:
                conn.execute("ROLLBACK")
                return False
            try:
                codes = json.loads(cur_row["backup_codes"] or "[]")
            except json.JSONDecodeError:
                codes = []
            if target_hash not in codes:
                conn.execute("ROLLBACK")
                return False
            codes.remove(target_hash)
            conn.execute(
                "UPDATE totp_secrets SET backup_codes = ? WHERE username = ?",
                (json.dumps(codes), username),
            )
            conn.execute("COMMIT")
            return True
    except sqlite3.Error as e:
        logger.error("totp.consume_backup_code failed: %s", e)
        return False


def remaining_backup_codes(db_path: Path, username: str) -> int:
    """How many unused backup codes does this user have? UI uses this to
    nag once the count gets low."""
    row = get_row(db_path, username)
    if not row:
        return 0
    try:
        return len(json.loads(row["backup_codes"] or "[]"))
    except json.JSONDecodeError:
        return 0
