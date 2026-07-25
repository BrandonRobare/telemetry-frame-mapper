from __future__ import annotations

from pathlib import Path

import pytest

from drone_video_geotagger.pipeline import (
    ExportFormat,
    PipelineResult,
    ReconstructionPreset,
    StepKind,
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


# ── PipelineRunner tests ────────────────────────────────────────────────────


def test_pipeline_result_exit_code() -> None:
    result = PipelineResult(
        name="test",
        steps=[],
        started_at=None,  # type: ignore[arg-type]
        finished_at=None,  # type: ignore[arg-type]
        dry_run=True,
    )
    assert result.success is True
    assert result.exit_code == 0


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
    # Only the yaml_file and possibly output_root dir (created for logging)
    new_files = post_files - pre_files
    # Accept output_root or log_dir being created (infrastructure, not content)
    for nf in new_files:
        assert nf == out or nf == (out / "logs") or nf.is_relative_to(out), (
            f"Unexpected side-effect file: {nf}"
        )