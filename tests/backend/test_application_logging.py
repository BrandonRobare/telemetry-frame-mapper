from __future__ import annotations

import json
import logging

from backend.core.application_logging import configure_application_logging, logging_config


def _configured_handler() -> logging.Handler:
    logger = logging.getLogger("backend")
    return next(
        handler
        for handler in logger.handlers
        if getattr(handler, "telemetry_frame_mapper_application_log", False)
    )


def test_logging_config_resolves_local_path_and_validates_values(tmp_path):
    settings = logging_config(
        {
            "logging": {
                "level": "not-a-level",
                "directory": "logs",
                "filename": "nested/backend.jsonl",
                "max_bytes": 0,
                "backup_count": -1,
            }
        },
        str(tmp_path / "config.yaml"),
    )

    assert settings["level"] == "INFO"
    assert settings["path"] == tmp_path / "logs" / "backend.jsonl"
    assert settings["max_bytes"] == 1
    assert settings["backup_count"] == 0


def test_application_logging_writes_json_lines_and_rotates(tmp_path):
    path = tmp_path / "logs" / "backend.jsonl"
    settings = {
        "enabled": True,
        "level": "INFO",
        "path": path,
        "max_bytes": 100,
        "backup_count": 1,
    }
    configure_application_logging(settings)
    logger = logging.getLogger("backend")
    logger.info("first log message")
    logger.info("second log message that triggers rotation")
    _configured_handler().flush()

    records = []
    for candidate in (path, path.with_name("backend.jsonl.1")):
        if candidate.exists():
            records.extend(
                json.loads(line) for line in candidate.read_text(encoding="utf-8").splitlines()
            )
    assert any(
        record["message"] == "second log message that triggers rotation" for record in records
    )
    assert all({"timestamp", "level", "logger", "message"} <= record.keys() for record in records)

    configure_application_logging({"enabled": False})
