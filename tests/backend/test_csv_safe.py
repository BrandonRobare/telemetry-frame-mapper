"""Spreadsheet-formula injection guards for CSV exports (#863)."""

from __future__ import annotations

from backend.core.csv_safe import csv_safe


def test_csv_safe_neutralizes_formula_prefixes() -> None:
    evil = '=HYPERLINK("http://evil","x")'
    assert csv_safe(evil) == "'" + evil
    assert csv_safe("+1") == "'+1"
    assert csv_safe("-sum(A1:A2)") == "'-sum(A1:A2)"
    assert csv_safe("@cmd") == "'@cmd"
    assert csv_safe("\t=cmd") == "'\t=cmd"
    assert csv_safe("plain value") == "plain value"
    assert csv_safe(42) == "42"
    assert csv_safe(None) == ""


def test_control_point_csv_escapes_labels() -> None:
    from unittest.mock import patch

    from backend.services import georeferencing_workflows as gw

    point = type(
        "P", (), {"label": "=EVIL()", "latitude": 1.0, "longitude": 2.0, "altitude_m": 3.0}
    )()
    with patch.object(gw, "_validate_control_point", lambda *a, **k: None), patch.object(
        gw, "_validate_control_point_format", lambda *a, **k: None
    ):
        out = gw.render_control_point_csv([point], format="pix4d")
    assert out is not None
    assert "'=EVIL()" in out


def test_audit_csv_escapes_filenames(tmp_path) -> None:
    from pathlib import Path

    from drone_video_geotagger import audit
    from drone_video_geotagger.frames import FrameTag

    tag = FrameTag(
        source=Path("orig.jpg"),
        target=Path("=CMD.jpg"),
        frame_index=0,
        seconds=0.0,
        lat=0.0,
        lon=0.0,
        rel_alt_m=0.0,
        abs_alt_m=0.0,
        timestamp=None,
    )
    path = tmp_path / "audit.csv"
    audit.write_audit_csv([tag], path)
    text = path.read_text(encoding="utf-8")
    assert "'=CMD.jpg" in text