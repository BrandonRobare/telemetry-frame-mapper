# Drone Video Geotagger

Geotags DJI drone video frames with GPS EXIF metadata for WebODM/OpenDroneMap processing.

DJI videos can store GPS telemetry in an embedded subtitle track. Extracted still frames do not always keep that location data. This tool reads the DJI telemetry, lines it up with the extracted frame sequence, and writes GPS EXIF tags into the JPG files.

## Features

- Extracts DJI SRT telemetry from an MP4 with `ffmpeg`, or reads an existing `.srt` file.
- Interpolates latitude, longitude, and relative height for each extracted frame.
- Writes GPS EXIF tags with `exiftool`.
- Creates an audit CSV so you can inspect the frame timing and coordinates.
- Keeps raw videos, flight logs, and generated image folders out of git.

## Install

```bash
python -m pip install .
```

For development:

```bash
python -m pip install ".[dev]"
```

The CLI expects `ffmpeg` and `exiftool` on your PATH. You can also pass their paths with `--ffmpeg` and `--exiftool`.

## Usage

Extract frames from the video first:

```bash
ffmpeg -i flight.mp4 -vf fps=8 extracted/frame_%05d.jpg
```

Then geotag the extracted JPGs:

```bash
drone-video-geotagger \
  --video flight.mp4 \
  --frames extracted \
  --takeoff-altitude 236.94
```

The command writes geotagged copies to `extracted_geotagged/` by default.

If you already have the SRT telemetry:

```bash
drone-video-geotagger \
  --video flight.mp4 \
  --frames extracted \
  --srt flight.srt \
  --takeoff-altitude 236.94 \
  --frame-rate 8
```

## Inputs

- `--video`: Source DJI video.
- `--frames`: Folder of extracted JPG frames.
- `--takeoff-altitude`: Takeoff altitude in meters above sea level.
- `--srt`: Optional DJI SRT file. If you skip it, the CLI extracts the subtitle track from the video.
- `--frame-rate`: Optional frame extraction rate. If you skip it, the CLI estimates the rate from the frame count and SRT duration.

## Outputs

- Geotagged JPG files.
- `frame_geotags.csv` with frame index, time offset, latitude, longitude, relative height, GPS altitude, and timestamp.
- `exiftool_geotags.args`, the generated ExifTool argument file.

Upload the geotagged JPG folder to WebODM. WebODM reads the EXIF GPS tags during import.

## Privacy Notes

Do not commit real drone videos, FlightRecord files, extracted frames, SRT files, credentials, or generated geotagged images. The `.gitignore` blocks those files by default. Run `git status --short` before pushing.

## Tests

```bash
pytest
ruff check .
```

The tests use inline strings and temporary paths. They do not include real flight data.
