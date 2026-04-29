from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from drone_video_geotagger.exiftool import build_exiftool_args
from drone_video_geotagger.frames import FrameTag


def test_build_exiftool_args_contains_gps_tags() -> None:
    tag = FrameTag(
        source=Path("frames/frame_00001.jpg"),
        target=Path("geotagged/frame_00001.jpg"),
        frame_index=1,
        seconds=0,
        lat=41.125,
        lon=-81.25,
        rel_alt_m=115.5,
        abs_alt_m=352.438,
        timestamp=datetime(2025, 8, 6, 18, 28, 47, tzinfo=timezone.utc),
    )

    args = build_exiftool_args([tag])

    assert "-GPSLatitude=41.12500000" in args
    assert "-GPSLatitudeRef=N" in args
    assert "-GPSLongitude=81.25000000" in args
    assert "-GPSLongitudeRef=W" in args
    assert "-GPSAltitude=352.438" in args
    assert "-DateTimeOriginal=2025:08:06 18:28:47" in args
    assert "geotagged/frame_00001.jpg" in args
