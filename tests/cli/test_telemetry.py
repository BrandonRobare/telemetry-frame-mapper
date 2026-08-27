from __future__ import annotations

import argparse
import io
from pathlib import Path

import pytest

from drone_video_geotagger import cli, telemetry
from drone_video_geotagger.cli import warn_gps_lock
from drone_video_geotagger.frames import build_frame_tags
from drone_video_geotagger.telemetry import (
    interpolate,
    parse_srt_text,
    parse_srt_time,
    resolve_altitudes,
)

SRT_TEXT = """
1
00:00:00,000 --> 00:00:01,000
F/2.8, SS 1000, ISO 100, GPS (-81.1000, 41.1000, 24), D 10.0m, H 100.00m

2
00:00:01,000 --> 00:00:02,000
F/2.8, SS 1000, ISO 100, GPS (-81.0000, 41.2000, 24), D 11.0m, H 102.00m
"""


def _force_locale_codec(monkeypatch: pytest.MonkeyPatch, codec: str) -> None:
    """Decode encoding-less reads with `codec`, the way a non-UTF-8 locale box does."""
    real_read_text = Path.read_text

    def read_text(self: Path, encoding: str | None = None, *args: object, **kwargs: object) -> str:
        return real_read_text(self, encoding or codec, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", read_text)


def test_parse_srt_decodes_utf8_not_the_locale_codec(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A UTF-8 SRT must survive a cp1252 locale (#677).

    ``errors="ignore"`` turns the codec mismatch into silent character loss instead
    of a crash, so the only thing that shows it is the text the parser is handed.
    """
    srt_text = f"[Übung 日本語 Ёлка]{SRT_TEXT}"
    srt_path = tmp_path / "flight.SRT"
    srt_path.write_bytes(srt_text.encode())
    _force_locale_codec(monkeypatch, "cp1252")
    monkeypatch.setattr(telemetry, "parse_srt_text", lambda text: [text])

    assert telemetry.parse_srt(srt_path) == [srt_text]


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


def test_parse_srt_text_accepts_dji_longtitude_misspelling() -> None:
    points = parse_srt_text(
        """
1
00:00:00,000 --> 00:00:01,000
[latitude : 41.150900] [longtitude : -81.338200] [altitude: 449.900]

2
00:00:01,000 --> 00:00:02,000
[latitude : 41.151000] [longtitude : -81.338300] [altitude: 450.900]
"""
    )

    assert len(points) == 2
    assert points[0].lat == 41.1509
    assert points[0].lon == -81.3382
    assert points[0].rel_alt_m == 449.9
    assert points[1].lon == -81.3383


def test_bare_altitude_is_absolute_and_does_not_double_count_takeoff(tmp_path: Path) -> None:
    """A lone "altitude" field is metres above sea level, not height above launch (#675).

    449.9 m MSL from a 334 m launch pad is 115.9 m above launch. Read as relative it wrote
    RelativeAltitude=+449.900 and GPSAltitude=783.900 for the same frame, and that XMP tag
    is what the backend sizes ground footprints from.
    """
    points = parse_srt_text(
        """
1
00:00:00,000 --> 00:00:01,000
[latitude : 41.1509] [longitude : -81.3382] [altitude: 449.900]

2
00:00:01,000 --> 00:00:02,000
[latitude : 41.1510] [longitude : -81.3383] [altitude: 449.900]
"""
    )

    assert points[0].abs_alt_m == 449.9

    with pytest.warns(UserWarning, match="only an absolute altitude"):
        tags = build_frame_tags(
            frames=[(Path("frames/frame_00001.jpg"), 1)],
            telemetry=points,
            output_dir=tmp_path,
            frame_rate=1,
            takeoff_altitude_m=334.0,
            video_start=None,
        )

    assert tags[0].rel_alt_m == pytest.approx(115.9)
    assert tags[0].abs_alt_m == pytest.approx(449.9)


def test_explicit_relative_altitude_is_never_reinterpreted() -> None:
    """rel_alt wins over a bare altitude on the same line, and is left alone (#675)."""
    points = parse_srt_text(
        """
1
00:00:00,000 --> 00:00:01,000
[latitude: 41.1000] [longitude: -81.1000] [rel_alt: 100.0] [altitude: 434.0]

2
00:00:01,000 --> 00:00:02,000
[latitude: 41.2000] [longitude: -81.2000] [rel_alt: 102.0] [altitude: 436.0]
"""
    )

    assert [point.rel_alt_m for point in points] == [100.0, 102.0]
    assert [point.abs_alt_m for point in points] == [None, None]
    assert resolve_altitudes(points, 334.0) == points


def test_parse_srt_text_warns_about_blocks_with_a_partial_fix() -> None:
    with pytest.warns(UserWarning, match="1 SRT block"):
        points = parse_srt_text(
            """
1
00:00:00,000 --> 00:00:01,000
[latitude: 41.1000] [longitude: -81.1000] [rel_alt: 100.0]

2
00:00:01,000 --> 00:00:02,000
[latitude: 41.2000] [rel_alt: 102.0]

3
00:00:02,000 --> 00:00:03,000
[latitude: 41.3000] [longitude: -81.3000] [rel_alt: 104.0]
"""
        )

    assert [point.lat for point in points] == [41.1, 41.3]


def test_parse_srt_text_error_distinguishes_unrecognized_gps_shape() -> None:
    with pytest.raises(ValueError, match="not in a recognized shape.*Supported DJI formats"):
        parse_srt_text(
            """
1
00:00:00,000 --> 00:00:01,000
[latitude: 41.1000] [rel_alt: 100.0]

2
00:00:01,000 --> 00:00:02,000
[latitude: 41.2000] [rel_alt: 102.0]
"""
        )


def test_parse_srt_text_error_reports_no_gps_lines_found() -> None:
    with pytest.raises(ValueError, match="no GPS lines were found.*Supported DJI formats"):
        parse_srt_text("1\n00:00:00,000 --> 00:00:01,000\nno gps")
