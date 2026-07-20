"""Small, opt-in Cesium ion client for uploading the existing 3D Tiles bundle."""

from __future__ import annotations

import hashlib
import hmac
import os
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, urlparse

import httpx

from ..core.config import get_config


def _directory_prefix(root: str) -> str:
    return root if root.endswith(os.sep) else f"{root}{os.sep}"


class CesiumIonError(RuntimeError):
    """Cesium ion is disabled, misconfigured, or did not accept an upload."""


def _base_url(config: dict) -> str:
    if not config.get("enabled"):
        raise CesiumIonError("Cesium ion upload is disabled in config.yaml")
    url = str(config.get("api_url", ""))
    parsed = urlparse(url)
    if (
        parsed.scheme not in {"https", "http"}
        or not parsed.netloc
        or parsed.username
        or parsed.password
        or parsed.params
        or parsed.query
        or parsed.fragment
    ):
        raise CesiumIonError("Cesium ion API URL must be an absolute URL without credentials")
    if parsed.scheme != "https" and not config.get("allow_insecure_http"):
        raise CesiumIonError(
            "Cesium ion API URL must use HTTPS (set allow_insecure_http only for development)"
        )
    return url.rstrip("/")


def _headers(config: dict) -> dict[str, str]:
    name = str(config.get("token_env", "CESIUM_ION_TOKEN"))
    token = os.environ.get(name, "").strip()
    if not token:
        raise CesiumIonError(f"Cesium ion token is missing from environment variable {name}")
    return {"Authorization": f"Bearer {token}"}


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
        status = exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else None
        detail = f" ({status})" if status else ""
        raise CesiumIonError(
            f"Cesium ion request failed{detail}; check token scopes and connectivity"
        ) from exc


def _response_object(response: httpx.Response) -> dict:
    try:
        body = response.json()
    except ValueError as exc:
        raise CesiumIonError("Cesium ion returned invalid JSON") from exc
    if not isinstance(body, dict):
        raise CesiumIonError("Cesium ion returned a non-object JSON response")
    return body


def _required_upload_value(upload: dict, name: str) -> str:
    value = upload.get(name)
    if not isinstance(value, str) or not value:
        raise CesiumIonError(f"Cesium ion upload response did not include {name}")
    return value


def _signing_key(secret: str, date: str, region: str) -> bytes:
    key = ("AWS4" + secret).encode()
    for value in (date, region, "s3", "aws4_request"):
        key = hmac.new(key, value.encode(), hashlib.sha256).digest()
    return key


def _upload_bundle(config: dict, upload: dict, filename: str, body: bytes) -> None:
    """Upload one ZIP with temporary S3 credentials returned by ion.

    Cesium provides a bucket/prefix plus short-lived AWS credentials.  Signing
    a single PUT here avoids adding an SDK solely for this optional pathway.
    """
    bucket = _required_upload_value(upload, "bucket")
    prefix = _required_upload_value(upload, "prefix")
    access_key = _required_upload_value(upload, "accessKey")
    secret = _required_upload_value(upload, "secretAccessKey")
    session_token = _required_upload_value(upload, "sessionToken")
    endpoint = str(upload.get("endpoint") or f"https://{bucket}.s3.amazonaws.com").rstrip("/")
    parsed = urlparse(endpoint)
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        raise CesiumIonError("Cesium ion returned an unsafe upload endpoint")

    key = f"{prefix.rstrip('/')}/{filename}"
    canonical_uri = f"{parsed.path.rstrip('/')}/{quote(key, safe='/~')}".replace("//", "/")
    url = f"{parsed.scheme}://{parsed.netloc}{canonical_uri}"
    now = datetime.now(timezone.utc)
    timestamp, date = now.strftime("%Y%m%dT%H%M%SZ"), now.strftime("%Y%m%d")
    region = str(upload.get("region") or "us-east-1")
    payload_hash = hashlib.sha256(body).hexdigest()
    headers = {
        "host": parsed.netloc,
        "x-amz-content-sha256": payload_hash,
        "x-amz-date": timestamp,
        "x-amz-security-token": session_token,
    }
    signed_headers = ";".join(headers)
    canonical_headers = "".join(f"{name}:{headers[name]}\n" for name in headers)
    canonical_request = (
        f"PUT\n{canonical_uri}\n\n{canonical_headers}\n{signed_headers}\n{payload_hash}"
    )
    scope = f"{date}/{region}/s3/aws4_request"
    string_to_sign = "\n".join(
        (
            "AWS4-HMAC-SHA256",
            timestamp,
            scope,
            hashlib.sha256(canonical_request.encode()).hexdigest(),
        )
    )
    signature = hmac.new(
        _signing_key(secret, date, region), string_to_sign.encode(), hashlib.sha256
    ).hexdigest()
    authorization = (
        f"AWS4-HMAC-SHA256 Credential={access_key}/{scope}, "
        f"SignedHeaders={signed_headers}, Signature={signature}"
    )
    try:
        response = httpx.request(
            "PUT",
            url,
            headers={**headers, "Authorization": authorization},
            content=body,
            timeout=config["timeout_seconds"],
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise CesiumIonError("Cesium ion storage upload failed; check quota and retry") from exc


def upload_tileset(config: dict, bundle: Path, name: str) -> dict:
    """Create one 3D Tiles asset, upload the ZIP, and start Cesium processing."""
    _base_url(config)
    _headers(config)
    exports_root = os.path.normcase(os.path.normpath(os.path.realpath(get_config().exports_dir)))
    bundle_path = os.path.normcase(os.path.normpath(os.path.realpath(bundle)))
    exports_prefix = _directory_prefix(exports_root)
    if bundle_path != exports_root and not bundle_path.startswith(exports_prefix):
        raise CesiumIonError("Cesium ion upload bundle must be inside the exports directory")
    try:
        with open(bundle_path, "rb") as bundle_file:
            body = bundle_file.read()
    except OSError as exc:
        raise CesiumIonError("Cesium ion upload bundle does not exist") from exc
    created = _response_object(
        _request(
            config,
            "POST",
            "/assets",
            json={"name": name, "type": "3DTILES", "options": {"sourceType": "3DTILES"}},
        )
    )
    metadata = created.get("assetMetadata")
    asset_id = metadata.get("id") if isinstance(metadata, dict) else None
    if not isinstance(asset_id, int):
        raise CesiumIonError("Cesium ion asset response did not include an integer id")
    upload = created.get("uploadLocation")
    complete = created.get("onComplete")
    if not isinstance(upload, dict) or not isinstance(complete, dict):
        raise CesiumIonError(f"Cesium ion asset {asset_id} did not provide upload instructions")
    _upload_bundle(config, upload, os.path.basename(bundle_path), body)
    method, url = complete.get("method"), complete.get("url")
    if not isinstance(method, str) or not isinstance(url, str) or not url:
        raise CesiumIonError(f"Cesium ion asset {asset_id} did not provide completion instructions")
    fields = complete.get("fields", {})
    if not isinstance(fields, dict):
        raise CesiumIonError(f"Cesium ion asset {asset_id} returned invalid completion fields")
    try:
        response = httpx.request(
            method, url, headers=_headers(config), json=fields, timeout=config["timeout_seconds"]
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise CesiumIonError(
            "Cesium ion upload completed storage transfer but asset "
            f"{asset_id} could not start processing"
        ) from exc
    return {"asset_id": asset_id, "status": metadata.get("status", "AWAITING_FILES")}
