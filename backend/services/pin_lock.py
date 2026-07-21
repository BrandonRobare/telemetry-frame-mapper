"""Minimal in-memory sessions for the opt-in single-user PIN lock."""

from __future__ import annotations

import math
import time
from collections.abc import MutableMapping

from backend.services.share_links import create_opaque_token, token_hash, verify_password


def valid_pin(pin: str, pin_hash: str) -> bool:
    """Verify a PIN against the same stdlib-scrypt format as share passwords."""
    return verify_password(pin, pin_hash)


def valid_api_key(api_key: str, key_hash: str) -> bool:
    """Verify an automation key using the same constant-time scrypt check as a PIN."""
    return verify_password(api_key, key_hash)


def create_session(sessions: MutableMapping[str, float], ttl: int) -> str:
    """Store only a digest of a random cookie token; restarting drops sessions."""
    token = create_opaque_token()
    sessions[token_hash(token)] = time.time() + ttl
    return token


def session_is_valid(sessions: MutableMapping[str, float], token: str | None) -> bool:
    """Reject expired or unknown tokens and remove expired entries opportunistically."""
    now = time.time()
    for digest, expires_at in list(sessions.items()):
        if expires_at <= now:
            del sessions[digest]
    return bool(token and sessions.get(token_hash(token), 0) > now)


# Shared failed-unlock throttle for the PIN and share-link unlock endpoints.
# ponytail: in-memory per-process counter — single-process deployment only;
# move to DB if multi-worker ever ships.
_BACKOFF_THRESHOLD = 5  # consecutive failures before backoff starts
_LOCKOUT_THRESHOLD = 10  # consecutive failures before the long lockout
_LOCKOUT_SECONDS = 15 * 60


def unlock_retry_after(attempts: MutableMapping[str, list], client: str) -> int:
    """Seconds this client must wait before another unlock attempt (0 if allowed now)."""
    entry = attempts.get(client)
    if not entry:
        return 0
    return max(0, math.ceil(entry[1] - time.time()))


def record_unlock_failure(attempts: MutableMapping[str, list], client: str) -> None:
    """Count a failed unlock and apply exponential backoff, then a 15-minute lockout."""
    now = time.time()
    entry = attempts.get(client) or [0, 0.0]
    entry[0] += 1
    fails = entry[0]
    if fails >= _LOCKOUT_THRESHOLD:
        entry[1] = now + _LOCKOUT_SECONDS
    elif fails >= _BACKOFF_THRESHOLD:
        entry[1] = now + 2 ** (fails - _BACKOFF_THRESHOLD + 1)  # 2s, 4s, 8s, 16s, 32s
    attempts[client] = entry


def reset_unlock_attempts(attempts: MutableMapping[str, list], client: str) -> None:
    """Clear a client's failure streak after a successful unlock."""
    attempts.pop(client, None)
