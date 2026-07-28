from __future__ import annotations

import io
import sys

import pytest

from drone_video_geotagger.paths import force_utf8_streams


def test_force_utf8_streams_rescues_a_cp1252_stream(monkeypatch) -> None:
    """A redirected stream on Windows defaults to the ANSI code page.

    U+2192 is not representable in cp1252, and `dvg-pipeline` prints it in every
    plan line, so a redirected dry-run died with an unhandled UnicodeEncodeError.
    """
    stream = io.TextIOWrapper(io.BytesIO(), encoding="cp1252")
    monkeypatch.setattr(sys, "stdout", stream)

    with pytest.raises(UnicodeEncodeError):
        stream.write("extract SRT from a → b")
        stream.flush()

    force_utf8_streams()

    assert sys.stdout.encoding == "utf-8"
    sys.stdout.write("extract SRT from a → b")
    sys.stdout.flush()


@pytest.mark.parametrize("module_name", ["cli", "pipeline_cli"])
def test_every_console_entry_point_forces_utf8(monkeypatch, module_name: str) -> None:
    """Both console scripts must call it — pipeline_cli was originally missed."""
    import importlib

    module = importlib.import_module(f"drone_video_geotagger.{module_name}")
    called: list[bool] = []
    monkeypatch.setattr(module, "force_utf8_streams", lambda: called.append(True))

    with pytest.raises(SystemExit):
        module.main(["--help"])

    assert called == [True], f"{module_name}.main() did not call force_utf8_streams()"
