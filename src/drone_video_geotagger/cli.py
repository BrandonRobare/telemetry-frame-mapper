from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from drone_video_geotagger.audit import write_audit_csv
from drone_video_geotagger.exiftool import write_exif
from drone_video_geotagger.frames import build_frame_tags, collect_frames, infer_frame_rate
from drone_video_geotagger.telemetry import parse_srt
from drone_video_geotagger.video import extract_srt, read_video_start


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="drone-video-geotagger",
        description=(
            "Geotag extracted DJI video frames with GPS EXIF metadata for "
            "WebODM/OpenDroneMap processing."
        ),
    )
    parser.add_argument("--video", type=Path, required=True, help="Path to the source DJI video.")
    parser.add_argument(
        "--frames",
        type=Path,
        required=True,
        help="Folder of extracted JPG frames.",
    )
    parser.add_argument(
        "--takeoff-altitude",
        type=float,
        required=True,
        help="Takeoff altitude in meters above sea level.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Folder for geotagged copies. Defaults to '<frames>_geotagged'.",
    )
    parser.add_argument(
        "--srt",
        type=Path,
        help="Path to a DJI SRT telemetry file. If missing, the CLI extracts it from the video.",
    )
    parser.add_argument(
        "--frame-rate",
        type=float,
        help="Frame extraction rate in frames per second. If omitted, the CLI estimates it.",
    )
    parser.add_argument("--ffmpeg", default="ffmpeg", help="ffmpeg executable path.")
    parser.add_argument("--exiftool", default="exiftool", help="exiftool executable path.")
    parser.add_argument(
        "--in-place",
        action="store_true",
        help="Write EXIF tags into the frame folder instead of making geotagged copies.",
    )
    return parser


def copy_frames(tags) -> None:
    for tag in tags:
        tag.target.parent.mkdir(parents=True, exist_ok=True)
        if tag.source != tag.target:
            shutil.copy2(tag.source, tag.target)


def default_output_dir(frames_dir: Path) -> Path:
    return frames_dir.with_name(f"{frames_dir.name}_geotagged")


def resolve_srt_path(video: Path, output_dir: Path, requested_srt: Path | None) -> Path:
    if requested_srt:
        return requested_srt
    return output_dir / f"{video.stem}.srt"


def run(args: argparse.Namespace) -> int:
    output_dir = args.frames if args.in_place else args.output or default_output_dir(args.frames)
    srt_path = resolve_srt_path(args.video, output_dir, args.srt)

    if not srt_path.exists():
        extract_srt(args.ffmpeg, args.video, srt_path)

    telemetry = parse_srt(srt_path)
    frames = collect_frames(args.frames)
    frame_rate = args.frame_rate or infer_frame_rate(frames, telemetry[-1].end_s)
    video_start = read_video_start(args.ffmpeg, args.video)

    tags = build_frame_tags(
        frames=frames,
        telemetry=telemetry,
        output_dir=output_dir,
        frame_rate=frame_rate,
        takeoff_altitude_m=args.takeoff_altitude,
        video_start=video_start,
        in_place=args.in_place,
    )

    copy_frames(tags)
    audit_csv = output_dir / "frame_geotags.csv"
    exif_args = output_dir / "exiftool_geotags.args"
    write_audit_csv(tags, audit_csv)
    write_exif(args.exiftool, tags, exif_args)

    print(f"Frames tagged: {len(tags)}")
    print(f"Frame rate used: {frame_rate:g} fps")
    print(f"SRT points used: {len(telemetry)}")
    print(f"Output folder: {output_dir}")
    print(f"Audit CSV: {audit_csv}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return run(args)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
