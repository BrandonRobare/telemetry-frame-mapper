from __future__ import annotations

import csv
from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

from drone_video_geotagger.audit import write_audit_csv
from drone_video_geotagger.exiftool import timestamp_values
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


def test_audit_csv_utc_timestamp_matches_exif_for_offset_timestamp(tmp_path):
    """The utc_timestamp column must be UTC and agree with the EXIF tags (#679).

    FrameTag.timestamp keeps whatever offset read_video_start parsed, but
    timestamp_values converts to UTC before formatting DateTimeOriginal and
    GPSTimeStamp, so the CSV was off by the offset for any non-zero-offset video.
    """
    target = tmp_path / "frame_00001.jpg"
    berlin = timezone(timedelta(hours=2))
    tag = replace(_tag(target), timestamp=datetime(2024, 6, 1, 12, 0, 0, tzinfo=berlin))
    csv_path = tmp_path / "frame_geotags.csv"

    write_audit_csv([tag], csv_path)

    with csv_path.open(encoding="utf-8") as file:
        row = next(csv.DictReader(file))
    written = datetime.fromisoformat(row["utc_timestamp"])

    exif_time, gps_date, gps_time, _ = timestamp_values(tag.timestamp)
    assert written.utcoffset() == timedelta(0)
    assert written.strftime("%Y:%m:%d %H:%M:%S") == exif_time
    assert written.strftime("%Y:%m:%d") == gps_date
    assert written.strftime("%H:%M:%S.%f")[:-3] == gps_time
    assert row["utc_timestamp"] == "2024-06-01T10:00:00+00:00"
