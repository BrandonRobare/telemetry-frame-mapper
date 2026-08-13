from __future__ import annotations

import argparse
import io
from pathlib import Path

import pytest

from drone_video_geotagger import cli
from drone_video_geotagger.cli import warn_gps_lock
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


def test_parse_srt_time_rejects_malformed_timecode() -> None:
    with pytest.raises(ValueError, match="Unrecognized SRT timecode: '12.34.56'"):
        parse_srt_time("12.34.56")


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


def test_parse_srt_text_reads_key_value_dji_format() -> None:
    points = parse_srt_text(
        """
1
00:00:00,000 --> 00:00:01,000
[latitude: 41.1000] [longitude: -81.1000] [rel_alt: 100.0]

2
00:00:01,000 --> 00:00:02,000
Lat: 41.2000 Lon: -81.0000 Alt: 102.0
"""
    )

    assert len(points) == 2
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


def test_parse_srt_text_preserves_leading_no_fix_for_cli_warning() -> None:
    points = parse_srt_text(
        """
1
00:00:00,000 --> 00:00:01,000
GPS (0.000000, 0.000000, 0)

2
00:00:01,000 --> 00:00:02,000
GPS (0.000000, 0.000000, 0)

3
00:00:02,000 --> 00:00:03,000
GPS (-81.1000, 41.1000, 100)

4
00:00:03,000 --> 00:00:04,000
GPS (-81.0000, 41.2000, 102)
"""
    )
    stream = io.StringIO()

    warn_gps_lock(points, stream=stream)

    assert [(point.start_s, point.lat, point.lon) for point in points[:2]] == [
        (0.0, 0.0, 0.0),
        (1.0, 0.0, 0.0),
    ]
    assert "WARNING:" in stream.getvalue()
    assert "(0, 0)" in stream.getvalue()


def test_interpolate_rejects_leading_no_fix_window_parsed_from_srt() -> None:
    points = parse_srt_text(
        """
1
00:00:00,000 --> 00:00:01,000
GPS (0.000000, 0.000000, 0)

2
00:00:01,000 --> 00:00:02,000
GPS (-81.1000, 41.1000, 100)

3
00:00:02,000 --> 00:00:03,000
GPS (-81.0000, 41.2000, 102)
"""
    )

    with pytest.raises(ValueError, match="no GPS fix"):
        interpolate(points, 0.5)


def test_interpolate_rejects_mid_flight_no_fix_window_parsed_from_srt() -> None:
    points = parse_srt_text(
        """
1
00:00:00,000 --> 00:00:01,000
GPS (-81.2000, 41.0000, 98)

2
00:00:01,000 --> 00:00:02,000
GPS (0.000000, 0.000000, 0)

3
00:00:02,000 --> 00:00:03,000
GPS (-81.0000, 41.2000, 102)
"""
    )

    with pytest.raises(ValueError, match="no GPS fix"):
        interpolate(points, 1.5)


def test_cli_run_reports_parser_warning_before_rejecting_no_fix_frame(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    srt = tmp_path / "flight.srt"
    srt.write_text(
        """1
00:00:00,000 --> 00:00:01,000
GPS (0.000000, 0.000000, 0)

2
00:00:01,000 --> 00:00:02,000
GPS (-81.1000, 41.1000, 100)

3
00:00:02,000 --> 00:00:03,000
GPS (-81.0000, 41.2000, 102)
"""
    )
    frame = tmp_path / "frame_00001.jpg"
    frame.touch()
    monkeypatch.setattr(cli, "collect_frames", lambda _: [(frame, 1)])
    monkeypatch.setattr(cli, "infer_frame_rate", lambda *_: 1.0)
    monkeypatch.setattr(cli, "read_video_duration", lambda *_: None)
    monkeypatch.setattr(cli, "read_video_start", lambda *_: None)

    args = argparse.Namespace(
        video=tmp_path / "flight.mp4",
        frames=tmp_path,
        takeoff_altitude=10.0,
        output=tmp_path / "out",
        srt=srt,
        frame_rate=None,
        ffmpeg="ffmpeg",
        exiftool="exiftool",
        in_place=False,
    )

    with pytest.raises(ValueError, match="no GPS fix"):
        cli.run(args)

    assert "WARNING:" in capsys.readouterr().err


def test_parse_srt_text_rejects_missing_gps() -> None:
    with pytest.raises(ValueError, match="Supported DJI formats"):
        parse_srt_text("1\n00:00:00,000 --> 00:00:01,000\nno gps")
