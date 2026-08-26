from __future__ import annotations

import json
import math
from datetime import datetime
from pathlib import Path

import pytest

from drone_video_geotagger.exiftool import build_exiftool_args
from drone_video_geotagger.frames import FrameTag, build_frame_tags
from drone_video_geotagger.telemetry import parse_srt_text

FIXTURE_DIR = Path(__file__).parents[1] / "fixtures" / "omnisim_altitude_truth"


def _load_truth() -> dict:
    return json.loads((FIXTURE_DIR / "truth.json").read_text(encoding="utf-8"))


def _build_tags(srt_name: str, truth: dict) -> list[FrameTag]:
    telemetry = parse_srt_text((FIXTURE_DIR / srt_name).read_text(encoding="utf-8"))
    frames = [
        (Path(f"frames/frame_{frame['frame'] + 1:05d}.jpg"), frame["frame"] + 1)
        for frame in truth["frames"]
    ]
    video_start = datetime.fromisoformat(truth["frames"][0]["timestamp_utc"].replace("Z", "+00:00"))
    return build_frame_tags(
        frames=frames,
        telemetry=telemetry,
        output_dir=Path("geotagged"),
        frame_rate=1.0,
        takeoff_altitude_m=truth["takeoff_altitude_msl_m"],
        video_start=video_start,
    )


def test_absolute_and_relative_srt_variants_match_omnisim_truth() -> None:
    truth = _load_truth()
    absolute_tags = _build_tags("absolute_altitude.srt.txt", truth)
    relative_tags = _build_tags("relative_altitude.srt.txt", truth)

    for absolute_tag, relative_tag, expected in zip(
        absolute_tags, relative_tags, truth["frames"], strict=True
    ):
        assert absolute_tag.source == relative_tag.source
        assert absolute_tag.target == relative_tag.target
        assert absolute_tag.frame_index == relative_tag.frame_index
        assert absolute_tag.seconds == relative_tag.seconds
        assert absolute_tag.timestamp == relative_tag.timestamp
        assert absolute_tag.rel_alt_m == pytest.approx(relative_tag.rel_alt_m)
        assert absolute_tag.abs_alt_m == pytest.approx(relative_tag.abs_alt_m)
        assert absolute_tag.lat == pytest.approx(expected["latitude_deg"], abs=1e-12)
        assert absolute_tag.lon == pytest.approx(expected["longitude_deg"], abs=1e-12)
        assert absolute_tag.rel_alt_m == pytest.approx(expected["relative_altitude_m"])
        assert absolute_tag.abs_alt_m == pytest.approx(expected["absolute_altitude_msl_m"])
        assert (
            absolute_tag.timestamp.isoformat().replace("+00:00", "Z")
            == expected["timestamp_utc"]
        )

    first_args = build_exiftool_args([absolute_tags[0]])
    assert "-GPSAltitude=449.900" in first_args
    assert "-XMP-drone-dji:RelativeAltitude=+115.900" in first_args
    assert "-GPSAltitude=783.900" not in first_args


def test_altitude_fix_prevents_oversized_camera_footprint() -> None:
    truth = _load_truth()
    first = _build_tags("absolute_altitude.srt.txt", truth)[0]
    half_fov_rad = math.radians(truth["camera"]["field_of_view_horizontal_deg"] / 2.0)

    correct_width_m = 2.0 * first.rel_alt_m * math.tan(half_fov_rad)
    double_counted_width_m = 2.0 * first.abs_alt_m * math.tan(half_fov_rad)

    assert correct_width_m == pytest.approx(205.03, abs=0.05)
    assert double_counted_width_m / correct_width_m == pytest.approx(449.9 / 115.9)
    assert double_counted_width_m > correct_width_m * 3.8
