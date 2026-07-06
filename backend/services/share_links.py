"""Signed, time-limited share links for public read-only reconstruction access."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SHARE_LINK_EXPIRY_S = 7 * 24 * 3600  # 7 days default
SHARE_LINK_PREFIX = "tfm_share_"


def _signing_key() -> bytes:
    """Derive a stable HMAC key from a random secret stored on disk.

    Creates ``.share_signing_key`` in the config directory on first call,
    similar to how Flask's ``SECRET_KEY`` bootstraps itself.
    """
    from backend.core.config import get_config

    cfg = get_config()
    key_path = Path(cfg.exports_dir).parent / ".share_signing_key"
    if key_path.exists():
        return key_path.read_bytes()
    raw = secrets.token_bytes(64)
    key_path.parent.mkdir(parents=True, exist_ok=True)
    key_path.write_bytes(raw)
    # Restrict permissions (owner rw only).
    key_path.chmod(0o600)
    return raw


@dataclass(frozen=True)
class ShareToken:
    reconstruction_id: int
    session_id: int | None
    issued_at: float
    expires_at: float

    @property
    def expired(self) -> bool:
        return time.time() > self.expires_at


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64url_decode(s: str) -> bytes:
    # Add padding back.
    pad = 4 - len(s) % 4
    if pad != 4:
        s += "=" * pad
    return base64.urlsafe_b64decode(s)


def create_share_token(
    reconstruction_id: int,
    session_id: int | None = None,
    *,
    expiry_s: int = SHARE_LINK_EXPIRY_S,
) -> str:
    """Build a signed, time-limited share token string.

    The token is an opaque HMAC-signed blob.  The caller prepends
    ``SHARE_LINK_PREFIX`` for routing and hands it back in a share URL.
    """
    now = time.time()
    payload = {
        "rid": reconstruction_id,
        "sid": session_id,
        "iat": int(now),
        "exp": int(now + expiry_s),
    }
    payload_json = json.dumps(payload, separators=(",", ":")).encode()
    sig = hmac.digest(_signing_key(), payload_json, hashlib.sha256)
    return _b64url(payload_json) + "." + _b64url(sig)


def parse_share_token(token: str) -> ShareToken:
    """Validate and decode a share token.

    Returns:
        ``ShareToken`` on success.

    Raises:
        ``ValueError`` if the token is malformed, the signature doesn't match,
        or the token has expired.
    """
    if "." not in token:
        raise ValueError("Malformed token")
    payload_b64, sig_b64 = token.rsplit(".", 1)
    payload_bytes = _b64url_decode(payload_b64)
    expected_sig = hmac.digest(_signing_key(), payload_bytes, hashlib.sha256)
    actual_sig = _b64url_decode(sig_b64)
    if not hmac.compare_digest(expected_sig, actual_sig):
        raise ValueError("Invalid token signature")
    try:
        data = json.loads(payload_bytes)
    except json.JSONDecodeError as exc:
        raise ValueError("Malformed token payload") from exc
    token_obj = ShareToken(
        reconstruction_id=int(data["rid"]),
        session_id=data.get("sid"),
        issued_at=float(data["iat"]),
        expires_at=float(data["exp"]),
    )
    if token_obj.expired:
        raise ValueError("Token expired")
    return token_obj


def build_public_viewer_payload(rec: Any) -> dict:
    """Return a read-only payload for the public viewer.

    The response NEVER includes filesystem paths — only curated metadata
    and relative download URLs that the public viewer routes resolve.
    """
    return {
        "reconstruction_id": rec.id,
        "session_id": rec.session_id,
        "status": rec.status,
        "frames_used": rec.frames_used,
        "frames_registered": rec.frames_registered,
        "gaussian_count": rec.gaussian_count,
        "psnr": rec.psnr,
        "ssim": rec.ssim,
        "artifacts": {
            "pointcloud": (
                f"/share/{rec.id}/pointcloud"
            ),
            "mesh_glb": (
                f"/share/{rec.id}/mesh?format=glb" if rec.mesh_glb_path else None
            ),
            "mesh_obj": (
                f"/share/{rec.id}/mesh?format=obj" if rec.mesh_obj_path else None
            ),
        },
        "generated_at": time.time(),
    }