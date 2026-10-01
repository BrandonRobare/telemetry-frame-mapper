from __future__ import annotations

import csv
from datetime import UTC, datetime
from pathlib import Path

import pytest

from drone_video_geotagger import cli
from drone_video_geotagger.frames import (
    FrameTag,
    build_frame_tags,
    collect_frames,
    infer_frame_rate,
)
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
    start = datetime(2025, 8, 6, 18, 28, 47, tzinfo=UTC)

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
    assert tags[2].timestamp == datetime(2025, 8, 6, 18, 28, 48, tzinfo=UTC)


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

    assert infer_frame_rate(frames, telemetry_end_s=14.5, video_duration_s=14.5) == 8


def test_infer_frame_rate_rejects_telemetry_span_that_disagrees_with_video_timing() -> None:
    frames = [(Path(f"frame_{index:05d}.jpg"), index) for index in range(1, 802)]

    with pytest.raises(ValueError, match=r"telemetry.*--frame-rate"):
        infer_frame_rate(frames, telemetry_end_s=80, video_duration_s=100)


@pytest.mark.parametrize("telemetry_end_s", [0, -1.0])
def test_infer_frame_rate_requires_explicit_rate_without_telemetry_duration(
    telemetry_end_s: float,
) -> None:
    """No telemetry duration means no basis for a rate; never guess 8 fps (#948)."""
    frames = [(Path(f"frame_{index:05d}.jpg"), index) for index in range(1, 10)]

    with pytest.raises(ValueError, match="--frame-rate"):
        infer_frame_rate(frames, telemetry_end_s=telemetry_end_s)


def test_build_frame_tags_rejects_frames_after_telemetry_ends() -> None:
    frames = [(Path("frame_00001.jpg"), 1), (Path("frame_00003.jpg"), 3)]
    telemetry = [
        TelemetryPoint(0, 1, 41.0, -81.0, 100.0),
        TelemetryPoint(1, 2, 41.2, -80.8, 102.0),
    ]

    with pytest.raises(ValueError, match=r"telemetry ends.*complete telemetry"):
        build_frame_tags(
            frames=frames,
            telemetry=telemetry,
            output_dir=Path("geotagged"),
            frame_rate=1,
            takeoff_altitude_m=236.5,
            video_start=None,
        )


def test_infer_frame_rate_requires_explicit_rate_for_numbering_gaps() -> None:
    frames = [(Path("frame_00001.jpg"), 1), (Path("frame_00005.jpg"), 5)]

    with pytest.raises(ValueError, match="--frame-rate"):
        infer_frame_rate(frames, telemetry_end_s=1)


def test_collect_frames_uses_last_digit_group(tmp_path: Path) -> None:
    (tmp_path / "DJI_0081_frame_42.jpg").touch()
    (tmp_path / "DJI_0081_frame_43.jpg").touch()

    frames = collect_frames(tmp_path)

    assert [index for _, index in frames] == [42, 43]


def test_collect_frames_plain_frame_names(tmp_path: Path) -> None:
    (tmp_path / "frame_00042.jpg").touch()

    frames = collect_frames(tmp_path)

    assert frames == [(tmp_path / "frame_00042.jpg", 42)]


def test_collect_frames_accepts_jpeg_case_insensitive(tmp_path: Path) -> None:
    (tmp_path / "frame_00001.jpeg").touch()
    (tmp_path / "frame_00002.JPG").touch()

    frames = collect_frames(tmp_path)

    assert frames == [(tmp_path / "frame_00001.jpeg", 1), (tmp_path / "frame_00002.JPG", 2)]


def test_collect_frames_skips_files_without_digits(tmp_path: Path) -> None:
    (tmp_path / "cover.jpg").touch()
    (tmp_path / "frame_00001.jpg").touch()

    frames = collect_frames(tmp_path)

    assert frames == [(tmp_path / "frame_00001.jpg", 1)]


# ── Frame time is anchored to ffmpeg's start number (#948) ─────────────────


def _one_second_telemetry(seconds: int) -> list[TelemetryPoint]:
    """One fix per second, each at a distinct position, so a time shift changes the GPS."""
    return [
        TelemetryPoint(t, t + 1, 41.0 + t * 0.001, -81.0 - t * 0.001, 100.0 + t)
        for t in range(seconds)
    ]


def _tags_by_index(frames: list[tuple[Path, int]], **kwargs) -> dict[int, FrameTag]:
    tags = build_frame_tags(
        frames=frames,
        telemetry=_one_second_telemetry(31),
        output_dir=Path("geotagged"),
        frame_rate=1,
        takeoff_altitude_m=236.5,
        video_start=datetime(2025, 8, 6, 18, 28, 47, tzinfo=UTC),
        **kwargs,
    )
    return {tag.frame_index: tag for tag in tags}


def test_trimming_leading_frames_does_not_shift_remaining_geotags() -> None:
    """Deleting the take-off frames 1..20 must leave frames 21..30 where they were."""
    all_frames = [(Path(f"frames/frame_{index:05d}.jpg"), index) for index in range(1, 31)]
    trimmed = [frame for frame in all_frames if frame[1] > 20]

    full = _tags_by_index(all_frames)
    kept = _tags_by_index(trimmed)

    assert [kept[index].seconds for index in range(21, 31)] == list(range(20, 30))
    for index, tag in kept.items():
        reference = full[index]
        assert (tag.seconds, tag.lat, tag.lon, tag.rel_alt_m, tag.abs_alt_m, tag.timestamp) == (
            reference.seconds,
            reference.lat,
            reference.lon,
            reference.rel_alt_m,
            reference.abs_alt_m,
            reference.timestamp,
        )


def test_build_frame_tags_honours_a_zero_start_number() -> None:
    """Frames extracted with `ffmpeg -start_number 0` put frame 0 at t=0."""
    frames = [(Path(f"frames/frame_{index:05d}.jpg"), index) for index in (0, 1, 2)]

    tags = _tags_by_index(frames, start_number=0)

    assert [tags[index].seconds for index in (0, 1, 2)] == [0, 1, 2]


def test_build_frame_tags_rejects_frames_numbered_below_the_start_number() -> None:
    frames = [(Path(f"frames/frame_{index:05d}.jpg"), index) for index in (0, 1, 2)]

    with pytest.raises(ValueError, match=r"frame 0.*--start-number"):
        _tags_by_index(frames)


def test_build_frame_tags_rejects_a_negative_start_number() -> None:
    frames = [(Path("frames/frame_00001.jpg"), 1)]

    with pytest.raises(ValueError, match="start number"):
        _tags_by_index(frames, start_number=-1)


def test_infer_frame_rate_requires_explicit_rate_when_leading_frames_are_missing() -> None:
    """96 survivors of 116 frames look like 6.6 fps; guessing that would misplace them all."""
    trimmed = [(Path(f"frame_{index:05d}.jpg"), index) for index in range(21, 117)]

    with pytest.raises(ValueError, match=r"first frame is 21.*--frame-rate"):
        infer_frame_rate(trimmed, telemetry_end_s=14.5, video_duration_s=14.5)


def test_infer_frame_rate_honours_the_start_number() -> None:
    frames = [(Path(f"frame_{index:05d}.jpg"), index) for index in range(0, 116)]

    assert infer_frame_rate(frames, 14.5, video_duration_s=14.5, start_number=0) == 8


def test_cli_start_number_defaults_to_one_and_reaches_frame_timing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    frames_dir = tmp_path / "frames"
    frames_dir.mkdir()
    for index in (21, 22):
        (frames_dir / f"frame_{index:05d}.jpg").write_bytes(b"jpg")
    srt = tmp_path / "flight.srt"
    srt.write_text(
        "\n".join(
            f"{t + 1}\n00:00:{t:02d},000 --> 00:00:{t + 1:02d},000\n"
            f"GPS ({-81.0 - t * 0.001:.4f}, {41.0 + t * 0.001:.4f}, 24), H {100 + t}.00m\n"
            for t in range(30)
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(cli, "read_video_start", lambda *_: None)
    monkeypatch.setattr(cli, "write_exif", lambda exiftool, tags, args_path: None)

    def seconds_for(*extra: str) -> list[str]:
        out = tmp_path / f"out{len(extra)}"
        argv = ["--video", str(tmp_path / "flight.mp4"), "--frames", str(frames_dir)]
        argv += ["--takeoff-altitude", "10", "--srt", str(srt), "--frame-rate", "1"]
        assert cli.main([*argv, "--output", str(out), *extra]) == 0
        with (out / "frame_geotags.csv").open(encoding="utf-8") as file:
            return [row["seconds"] for row in csv.DictReader(file)]

    required = ["--video", "v", "--frames", "f", "--takeoff-altitude", "1"]
    assert cli.build_parser().parse_args(required).start_number == 1
    assert seconds_for() == ["20.000", "21.000"]
    assert seconds_for("--start-number", "0") == ["21.000", "22.000"]
