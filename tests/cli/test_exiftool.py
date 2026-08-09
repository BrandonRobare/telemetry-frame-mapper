from __future__ import annotations

from datetime import UTC, datetime
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
        timestamp=datetime(2025, 8, 6, 18, 28, 47, tzinfo=UTC),
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


def test_build_exiftool_args_writes_relative_altitude() -> None:
    """Frames must carry height-above-launch, not just GPSAltitude (MSL).

    The backend sizes ground footprints from height above ground. It reads DJI's
    XMP RelativeAltitude when present and otherwise falls back to GPSAltitude,
    which is metres above sea level — so a frame tagged at a site 334 m above sea
    level was treated as flying 334 m higher than it was, making every footprint
    several times too large.
    """
    tag = FrameTag(
        source=Path("frames/frame_00001.jpg"),
        target=Path("geotagged/frame_00001.jpg"),
        frame_index=1,
        seconds=0,
        lat=41.1509,
        lon=-81.3382,
        rel_alt_m=115.9,
        abs_alt_m=449.9,
        timestamp=None,
    )

    args = build_exiftool_args([tag])

    assert "-XMP-drone-dji:RelativeAltitude=+115.900" in args
    assert "-GPSAltitude=449.900" in args


def test_write_exif_pipes_argfile_on_stdin(tmp_path: Path, monkeypatch) -> None:
    """The argfile must reach exiftool on stdin, never as a command-line path.

    On Windows a path crosses the ANSI argv boundary, which replaces characters
    outside the active code page with "?" before exiftool sees it. That loss is
    unrecoverable — `-charset filename=UTF8` cannot undo it — so any output
    directory with non-ASCII characters failed to geotag at all.
    """
    import subprocess

    from drone_video_geotagger.exiftool import write_exif

    tag = FrameTag(
        source=Path("frames/frame_00001.jpg"),
        target=tmp_path / "日本語" / "frame_00001.jpg",
        frame_index=1,
        seconds=0,
        lat=41.125,
        lon=-81.25,
        rel_alt_m=115.5,
        abs_alt_m=352.438,
        timestamp=None,
    )
    args_path = tmp_path / "日本語" / "args.txt"
    captured: dict[str, object] = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["input"] = kwargs.get("input")
        return subprocess.CompletedProcess(cmd, 0, b"", b"")

    monkeypatch.setattr(subprocess, "run", fake_run)
    write_exif("exiftool", [tag], args_path)

    assert captured["cmd"][1:] == ["-@", "-"], "argfile path must not be passed as an argument"
    assert isinstance(captured["input"], bytes), "argfile must be piped as bytes"
    assert "日本語".encode() in captured["input"]


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
