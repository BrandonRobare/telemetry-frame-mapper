from __future__ import annotations

import subprocess
from datetime import UTC, datetime
from pathlib import Path

from drone_video_geotagger.frames import FrameTag
from drone_video_geotagger.paths import external_file_arg


def gps_ref(value: float, positive: str, negative: str) -> str:
    return positive if value >= 0 else negative


def timestamp_values(
    timestamp: datetime | None,
) -> tuple[str | None, str | None, str | None, str | None]:
    if timestamp is None:
        return None, None, None, None
    utc_timestamp = timestamp.astimezone(UTC)
    exif_time = utc_timestamp.strftime("%Y:%m:%d %H:%M:%S")
    gps_date = utc_timestamp.strftime("%Y:%m:%d")
    gps_time = utc_timestamp.strftime("%H:%M:%S.%f")[:-3]
    subsec = f"{int(utc_timestamp.microsecond / 1000):03d}"
    return exif_time, gps_date, gps_time, subsec


def build_exiftool_args(tags: list[FrameTag], exiftool: str | Path = "exiftool") -> list[str]:
    args: list[str] = ["-charset", "filename=UTF8"]
    for tag in tags:
        exif_time, gps_date, gps_time, subsec = timestamp_values(tag.timestamp)
        args.extend(
            [
                "-overwrite_original",
                "-P",
                "-q",
                "-q",
                f"-GPSLatitude={abs(tag.lat):.8f}",
                f"-GPSLatitudeRef={gps_ref(tag.lat, 'N', 'S')}",
                f"-GPSLongitude={abs(tag.lon):.8f}",
                f"-GPSLongitudeRef={gps_ref(tag.lon, 'E', 'W')}",
                f"-GPSAltitude={abs(tag.abs_alt_m):.3f}",
                f"-GPSAltitudeRef={gps_ref(tag.abs_alt_m, 'Above Sea Level', 'Below Sea Level')}",
                "-GPSMapDatum=WGS-84",
                "-Make=DJI",
                # Height above the launch point, matching what a DJI still writes.
                # GPSAltitude alone is metres above sea level, and the backend sizes
                # ground footprints from height above ground: without this tag a
                # video-derived frame is treated as flying at its MSL altitude, which
                # made footprints several times too large on any non-zero terrain.
                f"-XMP-drone-dji:RelativeAltitude={tag.rel_alt_m:+.3f}",
            ]
        )
        if exif_time and gps_date and gps_time and subsec:
            args.extend(
                [
                    f"-DateTimeOriginal={exif_time}",
                    f"-CreateDate={exif_time}",
                    f"-SubSecTimeOriginal={subsec}",
                    f"-GPSDateStamp={gps_date}",
                    f"-GPSTimeStamp={gps_time}",
                ]
            )
        args.extend([external_file_arg(tag.target, exiftool), "-execute"])
    return args


def write_exiftool_args_file(
    tags: list[FrameTag], args_path: Path, exiftool: str | Path = "exiftool"
) -> None:
    args_path.parent.mkdir(parents=True, exist_ok=True)
    args_path.write_text(
        "\n".join(build_exiftool_args(tags, exiftool)) + "\n", encoding="utf-8", newline="\n"
    )


def write_exif(exiftool: str | Path, tags: list[FrameTag], args_path: Path) -> None:
    write_exiftool_args_file(tags, args_path, exiftool)
    # The args file is piped in on stdin rather than referenced with `-@ <path>`.
    # A path on the command line crosses the Windows ANSI argv boundary, which
    # replaces anything outside the active code page with "?" before exiftool
    # ever sees it — unrecoverable, and `-charset filename=UTF8` cannot undo it.
    # Frame paths *inside* the file are covered by the in-file -charset directive.
    args_bytes = args_path.read_bytes()
    try:
        result = subprocess.run(
            [str(exiftool), "-@", "-"],
            input=args_bytes,
            capture_output=True,
            check=False,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(
            "exiftool executable not found: "
            f"{exiftool}. Install ExifTool or pass --exiftool /path/to/exiftool."
        ) from exc
    if result.returncode != 0:
        stdout = result.stdout.decode("utf-8", "replace")
        stderr = result.stderr.decode("utf-8", "replace")
        raise RuntimeError(f"exiftool failed:\n{stdout}\n{stderr}")
