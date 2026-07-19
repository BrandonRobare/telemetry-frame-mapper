"""Minimal, opt-in HTTP client for the documented WebODM API."""

from __future__ import annotations

import json
import os
from contextlib import ExitStack
from pathlib import Path
from urllib.parse import urlparse

import httpx


class WebODMError(RuntimeError):
    """WebODM is unavailable, misconfigured, or returned an invalid response."""


def validate_connection_config(config: dict) -> None:
    """Fail fast when the operator has not enabled a usable WebODM connection.

    This deliberately performs no network I/O.  Call it before queueing or
    presenting WebODM as an available reconstruction backend.
    """
    _base_url(config)
    _headers(config)


def _base_url(config: dict) -> str:
    if not config.get("enabled"):
        raise WebODMError("WebODM integration is disabled in config.yaml")
    url = str(config.get("url", ""))
    parsed = urlparse(url)
    if parsed.scheme not in {"https", "http"} or not parsed.netloc or parsed.username:
        raise WebODMError("WebODM URL must be an absolute URL without user credentials")
    if parsed.path not in {"", "/"} or parsed.params or parsed.query or parsed.fragment:
        raise WebODMError("WebODM URL must be the server origin, without an API path")
    if parsed.scheme != "https" and not config.get("allow_insecure_http"):
        raise WebODMError(
            "WebODM URL must use HTTPS (set allow_insecure_http only for development)"
        )
    return url.rstrip("/")


def _headers(config: dict) -> dict[str, str]:
    name = str(config.get("jwt_env", "WEBODM_JWT"))
    token = os.environ.get(name, "").strip()
    if not token:
        raise WebODMError(f"WebODM JWT is missing from environment variable {name}")
    return {"Authorization": f"JWT {token}"}


def _request(config: dict, method: str, path: str, **kwargs) -> httpx.Response:
    try:
        response = httpx.request(
            method,
            f"{_base_url(config)}{path}",
            headers=_headers(config),
            timeout=config["timeout_seconds"],
            **kwargs,
        )
        response.raise_for_status()
        return response
    except httpx.HTTPError as exc:
        raise WebODMError(f"WebODM request failed: {exc}") from exc


def _json(response: httpx.Response) -> dict:
    try:
        body = response.json()
    except ValueError as exc:
        raise WebODMError("WebODM returned invalid JSON") from exc
    if not isinstance(body, dict):
        raise WebODMError("WebODM returned a non-object JSON response")
    return body


def create_project(config: dict, name: str) -> int:
    body = _json(_request(config, "POST", "/api/projects/", data={"name": name}))
    project_id = body.get("id")
    if not isinstance(project_id, int):
        raise WebODMError("WebODM project response did not include an integer id")
    return project_id


def create_task(
    config: dict, project_id: int, name: str, images: list[Path], options: list[dict]
) -> int:
    if len(images) < 2:
        raise WebODMError("WebODM requires at least two images per task")
    with ExitStack() as stack:
        files = [
            ("images", (image.name, stack.enter_context(image.open("rb")), "image/jpeg"))
            for image in images
        ]
        body = _json(
            _request(
                config,
                "POST",
                f"/api/projects/{project_id}/tasks/",
                data={"name": name, "options": json.dumps(options)},
                files=files,
            )
        )
    task_id = body.get("id")
    if not isinstance(task_id, int):
        raise WebODMError("WebODM task response did not include an integer id")
    return task_id


def get_task(config: dict, project_id: int, task_id: int) -> dict:
    return _json(_request(config, "GET", f"/api/projects/{project_id}/tasks/{task_id}/"))


def cancel_task(config: dict, project_id: int, task_id: int) -> None:
    _request(config, "POST", f"/api/projects/{project_id}/tasks/{task_id}/cancel/")


def download_asset(
    config: dict, project_id: int, task_id: int, asset: str, output_dir: Path
) -> Path:
    filename = Path(asset).name
    if filename != asset or not filename:
        raise WebODMError("WebODM asset name must be a filename")
    response = _request(
        config, "GET", f"/api/projects/{project_id}/tasks/{task_id}/download/{filename}"
    )
    destination = output_dir / filename
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".part")
    try:
        temporary.write_bytes(response.content)
        temporary.replace(destination)
    except OSError as exc:
        temporary.unlink(missing_ok=True)
        raise WebODMError(f"Unable to save WebODM asset: {exc}") from exc
    return destination
