from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from drone_video_geotagger.frames import build_frame_tags, infer_frame_rate
from drone_video_geotagger.telemetry import TelemetryPoint


def test_build_frame_tags_aligns_frames_and_adds_takeoff_altitude() -> None:
    frames = [
        (Path("frames/frame_00001.jpg"), 1),
        (Path("frames/frame_00002.jpg"), 2),
        (Path("frames/frame_00003.jpg"), 3),
    ]
    telemetry = [
        TelemetryPoint(0, 1, 41.0, -81.0, 100.0),
        TelemetryPoint(1, 2, 41.2, -80.8, 102.0),
    ]
    start = datetime(2025, 8, 6, 18, 28, 47, tzinfo=timezone.utc)

    tags = build_frame_tags(
        frames=frames,
        telemetry=telemetry,
        output_dir=Path("geotagged"),
        frame_rate=2,
        takeoff_altitude_m=236.5,
        video_start=start,
    )

    assert tags[0].seconds == 0
    assert tags[0].target == Path("geotagged/frame_00001.jpg")
    assert tags[0].abs_alt_m == pytest.approx(336.5)
    assert tags[1].seconds == pytest.approx(0.5)
    assert tags[1].lat == pytest.approx(41.1)
    assert tags[1].lon == pytest.approx(-80.9)
    assert tags[1].rel_alt_m == pytest.approx(101.0)
    assert tags[1].abs_alt_m == pytest.approx(337.5)
    assert tags[2].timestamp == datetime(2025, 8, 6, 18, 28, 48, tzinfo=timezone.utc)


def test_build_frame_tags_rejects_zero_frame_rate() -> None:
    with pytest.raises(ValueError, match="frame rate"):
        build_frame_tags(
            frames=[(Path("frames/frame_00001.jpg"), 1)],
            telemetry=[TelemetryPoint(0, 1, 41.0, -81.0, 100.0)],
            output_dir=Path("geotagged"),
            frame_rate=0,
            takeoff_altitude_m=236.5,
            video_start=None,
        )


def test_infer_frame_rate_uses_nearest_common_rate() -> None:
    frames = [(Path(f"frame_{index:05d}.jpg"), index) for index in range(1, 117)]

    assert infer_frame_rate(frames, telemetry_end_s=14.5) == 8
