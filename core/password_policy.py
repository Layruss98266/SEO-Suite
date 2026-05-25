"""
Password-strength policy checks layered on top of the bare length minimum.

Two checks are layered on top of the 12-char minimum already enforced by
``core.auth.create_user`` / ``change_password``:

1. **zxcvbn strength score** — rejects passwords that score below 3 out of 4
   on Dropbox's zxcvbn library. zxcvbn understands dictionary words, common
   patterns (``qwerty``, ``12345``, dates), keyboard walks, and l33tspeak
   substitutions — far smarter than "must contain uppercase + number + symbol"
   theater that's been proven ineffective.

2. **HaveIBeenPwned k-anonymity API** — checks if the password appears in any
   public breach corpus without ever transmitting the full password or its
   full SHA-1. We send only the first 5 chars of the SHA-1 prefix; HIBP
   returns the suffix tail for that prefix and we match locally. Free, no
   API key needed.

Both checks are opt-out via env var so air-gapped installs aren't broken:

* ``SEO_SUITE_DISABLE_ZXCVBN=1`` — skip strength scoring
* ``SEO_SUITE_DISABLE_HIBP=1`` — skip breach lookup (and on any network error,
  the check is treated as a no-op so a flaky HIBP can't lock users out)
"""

from __future__ import annotations

import hashlib
import logging
import os

logger = logging.getLogger(__name__)

# Minimum acceptable zxcvbn score. Scale 0–4:
#   0 too guessable     ⌐ 10^3 guesses
#   1 very guessable    ⌐ 10^6
#   2 somewhat guessable ⌐ 10^8
#   3 safely unguessable ⌐ 10^10  (target for typical users)
#   4 very unguessable   ⌐ 10^14  (target for high-value accounts)
_MIN_ZXCVBN_SCORE = 3

# HIBP k-anonymity endpoint. We send the first 5 hex chars of the SHA-1 and
# receive ~500-1000 lines of "SUFFIX:count" — fast match on the suffix.
_HIBP_URL = "https://api.pwnedpasswords.com/range/{prefix}"


def check_strength(password: str, username: str = "") -> tuple[bool, str | None]:
    """Score *password* via zxcvbn. Returns ``(ok, error_or_hint)``.

    Passing the *username* lets zxcvbn penalise passwords that contain it
    (a very common weak-password pattern: ``alice2024!``).

    Returns ``(True, None)`` when:
      * zxcvbn is disabled via env var
      * zxcvbn isn't installed (graceful degradation)
      * the score meets the threshold
    """
    if os.environ.get("SEO_SUITE_DISABLE_ZXCVBN") == "1":
        return True, None
    try:
        from zxcvbn import zxcvbn
    except ImportError:
        logger.debug("zxcvbn not installed — skipping strength check")
        return True, None

    user_inputs = [username] if username else []
    result = zxcvbn(password, user_inputs=user_inputs)
    score = result.get("score", 0)
    if score >= _MIN_ZXCVBN_SCORE:
        return True, None

    # Build a friendly error message from zxcvbn's feedback.
    feedback = result.get("feedback", {}) or {}
    warning = feedback.get("warning") or ""
    suggestions = feedback.get("suggestions") or []
    suggestion_text = " ".join(suggestions) if suggestions else ""

    msg = f"Password is too weak (strength {score}/4)."
    if warning:
        msg += f" {warning}."
    if suggestion_text:
        msg += f" {suggestion_text}"
    return False, msg


def check_breached(password: str, timeout: float = 3.0) -> tuple[bool, int]:
    """Check the HIBP Pwned Passwords list. Returns ``(is_breached, occurrence_count)``.

    Uses the k-anonymity API: we transmit only the first 5 hex chars of the
    SHA-1 hash. HIBP returns suffix:count pairs for every hash starting with
    that prefix; we match the rest of OUR hash locally and never reveal the
    full password.

    Returns ``(False, 0)`` on:
      * disabled via env var
      * network error / timeout (fail-open: a flaky HIBP must not lock
        users out of password rotation)
      * any unexpected response shape
    """
    if os.environ.get("SEO_SUITE_DISABLE_HIBP") == "1":
        return False, 0
    if not password:
        return False, 0

    sha1 = hashlib.sha1(password.encode("utf-8")).hexdigest().upper()
    prefix, suffix = sha1[:5], sha1[5:]
    url = _HIBP_URL.format(prefix=prefix)

    try:
        # We import lazily and use a short timeout — auth path latency matters.
        import requests

        resp = requests.get(
            url,
            timeout=timeout,
            headers={"User-Agent": "SEO-Suite/2.0 HIBP-Client", "Add-Padding": "true"},
        )
        if resp.status_code != 200:
            logger.debug("HIBP returned HTTP %s — treating as not-breached", resp.status_code)
            return False, 0
    except Exception as exc:
        logger.debug("HIBP request failed (%s) — treating as not-breached", exc)
        return False, 0

    for line in resp.text.splitlines():
        try:
            line_suffix, count_str = line.strip().split(":", 1)
        except ValueError:
            continue
        if line_suffix == suffix:
            try:
                count = int(count_str)
            except ValueError:
                count = 1
            if count > 0:
                return True, count
    return False, 0


def validate_new_password(
    password: str, username: str = "", *, check_hibp: bool = True
) -> tuple[bool, str | None]:
    """One-stop check used by signup, password change, and password reset.

    Runs zxcvbn first (cheap, local) then HIBP (network call). Returns
    ``(ok, error_message)``. Callers should still enforce their length
    minimum *before* calling this — zxcvbn happily scores a 3-char password
    as low and we don't want to leak length policy errors through this layer.
    """
    ok, err = check_strength(password, username)
    if not ok:
        return False, err

    if check_hibp:
        breached, count = check_breached(password)
        if breached:
            return False, (
                f"This password has appeared in {count:,} known data breaches. "
                "Please choose a different password (see haveibeenpwned.com)."
            )

    return True, None
