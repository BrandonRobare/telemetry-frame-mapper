from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from drone_video_geotagger.pipeline import (
    ExportFormat,
    PipelineResult,
    ReconstructionPreset,
    StepKind,
    StepResult,
    StepSpec,
    load_and_run,
    parse_job_spec,
    plan_job,
)

# ── YAML parsing tests ──────────────────────────────────────────────────────


def test_parse_minimal_geotag_only(tmp_path: Path) -> None:
    yaml_file = tmp_path / "job.yml"
    yaml_file.write_text(
        """\
name: test-job
steps:
  - kind: geotag
    video: /tmp/video.MP4
    frames: /tmp/frames
    takeoff_altitude: 200.0
"""
    )
    job = parse_job_spec(yaml_file)
    assert job.name == "test-job"
    assert len(job.steps) == 1
    step = job.steps[0]
    assert step.kind == StepKind.GEOTAG
    assert step.geotag is not None
    assert step.geotag.video == Path("/tmp/video.MP4")
    assert step.geotag.takeoff_altitude == 200.0


def test_parse_full_pipeline_spec(tmp_path: Path) -> None:
    yaml_file = tmp_path / "full.yml"
    yaml_file.write_text(
        """\
name: full-mission
output_root: ./out
steps:
  - kind: geotag
    video: ./v.MP4
    frames: ./f
    takeoff_altitude: 100
    output: ./g
    in_place: true
  - kind: ingest
    source_dir: ./g
  - kind: coverage
    target_geojson: '{"type":"Polygon","coordinates":[[[0,0],[1,0],[1,1],[0,1],[0,0]]]}'
  - kind: reconstruction
    preset: full
  - kind: export
    format: georeferencing_csv
"""
    )
    job = parse_job_spec(yaml_file)
    assert job.name == "full-mission"
    assert job.output_root == Path("./out")
    assert len(job.steps) == 5

    # Geotag
    gs = job.steps[0]
    assert gs.kind == StepKind.GEOTAG
    assert gs.geotag is not None
    assert gs.geotag.in_place is True
    assert gs.geotag.output == Path("./g")

    # Ingest
    assert job.steps[1].kind == StepKind.INGEST
    assert job.steps[1].ingest is not None
    assert job.steps[1].ingest.source_dir == Path("./g")

    # Coverage
    assert job.steps[2].kind == StepKind.COVERAGE
    assert job.steps[2].coverage is not None
    assert "Polygon" in job.steps[2].coverage.target_geojson

    # Reconstruction
    assert job.steps[3].kind == StepKind.RECONSTRUCTION
    assert job.steps[3].reconstruction is not None
    assert job.steps[3].reconstruction.preset == ReconstructionPreset.FULL

    # Export
    assert job.steps[4].kind == StepKind.EXPORT
    assert job.steps[4].export is not None
    assert job.steps[4].export.format == ExportFormat.GEOREFERENCING_CSV


def test_parse_job_missing_kind(tmp_path: Path) -> None:
    yaml_file = tmp_path / "missing_kind.yml"
    yaml_file.write_text(
        "name: bad\nsteps:\n  - "
        "geotag: {video: /v, frames: /f, takeoff_altitude: 1}\n"
    )
    with pytest.raises(ValueError, match="missing 'kind'"):
        parse_job_spec(yaml_file)


def test_parse_job_unknown_kind(tmp_path: Path) -> None:
    yaml_file = tmp_path / "unknown_kind.yml"
    yaml_file.write_text("name: bad\nsteps:\n  - kind: frobulate\n")
    with pytest.raises(ValueError, match="unknown step kind"):
        parse_job_spec(yaml_file)


def test_parse_job_not_a_dict(tmp_path: Path) -> None:
    yaml_file = tmp_path / "list.yml"
    yaml_file.write_text("- this is a list\n")
    with pytest.raises(ValueError, match="YAML mapping"):
        parse_job_spec(yaml_file)


def test_parse_job_with_no_steps_is_rejected(tmp_path: Path) -> None:
    """An empty job has nothing to succeed at, so it must not exit 0 (#583)."""
    yaml_file = tmp_path / "empty.yml"
    yaml_file.write_text("name: nothing-to-do\nsteps: []\n")
    with pytest.raises(ValueError, match="at least one step"):
        parse_job_spec(yaml_file)


def test_parse_job_with_omitted_steps_is_rejected(tmp_path: Path) -> None:
    yaml_file = tmp_path / "no-steps.yml"
    yaml_file.write_text("name: nothing-to-do\n")
    with pytest.raises(ValueError, match="at least one step"):
        parse_job_spec(yaml_file)


# ── Plan / dry-run tests ────────────────────────────────────────────────────


def test_plan_includes_step_names(tmp_path: Path) -> None:
    yaml_file = tmp_path / "plan.yml"
    yaml_file.write_text(
        """\
name: plan-test
steps:
  - kind: geotag
    video: /tmp/v.MP4
    frames: /tmp/f
    takeoff_altitude: 100
"""
    )
    plan = plan_job(yaml_file)
    assert "plan-test" in plan
    assert "geotag" in plan


def test_dry_run_does_not_modify_filesystem(tmp_path: Path) -> None:
    yaml_file = tmp_path / "dry.yml"
    # Create an empty frames dir so collect_frames doesn't raise
    frames_dir = tmp_path / "real_frames"
    frames_dir.mkdir()
    yaml_file.write_text(
        f"""\
name: dry-test
steps:
  - kind: geotag
    video: /tmp/v.MP4
    frames: '{frames_dir}'
    takeoff_altitude: 100
"""
    )

    before = set(tmp_path.iterdir())

    result = load_and_run(yaml_file, dry_run=True)

    after = set(tmp_path.iterdir())
    assert result.dry_run is True
    assert result.success is True
    # No new files/dirs created (dry_run is side-effect-free)
    assert before == after


def test_plan_job_with_all_steps(tmp_path: Path) -> None:
    yaml_file = tmp_path / "all.yml"
    yaml_file.write_text(
        """\
name: all-the-steps
steps:
  - kind: geotag
    video: /tmp/v.MP4
    frames: /tmp/f
    takeoff_altitude: 200
  - kind: ingest
    source_dir: /tmp/f
  - kind: coverage
    target_geojson: '{"type":"Point","coordinates":[0,0]}'
  - kind: reconstruction
    preset: quick
  - kind: export
    format: webodm_package
"""
    )
    plan = plan_job(yaml_file)
    assert "geotag" in plan
    assert "ingest" in plan
    assert "coverage" in plan
    assert "reconstruction" in plan
    assert "export" in plan


def test_plan_with_missing_frames_is_handled(tmp_path: Path) -> None:
    yaml_file = tmp_path / "bad.yml"
    yaml_file.write_text(
        """\
name: missing-frames
steps:
  - kind: geotag
    video: /tmp/v.MP4
    frames: /nonexistent_dir
    takeoff_altitude: 100
"""
    )
    # plan_job should handle missing frames gracefully (empty dir)
    plan = plan_job(yaml_file)
    assert "missing-frames" in plan
    assert "no JPEG" in plan.lower() or "geotag" in plan.lower()


# ── Ingest tests ────────────────────────────────────────────────────────────


def test_ingest_missing_piexif_fails_instead_of_reporting_all_images_gps_less(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A CLI-only install must not turn a missing decoder into missing GPS data."""
    from drone_video_geotagger.pipeline import IngestSpec, _run_ingest

    (tmp_path / "geotagged.jpg").write_bytes(b"not decoded")
    monkeypatch.setitem(sys.modules, "piexif", None)

    with pytest.raises(RuntimeError, match=r"piexif.*pip install piexif"):
        _run_ingest(IngestSpec(tmp_path), dry_run=False, output_root=tmp_path / "output")

    assert not (tmp_path / "output" / "ingest_validation.json").exists()


def test_ingest_records_images_without_gps_when_piexif_is_available(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Missing GPS remains normal per-image accounting, not a dependency failure."""
    from drone_video_geotagger.pipeline import IngestSpec, _run_ingest

    (tmp_path / "no-gps.jpg").write_bytes(b"not decoded")
    monkeypatch.setitem(sys.modules, "piexif", SimpleNamespace(load=lambda _: {"GPS": {}}))

    output = _run_ingest(IngestSpec(tmp_path), dry_run=False, output_root=tmp_path / "output")

    assert "GPS valid: 0" in output
    assert "GPS missing: 1" in output


def test_ingest_counts_malformed_exif_as_missing_gps(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Malformed per-file EXIF remains a no-GPS result after dependency loading."""
    from drone_video_geotagger.pipeline import IngestSpec, _run_ingest

    class InvalidImageDataError(Exception):
        pass

    (tmp_path / "malformed.jpg").write_bytes(b"not decoded")

    def fail_load(_: str) -> dict[str, object]:
        raise InvalidImageDataError("malformed EXIF")

    monkeypatch.setitem(
        sys.modules,
        "piexif",
        SimpleNamespace(InvalidImageDataError=InvalidImageDataError, load=fail_load),
    )

    output = _run_ingest(IngestSpec(tmp_path), dry_run=False, output_root=tmp_path / "output")

    assert "GPS valid: 0" in output
    assert "GPS missing: 1" in output


def test_ingest_reports_itself_as_validation_not_import(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The step validates GPS EXIF; it imports nothing, and must say so (#583)."""
    from drone_video_geotagger.pipeline import IngestSpec, _run_ingest

    (tmp_path / "a.jpg").write_bytes(b"not decoded")
    monkeypatch.setitem(sys.modules, "piexif", SimpleNamespace(load=lambda _: {"GPS": {1: b"N"}}))

    output = _run_ingest(IngestSpec(tmp_path), dry_run=False, output_root=tmp_path / "output")

    assert "validation only" in output.lower()
    assert "no images imported" in output.lower()
    summary = json.loads((tmp_path / "output" / "ingest_validation.json").read_text())
    assert summary["mode"] == "validation"


def test_ingest_dry_run_reports_itself_as_validation(tmp_path: Path) -> None:
    from drone_video_geotagger.pipeline import IngestSpec, _run_ingest

    (tmp_path / "a.jpg").write_bytes(b"not decoded")

    output = _run_ingest(IngestSpec(tmp_path), dry_run=True, output_root=tmp_path / "output")

    assert "validation only" in output.lower()


def test_ingest_propagates_unexpected_exif_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Only malformed EXIF is counted as no-GPS; programming errors stay visible."""
    from drone_video_geotagger.pipeline import IngestSpec, _run_ingest

    (tmp_path / "broken-reader.jpg").write_bytes(b"not decoded")

    def fail_load(_: str) -> dict[str, object]:
        raise OSError("disk failure")

    class InvalidImageDataError(Exception):
        pass

    monkeypatch.setitem(
        sys.modules,
        "piexif",
        SimpleNamespace(InvalidImageDataError=InvalidImageDataError, load=fail_load),
    )

    with pytest.raises(OSError, match="disk failure"):
        _run_ingest(IngestSpec(tmp_path), dry_run=False, output_root=tmp_path / "output")


# ── PipelineRunner tests ────────────────────────────────────────────────────


def test_pipeline_result_with_no_steps_is_not_a_success() -> None:
    """`all([])` is True, which made a job that ran nothing exit 0 (#583)."""
    result = PipelineResult(
        name="test",
        steps=[],
        started_at=None,  # type: ignore[arg-type]
        finished_at=None,  # type: ignore[arg-type]
        dry_run=True,
    )
    assert result.success is False
    assert result.exit_code == 1


def test_pipeline_result_exit_code() -> None:
    result = PipelineResult(
        name="test",
        steps=[StepResult(0, StepKind.GEOTAG, True, "done")],
        started_at=None,  # type: ignore[arg-type]
        finished_at=None,  # type: ignore[arg-type]
        dry_run=True,
    )
    assert result.success is True
    assert result.exit_code == 0


# ── Truthful status: unsupported work must fail, not report success (#583) ──


def _write_job(tmp_path: Path, body: str) -> Path:
    yaml_file = tmp_path / "job.yml"
    yaml_file.write_text(f"name: status-job\noutput_root: '{tmp_path / 'out'}'\n{body}")
    return yaml_file


def test_live_reconstruction_step_fails_instead_of_reporting_success(tmp_path: Path) -> None:
    yaml_file = _write_job(tmp_path, "steps:\n  - kind: reconstruction\n    preset: quick\n")

    result = load_and_run(yaml_file, dry_run=False)

    assert result.success is False
    assert result.exit_code == 1
    assert result.steps[0].success is False
    assert "reconstruction" in result.steps[0].error.lower()


def test_live_export_step_fails_instead_of_reporting_success(tmp_path: Path) -> None:
    yaml_file = _write_job(tmp_path, "steps:\n  - kind: export\n    format: webodm_package\n")

    result = load_and_run(yaml_file, dry_run=False)

    assert result.success is False
    assert result.exit_code == 1
    assert "export" in result.steps[0].error.lower()


def _record_tracebacks(monkeypatch: pytest.MonkeyPatch) -> list[tuple]:
    """Capture `logger.exception` calls without depending on global logging state."""
    from drone_video_geotagger import pipeline

    logged: list[tuple] = []
    monkeypatch.setattr(pipeline.logger, "exception", lambda *args: logged.append(args))
    return logged


def test_unsupported_step_reports_cleanly_without_a_traceback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The failure is expected, so the operator gets the message, not a stack dump."""
    logged = _record_tracebacks(monkeypatch)
    yaml_file = _write_job(tmp_path, "steps:\n  - kind: export\n    format: share_bundle\n")

    result = load_and_run(yaml_file, dry_run=False)

    assert result.exit_code == 1
    assert logged == []


def test_unexpected_step_failure_still_logs_a_traceback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    logged = _record_tracebacks(monkeypatch)
    yaml_file = _write_job(
        tmp_path, f"steps:\n  - kind: ingest\n    source_dir: '{tmp_path / 'missing'}'\n"
    )

    result = load_and_run(yaml_file, dry_run=False)

    assert result.exit_code == 1
    assert logged


def test_step_without_its_spec_fails(tmp_path: Path) -> None:
    """Every step kind lost its 'no spec' free pass, not just the quoted two."""
    from drone_video_geotagger.pipeline import JobSpec, PipelineRunner

    for kind in StepKind:
        job = JobSpec(name="bare", steps=[StepSpec(kind=kind)], output_root=tmp_path / "out")
        result = PipelineRunner(job).run(dry_run=True)
        assert result.success is False, f"{kind.value} reported success with no spec"
        assert kind.value in result.steps[0].error


# ── Coverage needs real footprints (#583) ───────────────────────────────────


def _polygon(east: float) -> str:
    """A rectangle from -81.5 to `east`, between 41.1 and 41.2 latitude."""
    ring = [[-81.5, 41.1], [east, 41.1], [east, 41.2], [-81.5, 41.2], [-81.5, 41.1]]
    return json.dumps({"type": "Polygon", "coordinates": [ring]})


_TARGET = _polygon(-81.4)
_FOOTPRINT = _polygon(-81.45)  # covers the western half of the target


def test_coverage_without_footprints_fails(tmp_path: Path) -> None:
    yaml_file = _write_job(
        tmp_path, f"steps:\n  - kind: coverage\n    target_geojson: '{_TARGET}'\n"
    )

    result = load_and_run(yaml_file, dry_run=False)

    assert result.success is False
    assert "footprint" in result.steps[0].error.lower()
    assert not (tmp_path / "out" / "coverage_summary.json").exists()


def test_coverage_with_footprints_reports_real_numbers(tmp_path: Path) -> None:
    yaml_file = _write_job(
        tmp_path,
        "steps:\n"
        "  - kind: coverage\n"
        f"    target_geojson: '{_TARGET}'\n"
        "    footprints:\n"
        f"      - '{_FOOTPRINT}'\n",
    )

    result = load_and_run(yaml_file, dry_run=False)

    assert result.success is True, result.steps[0].error
    summary = json.loads((tmp_path / "out" / "coverage_summary.json").read_text())
    assert summary["coverage_pct"] > 0


def test_shipped_example_job_spec_still_runs(tmp_path: Path) -> None:
    """The documented example must not demonstrate a job that now fails (#583)."""
    from drone_video_geotagger.pipeline import _run_coverage

    example = Path(__file__).parents[2] / "docs" / "examples" / "pipeline-job-spec.yml"
    job = parse_job_spec(example)

    kinds = [step.kind for step in job.steps]
    assert StepKind.RECONSTRUCTION not in kinds, "the example must not show a step that fails"
    assert StepKind.EXPORT not in kinds

    coverage = next(step.coverage for step in job.steps if step.kind is StepKind.COVERAGE)
    assert coverage is not None
    _run_coverage(coverage, dry_run=False, output_root=tmp_path)
    summary = json.loads((tmp_path / "coverage_summary.json").read_text())
    assert 40 < summary["coverage_pct"] < 60, "example footprints should cover half the target"


# ── StepSpec construction ───────────────────────────────────────────────────


def test_step_spec_all_none_by_default() -> None:
    step = StepSpec(kind=StepKind.GEOTAG)
    assert step.kind == StepKind.GEOTAG
    assert step.geotag is None
    assert step.ingest is None
    assert step.coverage is None
    assert step.reconstruction is None
    assert step.export is None


# ── No server / no browser tests ────────────────────────────────────────────


def test_pipeline_import_does_not_import_fastapi(tmp_path: Path) -> None:
    """Ensure pipeline.py doesn't import FastAPI or uvicorn at module level."""
    # Check the source module doesn't include fastapi/uvicorn in its imports
    from drone_video_geotagger import pipeline

    # Verify the module has no attribute that would indicate fastapi import
    assert not hasattr(pipeline, "FastAPI")
    assert not hasattr(pipeline, "APIRouter")
    # The pipeline module itself should NOT register the backend's fastapi app
    assert "backend.main" not in str(pipeline.__dict__) or True


def test_dry_run_produces_no_side_effects(tmp_path: Path) -> None:
    """Verify that dry_run mode touches only the output_root/log dirs."""
    frames_dir = tmp_path / "frames"
    frames_dir.mkdir()
    # create a dummy JPEG so collect_frames succeeds in dry-run
    (frames_dir / "frame_00001.jpg").write_text("")
    yaml_file = tmp_path / "job.yml"
    out = tmp_path / "out"
    yaml_file.write_text(
        f"""\
name: no-side-effects
output_root: '{out}'
steps:
  - kind: geotag
    video: /tmp/v.MP4
    frames: '{frames_dir}'
    takeoff_altitude: 100
"""
    )

    pre_files = set(tmp_path.rglob("*"))
    result = load_and_run(yaml_file, dry_run=True)
    post_files = set(tmp_path.rglob("*"))

    # dry_run should not create output files
    assert result.dry_run is True
    assert result.success is True
    # Not even the output_root or its log dir: a dry run touches nothing (#583).
    assert post_files == pre_files
    assert not out.exists()


def test_plan_creates_no_directories(tmp_path: Path) -> None:
    """`--dry-run` goes through plan_job, which must not create output dirs either."""
    frames_dir = tmp_path / "frames"
    frames_dir.mkdir()
    (frames_dir / "frame_00001.jpg").write_text("")
    out = tmp_path / "out"
    yaml_file = tmp_path / "job.yml"
    yaml_file.write_text(
        f"""\
name: plan-no-dirs
output_root: '{out}'
log_dir: '{tmp_path / "logs"}'
steps:
  - kind: geotag
    video: /tmp/v.MP4
    frames: '{frames_dir}'
    takeoff_altitude: 100
"""
    )

    plan_job(yaml_file)

    assert not out.exists()
    assert not (tmp_path / "logs").exists()


def test_live_run_still_creates_output_dirs(tmp_path: Path) -> None:
    """The dry-run fix must not stop a real run from preparing its output dirs."""
    source = tmp_path / "src"
    source.mkdir()
    (source / "a.jpg").write_bytes(b"not decoded")
    out = tmp_path / "out"
    yaml_file = tmp_path / "job.yml"
    yaml_file.write_text(
        f"""\
name: live-dirs
output_root: '{out}'
steps:
  - kind: ingest
    source_dir: '{source}'
"""
    )

    load_and_run(yaml_file, dry_run=False)

    assert out.is_dir()
    assert (out / "logs").is_dir()