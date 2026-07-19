"""Minimal in-memory sessions for the opt-in single-user PIN lock."""

from __future__ import annotations

import time
from collections.abc import MutableMapping

from backend.services.share_links import create_opaque_token, token_hash, verify_password


def valid_pin(pin: str, pin_hash: str) -> bool:
    """Verify a PIN against the same stdlib-scrypt format as share passwords."""
    return verify_password(pin, pin_hash)


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
