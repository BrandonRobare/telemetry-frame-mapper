from __future__ import annotations

from pathlib import Path

import pytest

from drone_video_geotagger.exiftool import write_exif
from drone_video_geotagger.frames import FrameTag
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
