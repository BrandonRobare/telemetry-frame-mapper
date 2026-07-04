from __future__ import annotations

import argparse
from pathlib import Path

import pytest

from drone_video_geotagger import cli
from drone_video_geotagger.exiftool import write_exif
from drone_video_geotagger.frames import FrameTag
from drone_video_geotagger.telemetry import TelemetryPoint
from drone_video_geotagger.video import extract_srt, read_video_start


def _tag(tmp_path: Path) -> FrameTag:
    frame = tmp_path / "frame_00001.jpg"
    frame.write_bytes(b"jpg")
    return FrameTag(
        source=frame,
        target=frame,
        frame_index=1,
        seconds=0.0,
        lat=35.0,
        lon=-80.0,
        rel_alt_m=10.0,
        abs_alt_m=110.0,
        timestamp=None,
    )


def test_extract_srt_missing_ffmpeg_reports_install_guidance(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="ffmpeg executable not found"):
        extract_srt("/missing/bin/ffmpeg", tmp_path / "flight.mp4", tmp_path / "flight.srt")


def test_read_video_start_missing_ffmpeg_reports_install_guidance(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="ffmpeg executable not found"):
        read_video_start("/missing/bin/ffmpeg", tmp_path / "flight.mp4")


def test_write_exif_missing_exiftool_reports_install_guidance(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="exiftool executable not found"):
        write_exif("/missing/bin/exiftool", [_tag(tmp_path)], tmp_path / "exif.args")


def test_cli_run_reads_video_start_from_video_argument(monkeypatch, tmp_path: Path) -> None:
    video = tmp_path / "flight.mp4"
    video.write_bytes(b"video")
    frames_dir = tmp_path / "frames"
    frames_dir.mkdir()
    srt = tmp_path / "flight.srt"
    srt.write_text("telemetry")

    seen: dict[str, Path] = {}

    def fake_read_video_start(ffmpeg: str, video_arg: Path):
        seen["ffmpeg"] = Path(ffmpeg)
        seen["video"] = video_arg
        return None

    monkeypatch.setattr(cli, "parse_srt", lambda path: [TelemetryPoint(0.0, 1.0, 2.0, 3.0, 4.0)])
    monkeypatch.setattr(cli, "collect_frames", lambda path: [(path / "frame_00001.jpg", 1)])
    monkeypatch.setattr(cli, "infer_frame_rate", lambda frames, end_s: 1.0)
    monkeypatch.setattr(cli, "read_video_start", fake_read_video_start)
    monkeypatch.setattr(cli, "build_frame_tags", lambda **kwargs: [])
    monkeypatch.setattr(cli, "copy_frames", lambda tags: None)
    monkeypatch.setattr(cli, "write_audit_csv", lambda tags, audit_csv: None)
    monkeypatch.setattr(cli, "write_exif", lambda exiftool, tags, exif_args: None)

    args = argparse.Namespace(
        video=video,
        frames=frames_dir,
        takeoff_altitude=10.0,
        output=tmp_path / "out",
        srt=srt,
        frame_rate=None,
        ffmpeg="ffmpeg",
        exiftool="exiftool",
        in_place=False,
    )

    assert cli.run(args) == 0
    assert seen["video"] == video
