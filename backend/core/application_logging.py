from __future__ import annotations

import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

_HANDLER_MARKER = "telemetry_frame_mapper_application_log"
_LEVELS = {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG", "NOTSET"}
_DEFAULTS = {
    "enabled": True,
    "level": "INFO",
    "directory": "./logs",
    "filename": "backend.jsonl",
    "max_bytes": 10 * 1024 * 1024,
    "backup_count": 5,
}


class JsonFormatter(logging.Formatter):
    """Format backend records as one JSON object per line for local inspection."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def logging_config(data: dict, config_path: str = "config.yaml") -> dict:
    """Return validated local logging settings, resolving paths next to the config file."""
    configured = data.get("logging", {}) if isinstance(data, dict) else {}
    configured = configured if isinstance(configured, dict) else {}
    result = {**_DEFAULTS, **configured}
    result["enabled"] = bool(result["enabled"])

    level = str(result["level"]).upper()
    result["level"] = level if level in _LEVELS else _DEFAULTS["level"]
    try:
        result["max_bytes"] = max(1, int(result["max_bytes"]))
    except (TypeError, ValueError):
        result["max_bytes"] = _DEFAULTS["max_bytes"]
    try:
        result["backup_count"] = max(0, int(result["backup_count"]))
    except (TypeError, ValueError):
        result["backup_count"] = _DEFAULTS["backup_count"]

    filename = Path(str(result["filename"])).name
    result["filename"] = filename if filename not in ("", ".") else _DEFAULTS["filename"]
    directory = Path(str(result["directory"]))
    if not directory.is_absolute():
        directory = Path(config_path).resolve().parent / directory
    result["path"] = directory.resolve() / result["filename"]
    return result


def configure_application_logging(settings: dict) -> None:
    """Configure the ``backend`` logger with a single local rotating JSONL handler."""
    logger = logging.getLogger("backend")
    for handler in list(logger.handlers):
        if getattr(handler, _HANDLER_MARKER, False):
            logger.removeHandler(handler)
            handler.close()

    if not settings["enabled"]:
        return

    path = Path(settings["path"])
    path.parent.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        path,
        maxBytes=settings["max_bytes"],
        backupCount=settings["backup_count"],
        encoding="utf-8",
    )
    setattr(handler, _HANDLER_MARKER, True)
    handler.setFormatter(JsonFormatter())
    logger.addHandler(handler)
    logger.setLevel(settings["level"])
    logger.propagate = False
    logger.info("Application logging configured", extra={"log_path": str(path)})
