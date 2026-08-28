from __future__ import annotations

import argparse
import subprocess
from datetime import datetime
from pathlib import Path

import pytest

from drone_video_geotagger import cli
from drone_video_geotagger.exiftool import write_exif
from drone_video_geotagger.frames import FrameTag
from drone_video_geotagger.telemetry import TelemetryPoint
from drone_video_geotagger.video import extract_srt, read_video_duration, read_video_start


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


def test_extract_srt_selects_first_subtitle_stream(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """SRT extraction must select the subtitle track, not a hardcoded index (#685)."""
    seen: list[str] = []

    def fake_run(argv, **kwargs):
        seen.extend(argv)
        return subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr("drone_video_geotagger.video.subprocess.run", fake_run)

    extract_srt("ffmpeg", tmp_path / "flight.mp4", tmp_path / "flight.srt")

    assert "0:s:0" in seen
    assert "0:2" not in seen


def test_read_video_start_missing_ffmpeg_reports_install_guidance(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="ffmpeg executable not found"):
        read_video_start("/missing/bin/ffmpeg", tmp_path / "flight.mp4")


def test_write_exif_missing_exiftool_reports_install_guidance(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="exiftool executable not found"):
        write_exif("/missing/bin/exiftool", [_tag(tmp_path)], tmp_path / "exif.args")


def test_read_video_duration_parses_ffmpeg_output(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    output = "Duration: 00:01:40.125, start: 0.000000, bitrate: 42 kb/s"
    monkeypatch.setattr(
        "drone_video_geotagger.video.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 1, "", output),
    )

    assert read_video_duration("ffmpeg", tmp_path / "flight.mp4") == pytest.approx(100.125)


def test_read_video_duration_returns_none_when_ffmpeg_omits_duration(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        "drone_video_geotagger.video.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 1, "", ""),
    )

    assert read_video_duration("ffmpeg", tmp_path / "flight.mp4") is None


@pytest.mark.parametrize(
    ("creation_time", "expected"),
    [
        ("2024-06-01T12:00:00.000000-04:00", "2024-06-01T12:00:00-04:00"),
        ("2024-06-01T12:00:00.000000-0700", "2024-06-01T12:00:00-07:00"),
        ("2024-06-01 12:00:00.000000-04:00", "2024-06-01T12:00:00-04:00"),
    ],
)
def test_read_video_start_parses_ffmpeg_creation_time_offsets(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, creation_time: str, expected: str
) -> None:
    ffmpeg_output = f"""\
Input #0, mov,mp4,m4a,3gp,3g2,mj2, from 'flight.mp4':
  Metadata:
    creation_time   : {creation_time}
"""
    monkeypatch.setattr(
        "drone_video_geotagger.video.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 1, "", ffmpeg_output),
    )

    assert read_video_start("ffmpeg", tmp_path / "flight.mp4") == datetime.fromisoformat(expected)


def test_read_video_start_rejects_ffmpeg_creation_time_without_time_of_day(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    ffmpeg_output = "    creation_time   : 2024-06-01\n"
    monkeypatch.setattr(
        "drone_video_geotagger.video.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 1, "", ffmpeg_output),
    )

    with pytest.raises(ValueError, match="creation_time.*time of day"):
        read_video_start("ffmpeg", tmp_path / "flight.mp4")


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
    monkeypatch.setattr(cli, "infer_frame_rate", lambda frames, end_s, duration_s: 1.0)
    monkeypatch.setattr(cli, "read_video_duration", lambda *_: 1.0)
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
