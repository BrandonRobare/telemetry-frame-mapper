from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from drone_video_geotagger.audit import write_audit_csv
from drone_video_geotagger.frames import FrameTag


def _tag(target: Path) -> FrameTag:
    return FrameTag(
        source=target,
        target=target,
        frame_index=1,
        seconds=0.0,
        lat=41.1509,
        lon=-81.3382,
        rel_alt_m=115.9,
        abs_alt_m=449.9,
        timestamp=datetime(2025, 8, 6, 18, 28, 47, tzinfo=UTC),
    )


def test_write_audit_csv_handles_non_ascii_paths(tmp_path):
    """Non-ASCII frame paths must not fall back to the locale codec (cp1252 on Windows).

    Regression for the sibling of #503: the exiftool args file was fixed to write
    UTF-8, but the audit CSV was not. Because write_audit_csv runs *before*
    write_exif, the crash aborted geotagging entirely on any non-ASCII output path.
    """
    out_dir = tmp_path / "frames_übung_日本語"
    csv_path = out_dir / "frame_geotags.csv"

    write_audit_csv([_tag(out_dir / "frame_00001.jpg")], csv_path)

    written = csv_path.read_text(encoding="utf-8")
    assert "übung_日本語" in written
    assert "449.900" in written
