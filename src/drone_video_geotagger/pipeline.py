"""Headless pipeline orchestrator for batch telemetry-frame-mapper jobs.

Accepts a YAML job spec and runs geotag → ingest → coverage → reconstruction → export
without a FastAPI server or browser.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

import yaml

from drone_video_geotagger.audit import write_audit_csv
from drone_video_geotagger.exiftool import write_exif
from drone_video_geotagger.frames import build_frame_tags, collect_frames, infer_frame_rate
from drone_video_geotagger.telemetry import parse_srt
from drone_video_geotagger.video import extract_srt, read_video_start

logger = logging.getLogger("dvg-pipeline")


# ── Models ──────────────────────────────────────────────────────────────────


class StepKind(StrEnum):
    GEOTAG = "geotag"
    INGEST = "ingest"
    COVERAGE = "coverage"
    RECONSTRUCTION = "reconstruction"
    EXPORT = "export"


class ReconstructionPreset(StrEnum):
    """Reconstruction presets, named to match config.yaml and the backend.

    These were once "sparse"/"dense", which matched nothing else in the project —
    config.yaml, the REST API, and every user-facing doc say quick/full.
    """

    QUICK = "quick"
    FULL = "full"


class ExportFormat(StrEnum):
    WEBODM_PACKAGE = "webodm_package"
    GEOREFERENCING_CSV = "georeferencing_csv"
    SHARE_BUNDLE = "share_bundle"
    REPRODUCIBILITY_MANIFEST = "reproducibility_manifest"


@dataclass
class GeotagSpec:
    video: Path
    frames: Path
    takeoff_altitude: float
    output: Path | None = None
    srt: Path | None = None
    frame_rate: float | None = None
    ffmpeg: str = "ffmpeg"
    exiftool: str = "exiftool"
    in_place: bool = False

    def __post_init__(self) -> None:
        self.video = Path(self.video)
        self.frames = Path(self.frames)
        if self.output is not None:
            self.output = Path(self.output)
        if self.srt is not None:
            self.srt = Path(self.srt)


@dataclass
class IngestSpec:
    source_dir: Path

    def __post_init__(self) -> None:
        self.source_dir = Path(self.source_dir)


@dataclass
class CoverageSpec:
    target_geojson: str  # raw GeoJSON string
    # Flown footprints to measure the target against, each a raw GeoJSON string.
    # ponytail: inline GeoJSON only; read them from an ingested session when the
    # headless pipeline gains a database.
    footprints: list[str] = field(default_factory=list)


@dataclass
class ReconstructionSpec:
    preset: ReconstructionPreset = ReconstructionPreset.QUICK
    session_id: int | None = None  # if already ingested


@dataclass
class ExportSpec:
    format: ExportFormat
    session_id: int | None = None
    reconstruction_id: int | None = None
    options: dict[str, Any] = field(default_factory=dict)


@dataclass
class StepSpec:
    kind: StepKind
    geotag: GeotagSpec | None = None
    ingest: IngestSpec | None = None
    coverage: CoverageSpec | None = None
    reconstruction: ReconstructionSpec | None = None
    export: ExportSpec | None = None


@dataclass
class JobSpec:
    """A complete batch pipeline job specification."""

    name: str
    steps: list[StepSpec]
    output_root: Path = Path("./pipeline_output")
    log_dir: Path | None = None

    def __post_init__(self) -> None:
        self.output_root = Path(self.output_root)
        if self.log_dir is not None:
            self.log_dir = Path(self.log_dir)


# ── Step runners ────────────────────────────────────────────────────────────


def _default_output_dir(frames_dir: Path) -> Path:
    return frames_dir.with_name(f"{frames_dir.name}_geotagged")


def _resolve_srt_path(video: Path, output_dir: Path, requested_srt: Path | None) -> Path:
    if requested_srt:
        return requested_srt
    return output_dir / f"{video.stem}.srt"


def _run_geotag(spec: GeotagSpec, dry_run: bool) -> str:
    """Execute the geotag step. Returns the output directory path."""
    import shutil as _shutil

    output_dir = (
        spec.frames if spec.in_place else spec.output or _default_output_dir(spec.frames)
    )
    srt_path = _resolve_srt_path(spec.video, output_dir, spec.srt)

    # Collect frames (handle missing/empty dir gracefully)
    try:
        frames = collect_frames(spec.frames)
    except (FileNotFoundError, ValueError):
        if dry_run:
            steps = [f"  frames: {spec.frames} (no JPEG frames found — would fail in live run)"]
            return "\n".join(steps)
        raise

    if dry_run:
        steps = []
        if not srt_path.exists():
            steps.append(f"  extract SRT from {spec.video} → {srt_path}")
        steps.extend(
            [
                f"  parse {len(frames)} frames from {spec.frames}",
                f"  build frame tags → {output_dir}",
                f"  write EXIF tags via {spec.exiftool}",
                f"  write audit CSV → {output_dir / 'frame_geotags.csv'}",
            ]
        )
        return "\n".join(steps)

    if not srt_path.exists():
        extract_srt(spec.ffmpeg, spec.video, srt_path)

    telemetry = parse_srt(srt_path)
    frames = collect_frames(spec.frames)
    frame_rate = spec.frame_rate or infer_frame_rate(frames, telemetry[-1].end_s)
    video_start = read_video_start(spec.ffmpeg, spec.video)

    tags = build_frame_tags(
        frames=frames,
        telemetry=telemetry,
        output_dir=output_dir,
        frame_rate=frame_rate,
        takeoff_altitude_m=spec.takeoff_altitude,
        video_start=video_start,
        in_place=spec.in_place,
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    for tag in tags:
        tag.target.parent.mkdir(parents=True, exist_ok=True)
        if tag.source != tag.target:
            _shutil.copy2(tag.source, tag.target)

    audit_csv = output_dir / "frame_geotags.csv"
    exif_args = output_dir / "exiftool_geotags.args"
    write_audit_csv(tags, audit_csv)
    write_exif(spec.exiftool, tags, exif_args)

    return str(output_dir)


_INGEST_HEADER = "  validation only (no images imported)"


def _run_ingest(spec: IngestSpec, dry_run: bool, *, output_root: Path) -> str:
    """Check that every JPEG in the source directory carries GPS EXIF.

    This does not import anything into a session — it is a validation summary, and
    reports itself as one so automation is not told an import happened.
    """
    source_dir = spec.source_dir
    jpegs = sorted(
        p for p in source_dir.iterdir() if p.is_file() and p.suffix.lower() in {".jpg", ".jpeg"}
    )
    if not jpegs:
        raise ValueError(f"No JPEG files found in {source_dir}")

    if dry_run:
        return "\n".join(
            [
                _INGEST_HEADER,
                f"  source_dir: {source_dir}",
                f"  would check {len(jpegs)} JPEGs for GPS EXIF",
            ]
        )

    try:
        import piexif
    except ModuleNotFoundError as exc:
        if exc.name == "piexif":
            raise RuntimeError(
                "The ingest step requires the piexif dependency; "
                "install it with `pip install piexif`."
            ) from exc
        raise

    valid = 0
    no_gps = 0
    for jpg in jpegs:
        # Lightweight check: look for GPS EXIF via piexif.
        try:
            exif_dict = piexif.load(str(jpg))
        except piexif.InvalidImageDataError:
            no_gps += 1
            continue

        gps = exif_dict.get("GPS", {})
        if gps:
            valid += 1
        else:
            no_gps += 1

    ingest_log = output_root / "ingest_validation.json"
    ingest_log.parent.mkdir(parents=True, exist_ok=True)
    ingest_log.write_text(
        json.dumps(
            {
                "mode": "validation",
                "source_dir": str(source_dir),
                "total": len(jpegs),
                "gps_valid": valid,
                "gps_missing": no_gps,
                "timestamp": datetime.now(UTC).isoformat(),
            },
            indent=2,
        )
    )
    logger.info(
        "Ingest validation written to %s (total=%d, valid=%d)", ingest_log, len(jpegs), valid
    )

    return "\n".join(
        [
            _INGEST_HEADER,
            f"  source_dir: {source_dir}",
            f"  total JPEGs: {len(jpegs)}",
            f"  GPS valid: {valid}",
            f"  GPS missing: {no_gps}",
        ]
    )


def _run_coverage(spec: CoverageSpec, dry_run: bool, *, output_root: Path) -> str:
    """Compute coverage from a set of footprint GeoJSON strings."""
    if dry_run:
        return (
            f"  target_geojson present: {bool(spec.target_geojson)}\n"
            f"  footprints: {len(spec.footprints)}"
        )

    if not spec.footprints:
        raise ValueError(
            "The coverage step needs at least one flown footprint: add a 'footprints' "
            "list of GeoJSON polygons to the step. Measuring a target against no "
            "footprints only ever reports 0% coverage."
        )

    from backend.services.coverage import run_coverage

    result = run_coverage(spec.footprints, spec.target_geojson)
    cov_log = output_root / "coverage_summary.json"
    cov_log.parent.mkdir(parents=True, exist_ok=True)
    cov_log.write_text(json.dumps(result, indent=2))

    return (
        f"  coverage_pct: {result['coverage_pct']}%  "
        f"covered_area_m2: {result['covered_area_m2']}"
    )


def _run_reconstruction(spec: ReconstructionSpec, dry_run: bool, *, output_root: Path) -> str:
    if dry_run:
        return f"  preset: {spec.preset.value}  (NOT RUNNABLE HEADLESS — a real run fails here)"
    raise NotImplementedError(
        "The reconstruction step cannot run headlessly: it needs COLMAP/gsplat and a "
        "configured database. Start the reconstruction from the app, or drop the step "
        "from the job spec."
    )


def _run_export(spec: ExportSpec, dry_run: bool, *, output_root: Path) -> str:
    if dry_run:
        return f"  format: {spec.format.value}  (NOT RUNNABLE HEADLESS — a real run fails here)"
    raise NotImplementedError(
        "The export step cannot run headlessly: it needs a backend session to export "
        "from. Export from the app, or drop the step from the job spec."
    )


# ── YAML parsing ────────────────────────────────────────────────────────────


def _parse_geotag(raw: dict) -> GeotagSpec:
    geotag = raw.get("geotag", raw)
    return GeotagSpec(
        video=Path(geotag["video"]),
        frames=Path(geotag["frames"]),
        takeoff_altitude=float(geotag["takeoff_altitude"]),
        output=Path(geotag["output"]) if "output" in geotag else None,
        srt=Path(geotag["srt"]) if "srt" in geotag else None,
        frame_rate=float(geotag["frame_rate"]) if "frame_rate" in geotag else None,
        ffmpeg=geotag.get("ffmpeg", "ffmpeg"),
        exiftool=geotag.get("exiftool", "exiftool"),
        in_place=bool(geotag.get("in_place", False)),
    )


def _parse_ingest(raw: dict) -> IngestSpec:
    ingest = raw.get("ingest", raw)
    return IngestSpec(source_dir=Path(ingest["source_dir"]))


def _parse_coverage(raw: dict) -> CoverageSpec:
    coverage = raw.get("coverage", raw)
    return CoverageSpec(
        target_geojson=coverage["target_geojson"],
        footprints=list(coverage.get("footprints", [])),
    )


def _parse_reconstruction(raw: dict) -> ReconstructionSpec:
    rec = raw.get("reconstruction", raw)
    return ReconstructionSpec(
        preset=ReconstructionPreset(rec.get("preset", "quick")),
        session_id=rec.get("session_id"),
    )


def _parse_export(raw: dict) -> ExportSpec:
    export = raw.get("export", raw)
    return ExportSpec(
        format=ExportFormat(export["format"]),
        session_id=export.get("session_id"),
        reconstruction_id=export.get("reconstruction_id"),
        options=export.get("options", {}),
    )


_STEP_PARSERS = {
    StepKind.GEOTAG: _parse_geotag,
    StepKind.INGEST: _parse_ingest,
    StepKind.COVERAGE: _parse_coverage,
    StepKind.RECONSTRUCTION: _parse_reconstruction,
    StepKind.EXPORT: _parse_export,
}


def parse_job_spec(yaml_path: Path) -> JobSpec:
    """Parse a pipeline job YAML file into a JobSpec."""
    text = yaml_path.read_text()
    raw = yaml.safe_load(text)

    if not isinstance(raw, dict):
        raise ValueError("Job spec must be a YAML mapping")

    name = raw.get("name", yaml_path.stem)
    output_root = Path(raw.get("output_root", "./pipeline_output"))
    log_dir = Path(raw["log_dir"]) if "log_dir" in raw else None

    raw_steps = raw.get("steps") or []
    if not raw_steps:
        raise ValueError("Job spec must define at least one step")

    steps: list[StepSpec] = []
    for i, step_raw in enumerate(raw_steps):
        kind_raw = step_raw.get("kind")
        if kind_raw is None:
            raise ValueError(f"Step {i}: missing 'kind' field")
        try:
            kind = StepKind(kind_raw)
        except ValueError:
            raise ValueError(f"Step {i}: unknown step kind {kind_raw!r}") from None

        parser = _STEP_PARSERS.get(kind)
        if parser is None:
            raise ValueError(f"Step {i}: no parser for step kind {kind.value}")
        parsed = parser(step_raw)

        step = StepSpec(kind=kind)
        if kind == StepKind.GEOTAG:
            step.geotag = parsed
        elif kind == StepKind.INGEST:
            step.ingest = parsed
        elif kind == StepKind.COVERAGE:
            step.coverage = parsed
        elif kind == StepKind.RECONSTRUCTION:
            step.reconstruction = parsed
        elif kind == StepKind.EXPORT:
            step.export = parsed

        steps.append(step)

    return JobSpec(name=name, steps=steps, output_root=output_root, log_dir=log_dir)


# ── Orchestrator ────────────────────────────────────────────────────────────


@dataclass
class StepResult:
    step_index: int
    kind: StepKind
    success: bool
    output: str
    error: str = ""


@dataclass
class PipelineResult:
    name: str
    steps: list[StepResult]
    started_at: datetime
    finished_at: datetime
    dry_run: bool

    @property
    def success(self) -> bool:
        # `all([])` is True: a run that executed no steps has not succeeded at anything.
        return bool(self.steps) and all(s.success for s in self.steps)

    @property
    def exit_code(self) -> int:
        return 0 if self.success else 1


_STEP_RUNNERS = {
    StepKind.GEOTAG: lambda spec, dry_run, output_root: _run_geotag(spec, dry_run),
    StepKind.INGEST: lambda spec, dry_run, output_root: _run_ingest(
        spec, dry_run, output_root=output_root
    ),
    StepKind.COVERAGE: lambda spec, dry_run, output_root: _run_coverage(
        spec, dry_run, output_root=output_root
    ),
    StepKind.RECONSTRUCTION: lambda spec, dry_run, output_root: _run_reconstruction(
        spec, dry_run, output_root=output_root
    ),
    StepKind.EXPORT: lambda spec, dry_run, output_root: _run_export(
        spec, dry_run, output_root=output_root
    ),
}


def _run_step(step: StepSpec, dry_run: bool, output_root: Path) -> str:
    """Run one step, or raise. Never returns a string that stands in for a failure."""
    runner = _STEP_RUNNERS.get(step.kind)
    if runner is None:
        raise ValueError(f"Unsupported step kind: {step.kind.value}")
    # StepSpec's per-kind fields are named after the StepKind values.
    spec = getattr(step, step.kind.value)
    if spec is None:
        raise ValueError(f"Step of kind {step.kind.value} is missing its '{step.kind.value}' spec")
    return runner(spec, dry_run, output_root)


class PipelineRunner:
    """Orchestrate a JobSpec through its steps."""

    def __init__(self, job: JobSpec) -> None:
        self.job = job

    def _ensure_output_dirs(self) -> None:
        self.job.output_root.mkdir(parents=True, exist_ok=True)
        log_dir = self.job.log_dir or (self.job.output_root / "logs")
        log_dir.mkdir(parents=True, exist_ok=True)

    def run(self, dry_run: bool = False) -> PipelineResult:
        started_at = datetime.now(UTC)
        results: list[StepResult] = []

        if not dry_run:
            # A dry run must leave the filesystem exactly as it found it.
            self._ensure_output_dirs()

        for i, step in enumerate(self.job.steps):
            try:
                output = _run_step(step, dry_run, self.job.output_root)
                results.append(StepResult(i, step.kind, True, output))
            except Exception as exc:
                if not isinstance(exc, NotImplementedError):
                    # A step that cannot run headlessly is an expected outcome, not a
                    # crash: it gets the same failed StepResult, but no traceback.
                    logger.exception("Step %d (%s) failed", i, step.kind.value)
                results.append(StepResult(i, step.kind, False, "", str(exc)))

        finished_at = datetime.now(UTC)
        return PipelineResult(
            name=self.job.name,
            steps=results,
            started_at=started_at,
            finished_at=finished_at,
            dry_run=dry_run,
        )

    def plan(self) -> str:
        """Return a human-readable plan of what will execute, without running."""
        lines = [f"Pipeline: {self.job.name}", f"Output:  {self.job.output_root.resolve()}", ""]
        for i, step in enumerate(self.job.steps):
            lines.append(f"Step {i + 1}: {step.kind.value}")
            try:
                detail = _run_step(step, dry_run=True, output_root=self.job.output_root)
                if detail:
                    lines.append(detail)
            except Exception as exc:
                lines.append(f"  ERROR during plan: {exc}")
            lines.append("")
        return "\n".join(lines)


def load_and_run(
    yaml_path: Path,
    dry_run: bool = False,
    output_root: Path | None = None,
    log_dir: Path | None = None,
) -> PipelineResult:
    """Parse a job YAML and run it.

    CLI arg overrides (output_root, log_dir) take precedence over YAML values.
    """
    job = parse_job_spec(yaml_path)
    if output_root is not None:
        job.output_root = output_root
    if log_dir is not None:
        job.log_dir = log_dir
    runner = PipelineRunner(job)
    return runner.run(dry_run=dry_run)


def plan_job(yaml_path: Path) -> str:
    """Load a YAML job spec and return the plan string."""
    job = parse_job_spec(yaml_path)
    return PipelineRunner(job).plan()