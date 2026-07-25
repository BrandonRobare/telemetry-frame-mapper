from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from drone_video_geotagger.exiftool import build_exiftool_args, write_exiftool_args_file
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
    assert any("frame_00001.jpg" in str(a) for a in args)


def test_write_exiftool_args_file_non_ascii_path(tmp_path: Path) -> None:
    tag = FrameTag(
        source=Path("frames/café_0001.jpg"),
        target=tmp_path / "café_0001.jpg",
        frame_index=1,
        seconds=0,
        lat=41.125,
        lon=-81.25,
        rel_alt_m=115.5,
        abs_alt_m=352.438,
        timestamp=None,
    )
    args_path = tmp_path / "args.txt"

    write_exiftool_args_file([tag], args_path)

    content = args_path.read_text(encoding="utf-8")
    assert "café_0001.jpg" in content
    assert content.startswith("-charset\nfilename=UTF8\n")


def test_external_file_arg_rejects_newline_in_path() -> None:
    """ExifTool's -@ argfile is one argument per line, so a newline in a filename
    injects options. ``-config`` loads a Perl file, i.e. code execution as the
    pipeline user, and frame paths come from directory contents (SD-card import)."""
    import pytest

    from drone_video_geotagger.paths import external_file_arg

    with pytest.raises(ValueError, match="newline"):
        external_file_arg(Path("frames/frame\n-config\n/tmp/evil.cfg\n001.jpg"), "exiftool")


def test_write_exiftool_args_file_rejects_injected_option(tmp_path: Path) -> None:
    tag = FrameTag(
        source=Path("frames/a.jpg"),
        target=tmp_path / "a\n-config\nevil.cfg\n.jpg",
        frame_index=1,
        seconds=0,
        lat=41.125,
        lon=-81.25,
        rel_alt_m=115.5,
        abs_alt_m=352.438,
        timestamp=None,
    )
    import pytest

    with pytest.raises(ValueError):
        write_exiftool_args_file([tag], tmp_path / "args.txt")
