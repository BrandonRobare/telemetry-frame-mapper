from __future__ import annotations

import subprocess
from datetime import datetime, timezone
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
    utc_timestamp = timestamp.astimezone(timezone.utc)
    exif_time = utc_timestamp.strftime("%Y:%m:%d %H:%M:%S")
    gps_date = utc_timestamp.strftime("%Y:%m:%d")
    gps_time = utc_timestamp.strftime("%H:%M:%S.%f")[:-3]
    subsec = f"{int(utc_timestamp.microsecond / 1000):03d}"
    return exif_time, gps_date, gps_time, subsec


def build_exiftool_args(tags: list[FrameTag], exiftool: str | Path = "exiftool") -> list[str]:
    args: list[str] = []
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
                f"-GPSAltitude={tag.abs_alt_m:.3f}",
                "-GPSAltitudeRef=Above Sea Level",
                "-GPSMapDatum=WGS-84",
                "-Make=DJI",
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
    args_path.write_text("\n".join(build_exiftool_args(tags, exiftool)) + "\n", newline="\n")


def write_exif(exiftool: str | Path, tags: list[FrameTag], args_path: Path) -> None:
    write_exiftool_args_file(tags, args_path, exiftool)
    result = subprocess.run(
        [str(exiftool), "-@", external_file_arg(args_path, exiftool)],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"exiftool failed:\n{result.stdout}\n{result.stderr}")
