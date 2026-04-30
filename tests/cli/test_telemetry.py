from __future__ import annotations

import pytest

from drone_video_geotagger.telemetry import (
    interpolate,
    parse_srt_text,
    parse_srt_time,
)

SRT_TEXT = """
1
00:00:00,000 --> 00:00:01,000
F/2.8, SS 1000, ISO 100, GPS (-81.1000, 41.1000, 24), D 10.0m, H 100.00m

2
00:00:01,000 --> 00:00:02,000
F/2.8, SS 1000, ISO 100, GPS (-81.0000, 41.2000, 24), D 11.0m, H 102.00m
"""


def test_parse_srt_time() -> None:
    assert parse_srt_time("00:01:02,125") == pytest.approx(62.125)


def test_parse_srt_text_reads_gps_and_height() -> None:
    points = parse_srt_text(SRT_TEXT)

    assert len(points) == 2
    assert points[0].start_s == 0
    assert points[0].end_s == 1
    assert points[0].lat == 41.1
    assert points[0].lon == -81.1
    assert points[0].rel_alt_m == 100
    assert points[1].lat == 41.2
    assert points[1].lon == -81.0
    assert points[1].rel_alt_m == 102


def test_interpolate_between_srt_points() -> None:
    points = parse_srt_text(SRT_TEXT)

    lat, lon, rel_alt = interpolate(points, 0.5)

    assert lat == pytest.approx(41.15)
    assert lon == pytest.approx(-81.05)
    assert rel_alt == pytest.approx(101)


def test_parse_srt_text_rejects_missing_gps() -> None:
    with pytest.raises(ValueError, match="Not enough GPS telemetry"):
        parse_srt_text("1\n00:00:00,000 --> 00:00:01,000\nno gps")
