"""Small HTTP client for an explicitly configured remote reconstruction worker.

Workers and the API server must share the configured imports/data/exports
storage.  This module deliberately sends only paths and reconstruction metadata;
it never uploads image bytes or persists a credential.
"""

from __future__ import annotations

import os
from urllib.parse import urlparse

import httpx


class RemoteWorkerError(RuntimeError):
    """A remote worker could not be safely contacted or returned an invalid response."""


def _base_url(config: dict) -> str:
    url = config["url"]
    parsed = urlparse(url)
    if parsed.scheme not in {"https", "http"} or not parsed.netloc or parsed.username:
        raise RemoteWorkerError(
            "Remote worker URL must be an absolute URL without user credentials"
        )
    if parsed.scheme != "https" and not config["allow_insecure_http"]:
        raise RemoteWorkerError(
            "Remote worker URL must use HTTPS (set allow_insecure_http only for development)"
        )
    return url


def _headers(config: dict) -> dict[str, str]:
    token_name = config["auth_token_env"]
    token = os.environ.get(token_name, "").strip()
    if not token:
        raise RemoteWorkerError(
            f"Remote worker token is missing from environment variable {token_name}"
        )
    return {"Authorization": f"Bearer {token}"}


def _request(config: dict, method: str, path: str, *, payload: dict | None = None) -> dict:
    try:
        response = httpx.request(
            method,
            f"{_base_url(config)}{path}",
            headers=_headers(config),
            json=payload,
            timeout=config["timeout_seconds"],
        )
        response.raise_for_status()
        body = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise RemoteWorkerError(f"Remote worker request failed: {exc}") from exc
    if not isinstance(body, dict):
        raise RemoteWorkerError("Remote worker returned a non-object JSON response")
    return body


def dispatch_reconstruction(
    config: dict, payload: dict, reconstruction_id: int, queue_job_id: int
) -> str:
    """Submit one shared-storage reconstruction and return the worker's durable job id."""
    body = _request(
        config,
        "POST",
        "/v1/reconstructions",
        payload={
            "local_job_id": queue_job_id,
            "reconstruction_id": reconstruction_id,
            "preset": payload["preset"],
            "colmap_dir": payload["colmap_dir"],
            "image_ids": payload["image_ids"],
        },
    )
    remote_job_id = body.get("job_id")
    if not isinstance(remote_job_id, str) or not remote_job_id:
        raise RemoteWorkerError("Remote worker response did not include job_id")
    return remote_job_id


def get_reconstruction_status(config: dict, remote_job_id: str) -> dict:
    """Return the worker's latest status object for a dispatched reconstruction."""
    return _request(config, "GET", f"/v1/reconstructions/{remote_job_id}")


def cancel_reconstruction(config: dict, remote_job_id: str) -> None:
    """Best-effort cancellation; the durable local queue remains the source of truth."""
    _request(config, "POST", f"/v1/reconstructions/{remote_job_id}/cancel")
